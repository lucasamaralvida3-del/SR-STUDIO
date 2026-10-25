from __future__ import annotations

"""Pixel-faithful Qt previews built from the actual Smart Slot constructors.

No manually recreated QML rectangles or price labels. Each thumbnail is a
cropped/full rendering of a scene made from the same editable components that
the user inserts. The launcher never needs PPTX files for these previews.
"""

from pathlib import Path
from tempfile import mkdtemp


PREVIEW_TYPES = ("blue", "individual", "multi5", "multi6",
                 "layout-individual", "layout-six", "layout-seven", "layout-eleven")


def _sample_product(path: Path, index: int) -> dict:
    return {
        "id": f"preview-{index}",
        "name": ("SHAMPOO 400ML", "DETERGENTE 500ML", "ARROZ BRANCO 5KG",
                 "AMACIANTE 1L", "CAFE EXTRA FORTE", "SABAO EM PO 1KG")[index % 6],
        "price": f"{index + 7},99",
        "unit": "UN",
        "image_path": str(path),
    }


def _sample_image(destination: Path) -> Path:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QImage, QPainter, QBrush, QPen

    img = QImage(130, 180, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    painter = QPainter(img)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(QColor("#3978AC")))
    painter.drawRoundedRect(36, 22, 58, 147, 15, 15)
    painter.setBrush(QBrush(QColor("#1E527F")))
    painter.drawRoundedRect(45, 8, 40, 24, 5, 5)
    painter.setBrush(QBrush(QColor("#FFFFFF")))
    painter.drawRoundedRect(40, 78, 50, 58, 5, 5)
    painter.setPen(QPen(QColor("#105594"), 3))
    painter.drawLine(47, 102, 82, 102)
    painter.drawLine(47, 111, 75, 111)
    painter.end()
    if not img.save(str(destination)):
        raise RuntimeError("Could not draw the product example for previews")
    return destination


def build_slot_preview_catalog(directory: str | Path | None = None) -> dict[str, str]:
    """Return file URLs for real rendered slots and real composed flyers.

    Call only after QGuiApplication exists (Qt Quick launcher guarantees it).
    Output files stay on disk while the QML window is open.
    """
    from PySide6.QtCore import QUrl, Qt
    from PySide6.QtGui import QGuiApplication, QImage

    from .item_slots import bind_product_to_item_slot, create_item_slot
    from .slot_limpeza_blue import create_limpeza_blue_slot, bind_product_to_limpeza_blue_slot
    from .multi_item_strip import create_multi_item_strip
    from .promotion_composition import apply_slot_composition
    from .promotion_layouts import plan_promotion
    from .model import GraphicsDocument
    from .operations import GraphicsSession
    from .qt_renderer import render_png

    if QGuiApplication.instance() is None:
        raise RuntimeError("Qt previews need QGuiApplication")

    root = Path(directory) if directory is not None else Path(mkdtemp(prefix="sr-g2-slot-previews-"))
    root.mkdir(parents=True, exist_ok=True)
    sample = _sample_image(root / "example-product.png")
    output: dict[str, str] = {}

    for kind in PREVIEW_TYPES:
        doc = GraphicsDocument(name="Preview " + kind)
        session = GraphicsSession(doc)
        page = session.page
        # Keep every preview self-contained and free from the real document.
        if kind in ("blue", "individual"):
            if kind == "blue":
                slot = create_limpeza_blue_slot(session, x=0, y=0)
                bind_product_to_limpeza_blue_slot(session, slot.id, _sample_product(sample, 0))
            else:
                slot = create_item_slot(session, "individual-beta44", x=0, y=0)
                bind_product_to_item_slot(session, slot.id, _sample_product(sample, 0))
            rendered_root = page.node(slot.metadata["root_node_id"])
        elif kind.startswith("multi"):
            count = int(kind[-1])
            result = create_multi_item_strip(session, count=count, x=0, y=0)
            for index, sid in enumerate(result["slot_ids"]):
                bind_product_to_item_slot(session, sid, _sample_product(sample, index))
            rendered_root = page.node(result["root_node_id"])
        else:
            mode = kind.split("-", 1)[1]
            result = apply_slot_composition(session, plan_promotion(mode),
                                             reuse_existing=False)
            for index, sid in enumerate(result.slot_ids):
                bind_product_to_item_slot(session, sid, _sample_product(sample, index))
            rendered_root = None

        full = root / ("render-" + kind + ".png")
        report = render_png(doc, full, page_index=doc.pages.index(page),
                            target_width=730)
        raw = QImage(str(report.output))
        if raw.isNull():
            raise RuntimeError(f"Missing Qt preview for {kind}")
        if rendered_root is not None:
            rect = rendered_root.rect.normalized()
            factor = report.width / page.width
            # Same rectangular crop as the actual slot's persisted root.
            x, y = max(0, round(rect.x * factor)), max(0, round(rect.y * factor))
            w, h = max(1, round(rect.width * factor)), max(1, round(rect.height * factor))
            raw = raw.copy(x, y, w, h)
        max_width = 320 if kind.startswith("layout-") else 500
        if raw.width() > max_width:
            raw = raw.scaledToWidth(max_width, Qt.SmoothTransformation)
        output_path = root / (kind + ".png")
        if not raw.save(str(output_path)):
            raise RuntimeError(f"Cannot save Qt preview for {kind}")
        output[kind] = QUrl.fromLocalFile(str(output_path.resolve())).toString()
    return output
