from __future__ import annotations

"""Conservative non-mutating checks for canonical Smart Slot flyers.

Only product fields and the roots of a recorded composition are inspected;
price backgrounds, promotional badges and source art intentionally overlap.
Do not turn those legitimate design relationships into false alarms.
"""

from pathlib import Path

from .model import BindingRole, NodeKind
from .preflight import PreflightIssue


def _shown(page, node) -> bool:
    while node is not None:
        if not node.visible:
            return False
        node = page.node(node.parent_id) if node.parent_id else None
    return True


def _collision(a, b, *, margin=0.5) -> bool:
    return (a.x < b.right - margin and b.x < a.right - margin
            and a.y < b.bottom - margin and b.y < a.bottom - margin)


def inspect_smart_slot_flyer(document, *, page_ids: set[str] | None = None) -> list[PreflightIssue]:
    """Warn about actual product issues without modifying any design nodes."""
    issues: list[PreflightIssue] = []
    for page in document.pages:
        if page_ids is not None and page.id not in page_ids:
            continue
        composition = page.metadata.get("promotion_composition") or {}
        roots = [
            page.node(str(node_id))
            for node_id in composition.get("root_node_ids", ())
        ]
        roots = [root for root in roots if root is not None and _shown(page, root)]
        for i, root in enumerate(roots):
            rect = root.rect.normalized()
            if (rect.x < -0.5 or rect.y < -0.5
                    or rect.right > page.width + .5
                    or rect.bottom > page.height + .5):
                issues.append(PreflightIssue(
                    "warning", "SLOT_OUT_OF_PAGE",
                    "Um Smart Slot do layout está fora da página.", page.id, root.id))
            if any(_collision(rect, other.rect.normalized()) for other in roots[i + 1:]):
                issues.append(PreflightIssue(
                    "warning", "SLOT_LAYOUT_OVERLAP",
                    "Dois Smart Slots do layout estão sobrepostos.", page.id, root.id))

        for slot in page.slots.values():
            if (not slot.product_id or slot.metadata.get("preset_id") not in (
                "individual-beta44", "multi-cell-beta44", "limpeza-blue-v1",
            )):
                continue
            root = page.node(str(slot.metadata.get("root_node_id") or ""))
            if root is None or not _shown(page, root):
                continue
            image = page.node(str(slot.node_by_role.get(BindingRole.IMAGE.value) or ""))
            if image is None or not _shown(page, image):
                issues.append(PreflightIssue(
                    "warning", "SLOT_IMAGE_MISSING",
                    "Produto vinculado sem imagem visível.", page.id,
                    image.id if image else root.id))
            else:
                source = image.metadata.get("bound_image_source")
                if not source and image.asset_id in document.assets:
                    source = document.assets[image.asset_id].source
                if not source or (not str(source).startswith(("http:", "https:"))
                                  and not Path(str(source)).is_file()):
                    issues.append(PreflightIssue(
                        "warning", "SLOT_IMAGE_MISSING",
                        "Produto vinculado sem arquivo de imagem disponível.", page.id, image.id))
                if str(image.style.get("fit") or "contain").lower() == "fill":
                    issues.append(PreflightIssue(
                        "warning", "SLOT_IMAGE_DISTORTION",
                        "A imagem do produto está configurada para esticar.", page.id, image.id))

            name = page.node(str(slot.node_by_role.get(BindingRole.NAME.value) or ""))
            price = page.node(str((slot.metadata.get("role_area_nodes") or {}).get("price") or ""))
            if name is not None and price is not None and _shown(page, name):
                if _collision(name.rect.normalized(), price.rect.normalized(), margin=0.5):
                    issues.append(PreflightIssue(
                        "warning", "SLOT_NAME_PRICE_OVERLAP",
                        "Descrição do produto invade a área do preço.", page.id, name.id))
            for role in (BindingRole.NAME, BindingRole.PRICE_REAIS, BindingRole.PRICE_CENTS):
                value = page.node(str(slot.node_by_role.get(role.value) or ""))
                if value is None or not value.text.strip():
                    issues.append(PreflightIssue(
                        "warning", "SLOT_PRICE_EMPTY" if role != BindingRole.NAME else "SLOT_NAME_EMPTY",
                        "Produto vinculado sem descrição ou preço completo.", page.id,
                        value.id if value is not None else root.id))
                elif _text_exceeds_minimum_fit(value):
                    issues.append(PreflightIssue(
                        "warning", "SLOT_TEXT_CLIPPED",
                        "Texto do produto pode ser cortado mesmo na fonte mínima.", page.id,
                        value.id))
    return issues


def _text_exceeds_minimum_fit(node) -> bool:
    """Measure using Qt only when a GUI font database is available.

    Prevents false alarms based on character count; no rendering or
    modification is performed. Imported/custom nodes are not touched.
    """
    try:
        from PySide6.QtCore import QRectF, Qt
        from PySide6.QtGui import QFont, QFontMetricsF, QGuiApplication
    except ImportError:
        return False
    if QGuiApplication.instance() is None:
        return False
    style = node.style
    if not style.get("fit_inside_box"):
        return False
    bounds = node.rect.normalized()
    if min(bounds.width, bounds.height) <= 0:
        return True
    font = QFont(str(style.get("font_family") or "Segoe UI"))
    font.setPixelSize(max(3, round(float(style.get("min_font_size") or 4))))
    flags = Qt.AlignHCenter | Qt.AlignVCenter
    if not style.get("nowrap"):
        flags |= Qt.TextWordWrap
    extent = QFontMetricsF(font).boundingRect(
        QRectF(0, 0, bounds.width, bounds.height), flags, str(node.text))
    return extent.width() > bounds.width + 1 or extent.height() > bounds.height + 1
