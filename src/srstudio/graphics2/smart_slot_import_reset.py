from __future__ import annotations

"""Reset lógico de conteúdo de produto para NOVA importação Canva/PPTX.

A geometria visual importada é fonte de verdade e nunca é apagada por este
módulo. O reset atua somente na associação de produto do Smart Slot.

Abrir ``.srscene``/``.zip`` salvo não passa por este módulo.
"""

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from srstudio.core.models import StudioProject

from .model import GraphicsDocument, NodeKind, SmartSlot


_PRODUCT_VALUE_METADATA_KEYS = {
    "bound_product_id",
    "bound_product_code",
    "bound_product_ean",
    "bound_product_name",
    "bound_description",
    "bound_price",
    "bound_quantity",
    "bound_retail_price",
    "bound_wholesale_price",
    "bound_unit",
    "bound_validity",
    "last_bound_product_id",
}


@dataclass(slots=True)
class SmartSlotImportResetReport:
    source: str = ""
    mode: str = "new-pptx-import"
    pages: int = 0
    slots_reset: int = 0
    structural_role_links_preserved: int = 0
    imported_products_discarded: int = 0
    legacy_cards_reset: int = 0
    image_binding_markers_cleared: int = 0
    synthetic_images_emptied: int = 0
    source_text_mutations: int = 0
    source_geometry_mutations: int = 0
    source_nodes_deleted: int = 0
    slot_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def reset_new_pptx_import_product_content(
    document: GraphicsDocument,
    legacy_project: StudioProject,
    *,
    source: str | Path,
) -> SmartSlotImportResetReport:
    """Preserva Smart Slot STRUCTURE e zera PRODUCT CONTENT em import novo.

    Fonte canônica de conteúdo:
    - ``slot.product_id == ""``;
    - ``slot.metadata["product_snapshot"] == {}``.

    Contrato:
    - ``slot.id``, ``node_by_role``, ``extra_bindings``, bounds e nodes ficam;
    - conteúdo visual original do PPTX (texto/imagem/geometria) não é apagado;
    - imagem sintética criada apenas para auto-preenchimento volta a ficar vazia;
    - a lista de produtos inferidos do PPTX não vira conteúdo ativo do projeto G2.
    """

    report = SmartSlotImportResetReport(source=str(Path(source)))
    report.pages = len(document.pages)

    imported_products = list(document.metadata.get("products") or [])
    report.imported_products_discarded = len(imported_products)
    document.metadata["products"] = []

    for page in document.pages:
        for slot in page.slots.values():
            _reset_slot_product_state(page, slot, report)

    # O ImageLibrary já teve a oportunidade de aprender durante o pipeline;
    # agora removemos somente o conteúdo ativo do projeto intermediário.
    legacy_project.products.clear()
    for page in legacy_project.pages:
        for card in page.cards:
            card.product_id = ""
            card.overrides.pop("slot_template_product_id", None)
            card.overrides["slot_filled"] = False
            report.legacy_cards_reset += 1

    payload = report.to_dict()
    document.metadata["smart_slot_import_reset"] = payload
    document.metadata["smart_slot_import_started_empty"] = True
    document.metadata["smart_slot_import_reset_version"] = 1
    return report


def _reset_slot_product_state(page, slot: SmartSlot, report: SmartSlotImportResetReport) -> None:
    # Estrutura é capturada apenas para diagnóstico; não é reescrita.
    structural_ids = _slot_node_ids(slot)
    report.structural_role_links_preserved += len(structural_ids)
    report.slot_ids.append(slot.id)

    slot.product_id = ""
    slot.metadata["product_snapshot"] = {}
    for key in _PRODUCT_VALUE_METADATA_KEYS:
        slot.metadata.pop(key, None)

    for node_id in structural_ids:
        node = page.node(node_id)
        if node is None:
            continue

        if node.kind is not NodeKind.IMAGE:
            # Texto original é parte do layout visual importado. Não limpar
            # ``node.text`` aqui é requisito explícito: o binding fica vazio,
            # mas o PPTX continua visualmente idêntico ao arquivo fonte.
            continue

        if "bound_image_source" in node.metadata:
            # O asset original importado continua referenciado por ``asset_id``;
            # só o override de produto é removido.
            node.metadata.pop("bound_image_source", None)
            report.image_binding_markers_cleared += 1

        if _is_synthetic_product_image(node):
            # Placeholder sintético não pertence ao visual original. Se o banco
            # o auto-preencheu durante a análise, ele inicia vazio até escolha do usuário.
            node.visible = False
            report.synthetic_images_emptied += 1

    report.slots_reset += 1


def _slot_node_ids(slot: SmartSlot) -> list[str]:
    result: list[str] = []
    for node_id in slot.node_by_role.values():
        value = str(node_id or "")
        if value and value not in result:
            result.append(value)
    extras = slot.metadata.get("extra_bindings")
    if isinstance(extras, dict):
        for raw in extras.values():
            values = raw if isinstance(raw, (list, tuple, set)) else [raw]
            for node_id in values:
                value = str(node_id or "")
                if value and value not in result:
                    result.append(value)
    return result


def _is_synthetic_product_image(node) -> bool:
    metadata = node.metadata or {}
    if bool(metadata.get("semantic_synthetic_image_slot")):
        return True
    if str(metadata.get("source") or "") == "semantic-placeholder-recovery":
        return True
    source_name = str(metadata.get("source_name") or node.name or "").strip().casefold()
    if source_name == "sr smart image slot" and bool(metadata.get("template_hidden", False)):
        return True
    return False
