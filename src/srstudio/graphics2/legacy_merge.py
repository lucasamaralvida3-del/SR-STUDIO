from __future__ import annotations

"""Three-way merge seguro entre StudioProject e uma sessão SR Scene 2.

O Studio 5 e o Graphics Engine 2 podem continuar sendo editados em paralelo.
Quando ambos mudam depois da criação da sessão, o sync simples precisa bloquear
para não perder trabalho. Este módulo compara três estados:

- BASE: snapshot do Studio que originou a sessão G2;
- STUDIO: estado atual do projeto legado;
- G2: projeção seletiva da sessão atual sobre a BASE.

Mudanças independentes são combinadas automaticamente. Conflitos verdadeiros
podem ser resolvidos por campo escolhendo Studio, Graphics 2 ou BASE. Quando o
Studio vence um campo, o valor também é projetado seletivamente de volta para a
representação compatível do SR Scene; assim o mesmo conflito não reaparece na
próxima abertura e recursos exclusivos do G2 continuam intocados.
"""

from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any
import copy

from srstudio.core.models import Page, Product, ProductCard, StudioProject, to_decimal

from .legacy_sync import fingerprint_studio_project, sync_graphics_to_studio
from .model import AssetRef, BindingRole, GraphicsDocument, NodeKind

LEGACY_SOURCE_SNAPSHOT_KEY = "legacy_source_snapshot"
LEGACY_MERGE_SCHEMA = "srstudio/graphics2-legacy-merge-2"
_MISSING = object()

_PRODUCT_FIELDS = (
    "code",
    "ean",
    "original_name",
    "display_name",
    "price",
    "app_price",
    "wholesale_price",
    "retail_price",
    "unit",
    "quantity",
    "cpf_limit",
    "category",
    "image_path",
    "campaign",
    "validity",
)
_PRICE_FIELDS = {"price", "app_price", "wholesale_price", "retail_price"}
_PAGE_FIELDS = ("name", "width", "height", "background")
_CARD_FIELDS = ("product_id", "x", "y", "width", "height", "rotation", "locked", "highlighted", "style_id", "z_index")
_VALID_DECISIONS = {"studio", "graphics2", "base"}


@dataclass(slots=True, frozen=True)
class LegacyMergeConflict:
    path: str
    category: str
    base: Any
    studio: Any
    graphics2: Any

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class LegacyMergeReport:
    ok: bool
    source_fingerprint: str = ""
    current_fingerprint: str = ""
    result_fingerprint: str = ""
    applied: int = 0
    resolved: int = 0
    unchanged: int = 0
    decisions: dict[str, str] = field(default_factory=dict)
    conflicts: list[LegacyMergeConflict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def conflict(self) -> bool:
        return bool(self.conflicts)

    @property
    def unresolved_conflicts(self) -> int:
        return len(self.conflicts)

    @property
    def changes(self) -> int:
        return self.applied

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": LEGACY_MERGE_SCHEMA,
            "ok": self.ok,
            "conflict": self.conflict,
            "source_fingerprint": self.source_fingerprint,
            "current_fingerprint": self.current_fingerprint,
            "result_fingerprint": self.result_fingerprint,
            "applied": self.applied,
            "resolved": self.resolved,
            "unchanged": self.unchanged,
            "unresolved_conflicts": self.unresolved_conflicts,
            "decisions": dict(self.decisions),
            "conflicts": [item.to_dict() for item in self.conflicts],
            "warnings": list(self.warnings),
        }


