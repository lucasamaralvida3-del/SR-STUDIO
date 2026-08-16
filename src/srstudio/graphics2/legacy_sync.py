from __future__ import annotations

"""Sincronização seletiva SR Scene 2 -> StudioProject legado.

O modelo Graphics Engine 2 é mais rico que o StudioProject 5.x. Este módulo
portanto nunca tenta fazer uma conversão destrutiva de toda a cena. Somente
campos que possuem representação equivalente no modelo legado são projetados de
volta: produtos, geometria dos ProductCards, propriedades básicas de página e
ordem de páginas já existentes.

A sincronização é protegida por fingerprint do projeto que originou a sessão.
Se o Studio legado mudou depois da abertura do Engine 2, o sync recusa a escrita
por padrão para não sobrescrever alterações mais novas.
"""

from dataclasses import asdict, dataclass, field
from decimal import Decimal
from hashlib import sha256
from typing import Any
import copy
import json

from srstudio.core.models import Product, StudioProject, to_decimal

from .model import BindingRole, GraphicsDocument, GraphicsNode, NodeKind

LEGACY_SOURCE_FINGERPRINT_KEY = "legacy_source_fingerprint"
LEGACY_LAST_SYNC_FINGERPRINT_KEY = "legacy_last_sync_fingerprint"
LEGACY_SYNC_SCHEMA = "srstudio/graphics2-legacy-sync-1"


@dataclass(slots=True)
class LegacySyncReport:
    ok: bool
    conflict: bool = False
    source_fingerprint: str = ""
    current_fingerprint: str = ""
    result_fingerprint: str = ""
    products_updated: int = 0
    products_added: int = 0
    cards_updated: int = 0
    pages_updated: int = 0
    pages_reordered: bool = False
    warnings: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    @property
    def changes(self) -> int:
        return self.products_updated + self.products_added + self.cards_updated + self.pages_updated

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["schema"] = LEGACY_SYNC_SCHEMA
        payload["changes"] = self.changes
        return payload


def fingerprint_studio_project(project: StudioProject) -> str:
    """Fingerprint determinístico do estado editável relevante do Studio 5.

    Metadados transitórios de renderização são removidos para que progresso de
    staging/cache não crie falsos conflitos enquanto o usuário edita a arte.
    """

    payload = project.to_dict()
    payload = _strip_volatile(copy.deepcopy(payload))
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(raw.encode("utf-8")).hexdigest()


