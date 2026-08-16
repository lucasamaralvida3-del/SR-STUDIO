from __future__ import annotations

"""Three-way merge seguro entre StudioProject e uma sessão SR Scene 2.

O Studio 5 e o Graphics Engine 2 podem continuar sendo editados em paralelo.
Quando ambos mudam depois da criação da sessão, o sync simples precisa bloquear
para não perder trabalho. Este módulo compara três estados:

- BASE: snapshot do Studio que originou a sessão G2;
- STUDIO: estado atual do projeto legado;
- G2: projeção seletiva da sessão atual sobre a BASE.

Somente alterações G2 que não conflitam com mudanças do Studio são aplicadas
automaticamente. Conflitos reais permanecem pendentes e recursos exclusivos do
Engine 2 continuam preservados no `.srscene`.
"""

from dataclasses import asdict, dataclass, field
from typing import Any
import copy

from srstudio.core.models import Page, Product, ProductCard, StudioProject

from .legacy_sync import fingerprint_studio_project, sync_graphics_to_studio
from .model import GraphicsDocument

LEGACY_SOURCE_SNAPSHOT_KEY = "legacy_source_snapshot"
LEGACY_MERGE_SCHEMA = "srstudio/graphics2-legacy-merge-1"
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
_PAGE_FIELDS = ("name", "width", "height", "background")
_CARD_FIELDS = ("product_id", "x", "y", "width", "height", "rotation", "locked", "highlighted", "style_id", "z_index")


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
    unchanged: int = 0
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
            "unchanged": self.unchanged,
            "unresolved_conflicts": self.unresolved_conflicts,
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
    """Aplica somente mudanças G2 que não colidem com mudanças atuais do Studio."""

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
    applied = 0

    # Produtos criados no G2 podem voltar ao Studio quando o ID ainda não foi
    # utilizado pelo Studio atual. A cópia inteira evita criar um produto pela
    # metade enquanto os campos individuais são percorridos abaixo.
    base_products = {item.id for item in base.products}
    current_products = {item.id for item in project.products}
    for source_product in projected.products:
        if source_product.id in base_products or source_product.id in current_products:
            continue
        project.products.append(Product.from_dict(source_product.to_dict()))
        current_products.add(source_product.id)
        applied += 1

    for path in sorted(set(base_values) | set(g2_values)):
        if path in conflict_paths:
            continue
        base_value = base_values.get(path, _MISSING)
        g2_value = g2_values.get(path, _MISSING)
        if _same(base_value, g2_value):
            continue
        studio_value = studio_values.get(path, _MISSING)
        # O Studio também pode ter chegado exatamente ao mesmo valor por outra
        # edição; nesse caso não há nada a aplicar nem conflito.
        if _same(studio_value, g2_value):
            continue
        if _set_path(project, path, g2_value):
            applied += 1

    analysis.applied = applied
    analysis.result_fingerprint = fingerprint_studio_project(project)
    document.metadata["legacy_merge_last_report"] = analysis.to_dict()

    # Somente avançamos a BASE quando não restou conflito. Em merge parcial a
    # BASE original é mantida para que uma próxima tentativa continue sabendo
    # quais campos ainda precisam de decisão humana.
    if not analysis.conflicts:
        document.metadata["legacy_source_fingerprint"] = analysis.result_fingerprint
        document.metadata[LEGACY_SOURCE_SNAPSHOT_KEY] = copy.deepcopy(project.to_dict())
        document.metadata["legacy_last_sync_fingerprint"] = analysis.result_fingerprint
    return analysis


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
        if product is None or parts[2] not in _PRODUCT_FIELDS or value is _MISSING:
            return False
        setattr(product, parts[2], value)
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


def _normalize(value: Any) -> Any:
    if hasattr(value, "as_tuple") and value.__class__.__name__ == "Decimal":
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