def analyze_legacy_merge(document: GraphicsDocument, project: StudioProject) -> LegacyMergeReport:
    """Analisa conflitos sem alterar o projeto nem o documento fornecidos."""

    base = _base_project(document)
    current_fingerprint = fingerprint_studio_project(project)
    source_fingerprint = str(document.metadata.get("legacy_source_fingerprint") or "")
    if base is None:
        return LegacyMergeReport(
            ok=False,
            source_fingerprint=source_fingerprint,
            current_fingerprint=current_fingerprint,
            warnings=["A sessão G2 não possui snapshot BASE para merge assistido."],
        )
    if str(base.id) != str(project.id):
        return LegacyMergeReport(
            ok=False,
            source_fingerprint=source_fingerprint,
            current_fingerprint=current_fingerprint,
            warnings=["O snapshot BASE pertence a outro projeto do Studio."],
        )

    projected = _project_graphics2_over_base(document, base)
    base_values = _flatten_project(base)
    studio_values = _flatten_project(project)
    g2_values = _flatten_project(projected)
    conflicts: list[LegacyMergeConflict] = []
    unchanged = 0

    for path in sorted(set(base_values) | set(studio_values) | set(g2_values)):
        base_value = base_values.get(path, _MISSING)
        studio_value = studio_values.get(path, _MISSING)
        g2_value = g2_values.get(path, _MISSING)
        g2_changed = not _same(g2_value, base_value)
        studio_changed = not _same(studio_value, base_value)
        if not g2_changed:
            unchanged += 1
            continue
        if studio_changed and not _same(studio_value, g2_value):
            conflicts.append(
                LegacyMergeConflict(
                    path=path,
                    category=path.split("/", 1)[0],
                    base=_public(base_value),
                    studio=_public(studio_value),
                    graphics2=_public(g2_value),
                )
            )

    return LegacyMergeReport(
        ok=True,
        source_fingerprint=source_fingerprint,
        current_fingerprint=current_fingerprint,
        unchanged=unchanged,
        conflicts=conflicts,
    )


def merge_graphics_to_studio_non_conflicting(document: GraphicsDocument, project: StudioProject) -> LegacyMergeReport:
    """Aplica mudanças G2 seguras e preserva conflitos para decisão posterior."""

    analysis = analyze_legacy_merge(document, project)
    if not analysis.ok:
        return analysis
    base = _base_project(document)
    assert base is not None
    projected = _project_graphics2_over_base(document, base)
    base_values = _flatten_project(base)
    studio_values = _flatten_project(project)
    g2_values = _flatten_project(projected)
    conflict_paths = {item.path for item in analysis.conflicts}
    applied = _add_new_products(projected, base, project)

    for path in sorted(set(base_values) | set(g2_values)):
        if path in conflict_paths:
            continue
        base_value = base_values.get(path, _MISSING)
        g2_value = g2_values.get(path, _MISSING)
        if _same(base_value, g2_value):
            continue
        studio_value = studio_values.get(path, _MISSING)
        if _same(studio_value, g2_value):
            continue
        if _set_path(project, path, g2_value):
            applied += 1

    # Se o Studio alterou um campo e o G2 não, essa mudança também precisa ir
    # para a representação compatível do documento. Caso contrário, avançar a
    # BASE faria o valor antigo do G2 parecer uma nova edição na próxima sessão.
    _reconcile_studio_only_changes(document, base_values, studio_values, g2_values, conflict_paths)

    analysis.applied = applied
    analysis.result_fingerprint = fingerprint_studio_project(project)
    document.metadata["legacy_merge_last_report"] = analysis.to_dict()
    if not analysis.conflicts:
        _advance_base(document, project, analysis.result_fingerprint)
    return analysis