def sync_graphics_to_studio(
    document: GraphicsDocument,
    project: StudioProject,
    *,
    allow_conflict: bool = False,
) -> LegacySyncReport:
    """Projeta alterações representáveis do SR Scene de volta ao StudioProject.

    Recursos sem equivalente no legado (vetores arbitrários, máscaras, efeitos,
    nós livres, fontes embutidas etc.) permanecem exclusivamente no `.srscene`.
    """

    metadata = dict(document.metadata or {})
    expected_project_id = str(metadata.get("legacy_project_id") or "")
    if expected_project_id and expected_project_id != str(project.id):
        return LegacySyncReport(
            ok=False,
            conflict=True,
            warnings=["A sessão Graphics Engine 2 pertence a outro projeto do Studio."],
        )

    source_fingerprint = str(metadata.get(LEGACY_SOURCE_FINGERPRINT_KEY) or "")
    current_fingerprint = fingerprint_studio_project(project)
    if source_fingerprint and current_fingerprint != source_fingerprint and not allow_conflict:
        return LegacySyncReport(
            ok=False,
            conflict=True,
            source_fingerprint=source_fingerprint,
            current_fingerprint=current_fingerprint,
            warnings=[
                "O projeto do Studio mudou depois que esta sessão do Engine 2 foi criada. "
                "A sincronização foi bloqueada para evitar sobrescrever alterações mais novas."
            ],
        )

    report = LegacySyncReport(
        ok=True,
        source_fingerprint=source_fingerprint,
        current_fingerprint=current_fingerprint,
    )
    product_index = {product.id: product for product in project.products}
    product_payload_index = _document_product_payloads(document)

    page_by_id = {page.id: page for page in project.pages}
    graphics_page_ids = [page.id for page in document.pages]
    legacy_page_ids = [page.id for page in project.pages]

    for graphics_page in document.pages:
        legacy_page = page_by_id.get(graphics_page.id)
        if legacy_page is None:
            report.skipped.append(
                f"Página '{graphics_page.name}' existe apenas no Engine 2 e foi preservada somente no .srscene."
            )
            continue

        page_changed = False
        if legacy_page.name != graphics_page.name:
            legacy_page.name = graphics_page.name
            page_changed = True
        if float(legacy_page.width) != float(graphics_page.width):
            legacy_page.width = float(graphics_page.width)
            page_changed = True
        if float(legacy_page.height) != float(graphics_page.height):
            legacy_page.height = float(graphics_page.height)
            page_changed = True
        if legacy_page.background != graphics_page.background:
            legacy_page.background = graphics_page.background
            page_changed = True
        if page_changed:
            report.pages_updated += 1

        for slot in graphics_page.slots.values():
            product_id = str(slot.product_id or slot.metadata.get("product_id") or "")
            if not product_id:
                snapshot = slot.metadata.get("product_snapshot")
                if isinstance(snapshot, dict):
                    product_id = str(snapshot.get("id") or "")
            if not product_id:
                continue

            product = product_index.get(product_id)
            if product is None:
                payload = product_payload_index.get(product_id)
                if payload is None and isinstance(slot.metadata.get("product_snapshot"), dict):
                    payload = dict(slot.metadata["product_snapshot"])
                if payload is None:
                    report.skipped.append(f"Produto {product_id} não existe no Studio e não possui snapshot recuperável.")
                    continue
                try:
                    product = Product.from_dict(_product_constructor_payload(payload, product_id))
                except Exception as exc:
                    report.warnings.append(f"Não foi possível recriar o produto {product_id}: {exc}")
                    continue
                project.products.append(product)
                product_index[product.id] = product
                report.products_added += 1

            if _sync_product_from_slot(document, graphics_page, slot.node_by_role, product):
                report.products_updated += 1

        for legacy_card in legacy_page.cards:
            node = graphics_page.nodes.get(legacy_card.id)
            if node is None or node.kind is not NodeKind.GROUP:
                continue
            legacy_product_id = str(node.metadata.get("legacy_product_id") or "")
            if legacy_product_id and legacy_product_id != legacy_card.product_id:
                report.warnings.append(
                    f"Card {legacy_card.id} não foi sincronizado: vínculo de produto divergiu no Engine 2."
                )
                continue
            transform = node.transform
            before = (
                legacy_card.x,
                legacy_card.y,
                legacy_card.width,
                legacy_card.height,
                legacy_card.rotation,
                legacy_card.locked,
                legacy_card.z_index,
            )
            after = (
                float(transform.x),
                float(transform.y),
                float(transform.width),
                float(transform.height),
                float(transform.rotation),
                bool(node.locked),
                int(node.z_index),
            )
            if before != after:
                (
                    legacy_card.x,
                    legacy_card.y,
                    legacy_card.width,
                    legacy_card.height,
                    legacy_card.rotation,
                    legacy_card.locked,
                    legacy_card.z_index,
                ) = after
                report.cards_updated += 1

    if len(graphics_page_ids) == len(legacy_page_ids) and set(graphics_page_ids) == set(legacy_page_ids):
        if graphics_page_ids != legacy_page_ids:
            by_id = {page.id: page for page in project.pages}
            project.pages[:] = [by_id[page_id] for page_id in graphics_page_ids]
            report.pages_reordered = True
    else:
        report.skipped.append(
            "A ordem de páginas não foi projetada ao Studio porque o Engine 2 possui páginas sem equivalente legado."
        )

    result_fingerprint = fingerprint_studio_project(project)
    report.result_fingerprint = result_fingerprint
    document.metadata[LEGACY_SOURCE_FINGERPRINT_KEY] = result_fingerprint
    document.metadata[LEGACY_LAST_SYNC_FINGERPRINT_KEY] = result_fingerprint
    document.metadata["legacy_sync_last_report"] = report.to_dict()
    return report


