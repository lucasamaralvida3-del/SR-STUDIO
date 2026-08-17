from __future__ import annotations

"""Orquestração final da recuperação semântica Canva.

A primeira passagem em ``semantic_placeholders`` pode promover PriceBlocks
órfãos a Smart Slots usando o backplate branco. Como esses novos slots nascem
durante a própria varredura, esta segunda etapa finaliza de forma explícita o
binding IMAGE no mesmo placeholder. Mantê-la separada torna as duas fases
idempotentes e evita mutação recursiva do dicionário de slots.
"""

from .model import BindingRole, GraphicsDocument, NodeKind
from .semantic_placeholders import (
    PlaceholderRecoveryReport,
    _attach_to_semantic_card,
    _ensure_synthetic_image_node,
    _image_box,
    _price_rect,
    recover_canva_image_placeholders,
)


def recover_canva_semantic_cards(document: GraphicsDocument) -> PlaceholderRecoveryReport:
    """Executa recuperação de card + placeholder + IMAGE até estado completo."""

    report = recover_canva_image_placeholders(document)
    for page in document.pages:
        for slot in list(page.slots.values()):
            if slot.node_by_role.get(BindingRole.IMAGE.value):
                continue
            placeholder_id = str(slot.metadata.get("recovered_image_placeholder_id") or "")
            if not placeholder_id:
                continue
            placeholder = page.node(placeholder_id)
            if placeholder is None or placeholder.kind not in {NodeKind.RECT, NodeKind.PATH}:
                report.warnings.append(
                    f"Smart Slot {slot.id}: placeholder recuperado não existe mais ({placeholder_id})."
                )
                continue
            price_rect = _price_rect(page, slot)
            if price_rect is None:
                report.warnings.append(f"Smart Slot {slot.id}: PriceBlock sem geometria para IMAGE sintética.")
                continue
            image_rect = _image_box(page, placeholder.rect.normalized(), price_rect)
            if image_rect is None:
                report.warnings.append(f"Smart Slot {slot.id}: placeholder não possui área útil de imagem.")
                continue
            synthetic = _ensure_synthetic_image_node(page, slot.id, placeholder, image_rect, price_rect)
            slot.node_by_role[BindingRole.IMAGE.value] = synthetic.id
            slot.metadata["synthetic_image_node_id"] = synthetic.id
            slot.metadata["synthetic_image_slot"] = True
            _attach_to_semantic_card(page, slot, placeholder, synthetic)
            report.placeholders_matched += 1
            report.synthetic_image_slots += 1

    document.metadata["semantic_image_placeholders"] = report.to_dict()
    document.metadata["semantic_recovery_complete"] = {
        "ready": not report.warnings,
        "pages": report.pages_scanned,
        "slots": sum(len(page.slots) for page in document.pages),
        "orphan_cards_promoted": report.orphan_cards_promoted,
        "synthetic_image_slots": report.synthetic_image_slots,
        "warnings": list(report.warnings),
    }
    return report