def resolve_legacy_merge_conflicts(
    document: GraphicsDocument,
    project: StudioProject,
    resolutions: dict[str, str],
    *,
    apply_non_conflicting: bool = True,
) -> LegacyMergeReport:
    """Resolve conflitos individualmente com decisões ``studio|graphics2|base``.

    Campos sem decisão permanecem conflitantes. Escolher ``studio`` atualiza a
    representação compatível do SR Scene; escolher ``graphics2`` atualiza o
    Studio; ``base`` restaura o valor comum nos dois lados. Recursos que não
    existem no Studio 5 não são tocados por este processo.
    """

    analysis = analyze_legacy_merge(document, project)
    if not analysis.ok:
        return analysis
    base = _base_project(document)
    assert base is not None
    projected = _project_graphics2_over_base(document, base)
    base_values = _flatten_project(base)
    studio_values = _flatten_project(project)
    g2_values = _flatten_project(projected)
    conflict_by_path = {item.path: item for item in analysis.conflicts}
    decisions = {str(path): str(choice).strip().lower() for path, choice in dict(resolutions or {}).items()}
    applied = _add_new_products(projected, base, project) if apply_non_conflicting else 0
    resolved = 0
    warnings: list[str] = []

    if apply_non_conflicting:
        for path in sorted(set(base_values) | set(g2_values)):
            if path in conflict_by_path:
                continue
            base_value = base_values.get(path, _MISSING)
            g2_value = g2_values.get(path, _MISSING)
            if _same(base_value, g2_value):
                continue
            studio_value = studio_values.get(path, _MISSING)
            if not _same(studio_value, g2_value) and _set_path(project, path, g2_value):
                applied += 1
        _reconcile_studio_only_changes(document, base_values, studio_values, g2_values, set(conflict_by_path))

    accepted: dict[str, str] = {}
    for path, conflict in conflict_by_path.items():
        choice = decisions.get(path, "")
        if choice not in _VALID_DECISIONS:
            if choice:
                warnings.append(f"Decisão inválida para {path}: {choice}.")
            continue
        accepted[path] = choice
        if choice == "graphics2":
            if _set_path(project, path, g2_values.get(path, _MISSING)):
                applied += 1
                resolved += 1
            else:
                warnings.append(f"Não foi possível aplicar o valor G2 em {path}.")
        elif choice == "studio":
            if _set_graphics_path(document, path, studio_values.get(path, _MISSING), project):
                resolved += 1
            else:
                warnings.append(f"Não foi possível reconciliar o valor do Studio em {path} no SR Scene.")
        else:  # base
            base_value = base_values.get(path, _MISSING)
            project_ok = _set_path(project, path, base_value)
            scene_ok = _set_graphics_path(document, path, base_value, project)
            if project_ok and scene_ok:
                applied += 1
                resolved += 1
            else:
                warnings.append(f"Não foi possível restaurar a BASE em {path}.")

    # Reanalisa após aplicar as decisões. Isso é mais seguro do que simplesmente
    # remover conflitos da lista, pois verifica que Studio e SR Scene realmente
    # convergiram para o valor escolhido.
    post = analyze_legacy_merge(document, project)
    post.applied = applied
    post.resolved = resolved
    post.decisions = accepted
    post.warnings.extend(warnings)
    post.result_fingerprint = fingerprint_studio_project(project)
    document.metadata["legacy_merge_last_report"] = post.to_dict()
    if post.ok and not post.conflicts:
        _advance_base(document, project, post.result_fingerprint)
    return post


def _advance_base(document: GraphicsDocument, project: StudioProject, fingerprint: str) -> None:
    document.metadata["legacy_source_fingerprint"] = fingerprint
    document.metadata[LEGACY_SOURCE_SNAPSHOT_KEY] = copy.deepcopy(project.to_dict())
    document.metadata["legacy_last_sync_fingerprint"] = fingerprint


def _reconcile_studio_only_changes(
    document: GraphicsDocument,
    base_values: dict[str, Any],
    studio_values: dict[str, Any],
    g2_values: dict[str, Any],
    conflict_paths: set[str],
) -> None:
    for path in sorted(set(base_values) | set(studio_values)):
        if path in conflict_paths:
            continue
        base_value = base_values.get(path, _MISSING)
        studio_value = studio_values.get(path, _MISSING)
        g2_value = g2_values.get(path, _MISSING)
        studio_changed = not _same(studio_value, base_value)
        g2_changed = not _same(g2_value, base_value)
        if studio_changed and not g2_changed:
            _set_graphics_path(document, path, studio_value, None)