def _sync_product_from_slot(document, page, node_by_role: dict[str, str], product: Product) -> bool:
    changed = False

    name = _role_text(page, node_by_role, BindingRole.NAME)
    if name is not None and product.display_name != name:
        product.display_name = name
        changed = True

    whole = _role_text(page, node_by_role, BindingRole.PRICE_REAIS)
    cents = _role_text(page, node_by_role, BindingRole.PRICE_CENTS)
    if whole is not None or cents is not None:
        amount = _combined_price(whole or "", cents or "")
        if amount is not None and product.price != amount:
            product.price = amount
            changed = True

    unit = _role_text(page, node_by_role, BindingRole.UNIT)
    if unit is not None:
        normalized_unit = unit.strip().upper().lstrip("/") or "UN"
        if product.unit != normalized_unit:
            product.unit = normalized_unit
            changed = True

    limit = _role_text(page, node_by_role, BindingRole.LIMIT)
    if limit is not None and product.cpf_limit != limit:
        product.cpf_limit = limit
        changed = True

    quantity = _role_text(page, node_by_role, BindingRole.QUANTITY)
    if quantity is not None and product.quantity != quantity:
        product.quantity = quantity
        changed = True

    validity = _role_text(page, node_by_role, BindingRole.VALIDITY)
    if validity is not None and product.validity != validity:
        product.validity = validity
        changed = True

    for role, attr in (
        (BindingRole.APP_PRICE, "app_price"),
        (BindingRole.WHOLESALE_PRICE, "wholesale_price"),
        (BindingRole.RETAIL_PRICE, "retail_price"),
    ):
        text = _role_text(page, node_by_role, role)
        if text is None:
            continue
        amount = to_decimal(text)
        if amount is not None and getattr(product, attr) != amount:
            setattr(product, attr, amount)
            changed = True

    image_node = _role_node(page, node_by_role, BindingRole.IMAGE)
    if image_node is not None:
        source = _image_source(document, image_node)
        if source and product.image_path != source:
            product.image_path = source
            changed = True

    return changed


def _role_node(page, node_by_role: dict[str, str], role: BindingRole) -> GraphicsNode | None:
    node_id = str(node_by_role.get(role.value) or "")
    return page.nodes.get(node_id) if node_id else None


def _role_text(page, node_by_role: dict[str, str], role: BindingRole) -> str | None:
    node = _role_node(page, node_by_role, role)
    if node is None or node.kind is not NodeKind.TEXT:
        return None
    return str(node.text or "").strip()


def _image_source(document: GraphicsDocument, node: GraphicsNode) -> str:
    metadata = node.metadata or {}
    for key in ("graphics2_preview_original_source", "bound_image_source", "source_url"):
        value = str(metadata.get(key) or "").strip()
        if value and not value.startswith("image://srscene/"):
            return value
    if node.asset_id:
        asset = document.assets.get(node.asset_id)
        if asset is not None:
            return str(asset.source or "").strip()
    return ""


def _combined_price(whole: str, cents: str) -> Decimal | None:
    whole_text = str(whole or "").strip().replace("R$", "").replace(" ", "")
    cents_text = str(cents or "").strip().replace("R$", "").replace(" ", "")
    if not whole_text and not cents_text:
        return None
    if cents_text:
        cents_digits = "".join(char for char in cents_text if char.isdigit())
        if cents_digits:
            cents_digits = cents_digits[-2:].rjust(2, "0")
            return to_decimal(f"{whole_text or '0'},{cents_digits}")
    return to_decimal(whole_text)


def _document_product_payloads(document: GraphicsDocument) -> dict[str, dict[str, Any]]:
    raw = document.metadata.get("products") if isinstance(document.metadata, dict) else None
    if not isinstance(raw, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        product_id = str(item.get("id") or "")
        if product_id:
            result[product_id] = dict(item)
    return result


def _product_constructor_payload(payload: dict[str, Any], product_id: str) -> dict[str, Any]:
    allowed = {
        "id",
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
        "source",
        "recognition_confidence",
        "metadata",
    }
    result = {key: value for key, value in payload.items() if key in allowed}
    result["id"] = product_id
    return result


def _strip_volatile(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text.startswith("render_") or key_text in {"last_rendered_at", "preview_cache_key"}:
                continue
            cleaned[key_text] = _strip_volatile(item)
        return cleaned
    if isinstance(value, list):
        return [_strip_volatile(item) for item in value]
    return value