def _add_new_products(projected: StudioProject, base: StudioProject, project: StudioProject) -> int:
    added = 0
    base_products = {item.id for item in base.products}
    current_products = {item.id for item in project.products}
    for source_product in projected.products:
        if source_product.id in base_products or source_product.id in current_products:
            continue
        project.products.append(Product.from_dict(source_product.to_dict()))
        current_products.add(source_product.id)
        added += 1
    return added


def _base_project(document: GraphicsDocument) -> StudioProject | None:
    raw = document.metadata.get(LEGACY_SOURCE_SNAPSHOT_KEY) if isinstance(document.metadata, dict) else None
    if not isinstance(raw, dict):
        return None
    try:
        return _project_from_dict(raw)
    except Exception:
        return None


def _project_graphics2_over_base(document: GraphicsDocument, base: StudioProject) -> StudioProject:
    projected = _project_from_dict(base.to_dict())
    document_copy = GraphicsDocument.from_dict(document.to_dict())
    report = sync_graphics_to_studio(document_copy, projected, allow_conflict=True)
    if not report.ok:
        raise RuntimeError("Não foi possível projetar a sessão G2 sobre o snapshot BASE.")
    return projected


def _project_from_dict(raw: dict[str, Any]) -> StudioProject:
    products = [Product.from_dict(dict(item)) for item in raw.get("products") or [] if isinstance(item, dict)]
    pages: list[Page] = []
    for page_raw in raw.get("pages") or []:
        if not isinstance(page_raw, dict):
            continue
        cards = [ProductCard(**dict(item)) for item in page_raw.get("cards") or [] if isinstance(item, dict)]
        pages.append(
            Page(
                id=str(page_raw.get("id") or ""),
                name=str(page_raw.get("name") or "Página"),
                width=float(page_raw.get("width") or 1080.0),
                height=float(page_raw.get("height") or 1350.0),
                background=str(page_raw.get("background") or "#FFFFFF"),
                cards=cards,
                elements=copy.deepcopy(page_raw.get("elements") or []),
            )
        )
    return StudioProject(
        schema_version=int(raw.get("schema_version") or 1),
        id=str(raw.get("id") or ""),
        name=str(raw.get("name") or "Novo Projeto"),
        campaign=str(raw.get("campaign") or ""),
        products=products,
        pages=pages,
        settings=copy.deepcopy(raw.get("settings") or {}),
    )


def _flatten_project(project: StudioProject) -> dict[str, Any]:
    values: dict[str, Any] = {"pages/order": tuple(page.id for page in project.pages)}
    for product in project.products:
        for field_name in _PRODUCT_FIELDS:
            values[f"product/{product.id}/{field_name}"] = _normalize(getattr(product, field_name))
    for page in project.pages:
        for field_name in _PAGE_FIELDS:
            values[f"page/{page.id}/{field_name}"] = _normalize(getattr(page, field_name))
        for card in page.cards:
            for field_name in _CARD_FIELDS:
                values[f"card/{page.id}/{card.id}/{field_name}"] = _normalize(getattr(card, field_name))
    return values


def _set_path(project: StudioProject, path: str, value: Any) -> bool:
    parts = path.split("/")
    if path == "pages/order":
        if value is _MISSING:
            return False
        order = [str(item) for item in value]
        by_id = {page.id: page for page in project.pages}
        if len(order) != len(project.pages) or set(order) != set(by_id):
            return False
        project.pages[:] = [by_id[item] for item in order]
        return True
    if len(parts) == 3 and parts[0] == "product":
        product = next((item for item in project.products if item.id == parts[1]), None)
        field_name = parts[2]
        if product is None or field_name not in _PRODUCT_FIELDS or value is _MISSING:
            return False
        if field_name in _PRICE_FIELDS:
            setattr(product, field_name, to_decimal(value))
        else:
            setattr(product, field_name, value)
        return True
    if len(parts) == 3 and parts[0] == "page":
        page = next((item for item in project.pages if item.id == parts[1]), None)
        if page is None or parts[2] not in _PAGE_FIELDS or value is _MISSING:
            return False
        setattr(page, parts[2], value)
        return True
    if len(parts) == 4 and parts[0] == "card":
        page = next((item for item in project.pages if item.id == parts[1]), None)
        if page is None:
            return False
        card = next((item for item in page.cards if item.id == parts[2]), None)
        if card is None or parts[3] not in _CARD_FIELDS or value is _MISSING:
            return False
        setattr(card, parts[3], value)
        return True
    return False


def _set_graphics_path(
    document: GraphicsDocument,
    path: str,
    value: Any,
    project: StudioProject | None,
) -> bool:
    if value is _MISSING:
        return False
    parts = path.split("/")
    if path == "pages/order":
        order = [str(item) for item in value]
        by_id = {page.id: page for page in document.pages}
        if len(order) != len(document.pages) or set(order) != set(by_id):
            return False
        document.pages[:] = [by_id[item] for item in order]
        if document.active_page_id not in by_id and document.pages:
            document.active_page_id = document.pages[0].id
        return True

    if len(parts) == 3 and parts[0] == "page":
        page = next((item for item in document.pages if item.id == parts[1]), None)
        field_name = parts[2]
        if page is None or field_name not in _PAGE_FIELDS:
            return False
        if field_name in {"width", "height"}:
            setattr(page, field_name, float(value))
        else:
            setattr(page, field_name, str(value))
        return True

    if len(parts) == 4 and parts[0] == "card":
        page = next((item for item in document.pages if item.id == parts[1]), None)
        if page is None:
            return False
        node = page.nodes.get(parts[2])
        field_name = parts[3]
        if node is None or node.kind is not NodeKind.GROUP or field_name not in _CARD_FIELDS:
            return False
        if field_name in {"x", "y", "width", "height", "rotation"}:
            setattr(node.transform, field_name, float(value))
        elif field_name == "locked":
            node.locked = bool(value)
        elif field_name == "z_index":
            node.z_index = int(value)
        elif field_name == "product_id":
            node.metadata["legacy_product_id"] = str(value)
            descendants = set(page.descendants(node.id))
            for slot in page.slots.values():
                if descendants.intersection(slot.node_by_role.values()):
                    slot.product_id = str(value)
                    slot.metadata["product_id"] = str(value)
        elif field_name == "highlighted":
            node.metadata["legacy_highlighted"] = bool(value)
        elif field_name == "style_id":
            node.metadata["legacy_style_id"] = str(value)
        else:
            return False
        return True

    if len(parts) == 3 and parts[0] == "product":
        product_id, field_name = parts[1], parts[2]
        if field_name not in _PRODUCT_FIELDS:
            return False
        normalized_value = _normalize_product_value(field_name, value)
        _update_document_product_payload(document, product_id, field_name, normalized_value, project)
        handled = field_name in {"code", "ean", "original_name", "category", "campaign"}
        for page in document.pages:
            for slot in page.slots.values():
                if _slot_product_id(slot) != product_id:
                    continue
                snapshot = slot.metadata.get("product_snapshot")
                if isinstance(snapshot, dict):
                    snapshot[field_name] = normalized_value
                if field_name == "display_name":
                    handled = _set_slot_text(page, slot, BindingRole.NAME, str(normalized_value or "")) or handled
                elif field_name == "price":
                    whole, cents = _price_parts(normalized_value)
                    a = _set_slot_text(page, slot, BindingRole.PRICE_REAIS, whole)
                    b = _set_slot_text(page, slot, BindingRole.PRICE_CENTS, cents)
                    handled = a or b or handled
                elif field_name == "unit":
                    unit = str(normalized_value or "UN").upper().strip().lstrip("/") or "UN"
                    handled = _set_slot_text(page, slot, BindingRole.UNIT, f"/{unit}") or handled
                elif field_name == "cpf_limit":
                    handled = _set_slot_text(page, slot, BindingRole.LIMIT, str(normalized_value or "")) or handled
                elif field_name == "quantity":
                    handled = _set_slot_text(page, slot, BindingRole.QUANTITY, str(normalized_value or "")) or handled
                elif field_name == "validity":
                    handled = _set_slot_text(page, slot, BindingRole.VALIDITY, str(normalized_value or "")) or handled
                elif field_name in {"app_price", "wholesale_price", "retail_price"}:
                    role = {
                        "app_price": BindingRole.APP_PRICE,
                        "wholesale_price": BindingRole.WHOLESALE_PRICE,
                        "retail_price": BindingRole.RETAIL_PRICE,
                    }[field_name]
                    handled = _set_slot_text(page, slot, role, _price_text(normalized_value)) or handled
                elif field_name == "image_path":
                    handled = _set_slot_image(document, page, slot, str(normalized_value or "")) or handled
        return handled
    return False


def _slot_product_id(slot) -> str:
    product_id = str(slot.product_id or slot.metadata.get("product_id") or "")
    if product_id:
        return product_id
    snapshot = slot.metadata.get("product_snapshot")
    return str(snapshot.get("id") or "") if isinstance(snapshot, dict) else ""


def _set_slot_text(page, slot, role: BindingRole, text: str) -> bool:
    node_id = str(slot.node_by_role.get(role.value) or "")
    node = page.nodes.get(node_id) if node_id else None
    if node is None or node.kind is not NodeKind.TEXT:
        return False
    node.text = str(text)
    return True


def _set_slot_image(document: GraphicsDocument, page, slot, source: str) -> bool:
    node_id = str(slot.node_by_role.get(BindingRole.IMAGE.value) or "")
    node = page.nodes.get(node_id) if node_id else None
    if node is None or node.kind is not NodeKind.IMAGE:
        return False
    node.metadata["bound_image_source"] = source
    node.metadata["graphics2_preview_original_source"] = source
    if not source:
        node.asset_id = ""
        return True
    asset = next((item for item in document.assets.values() if str(item.source) == source), None)
    if asset is None:
        asset = AssetRef(kind="image", source=source, embedded=False, metadata={"source": "legacy-merge"})
        document.add_asset(asset)
    node.asset_id = asset.id
    return True


def _update_document_product_payload(
    document: GraphicsDocument,
    product_id: str,
    field_name: str,
    value: Any,
    project: StudioProject | None,
) -> None:
    raw = document.metadata.get("products")
    if not isinstance(raw, list):
        raw = []
        document.metadata["products"] = raw
    payload = next((item for item in raw if isinstance(item, dict) and str(item.get("id") or "") == product_id), None)
    if payload is None:
        product = next((item for item in (project.products if project is not None else []) if item.id == product_id), None)
        payload = product.to_dict() if product is not None else {"id": product_id}
        raw.append(payload)
    payload[field_name] = value


def _normalize_product_value(field_name: str, value: Any) -> Any:
    if field_name in _PRICE_FIELDS:
        amount = to_decimal(value)
        return None if amount is None else str(amount)
    if field_name == "unit":
        return str(value or "UN").upper().strip().lstrip("/") or "UN"
    return value


def _price_parts(value: Any) -> tuple[str, str]:
    amount = to_decimal(value)
    if amount is None:
        return "", ""
    whole, cents = f"{amount.quantize(Decimal('0.01')):.2f}".split(".")
    return whole, f",{cents}"


def _price_text(value: Any) -> str:
    amount = to_decimal(value)
    if amount is None:
        return ""
    return f"{amount.quantize(Decimal('0.01')):.2f}".replace(".", ",")


def _normalize(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, float):
        return round(value, 8)
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    return str(value)


def _same(left: Any, right: Any) -> bool:
    if left is _MISSING or right is _MISSING:
        return left is right
    return left == right


def _public(value: Any) -> Any:
    return None if value is _MISSING else value
