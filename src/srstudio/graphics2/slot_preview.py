from __future__ import annotations

"""Pixel-faithful Qt previews built from the actual Smart Slot constructors.

No manually recreated QML rectangles or price labels. Each thumbnail is a
cropped/full rendering of a scene made from the same editable components that
the user inserts. The launcher never needs PPTX files for these previews.
"""

from hashlib import sha256
from pathlib import Path
from tempfile import gettempdir


PREVIEW_TYPES = ("blue", "individual", "individual-two", "multi5", "multi5-two",
                 "multi6", "multi6-two", "layout-individual", "layout-six",
                 "layout-seven", "layout-eleven")


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

    # Native Windows Qt provides the real font database; offscreen mode may
    # report no installed families. The visual CI renders on the native platform.
    # The same eleven heavy Qt renderings used to run on every launch.
    # Cache by the actual renderer/preset source and font availability so
    # changed slots invalidate naturally, with no stale fake thumbnails.
    if directory is None:
        from PySide6.QtGui import QFontDatabase
        sources = ("slot_preview.py", "item_slots.py", "slot_limpeza_blue.py",
                   "multi_item_strip.py", "promotion_composition.py",
                   "promotion_layouts.py", "qt_renderer.py")
        digest = sha256()
        import sys
        for name in sources:
            try:
                digest.update((Path(__file__).with_name(name)).read_bytes())
            except OSError:
                # Frozen PyInstaller executables do not expose the .py files.
                # Their executable changes on release; include its timestamp
                # and the preview builder's bytecode for cache invalidation.
                exe = Path(sys.executable)
                digest.update(str(exe.stat().st_mtime_ns).encode("ascii"))
                digest.update(build_slot_preview_catalog.__code__.co_code)
                break
        digest.update(str("Anton" in QFontDatabase.families()).encode("ascii"))
        root = Path(gettempdir()) / ("sr-g2-real-slot-preview-" + digest.hexdigest()[:16])
    else:
        # Qt render/export resolves local images strictly. Relative preview
        # directories broke thumbnails on Windows (IMAGE_NOT_LOCAL).
        root = Path(directory).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    output: dict[str, str] = {}
    for kind in PREVIEW_TYPES:
        cached = root / (kind + ".png")
        if cached.is_file() and cached.stat().st_size > 256:
            if not QImage(str(cached)).isNull():
                output[kind] = QUrl.fromLocalFile(str(cached.resolve())).toString()
    if len(output) == len(PREVIEW_TYPES):
        return output
    sample = _sample_image(root / "example-product.png")

    for kind in PREVIEW_TYPES:
        if kind in output:
            continue
        doc = GraphicsDocument(name="Preview " + kind)
        session = GraphicsSession(doc)
        page = session.page
        # Keep every preview self-contained and free from the real document.
        two_prices = kind.endswith("-two")
        def product(index):
            item = _sample_product(sample, index)
            if two_prices:
                item["club_price"] = f"{index + 5},99"
            return item
        if kind in ("blue", "individual", "individual-two"):
            if kind == "blue":
                slot = create_limpeza_blue_slot(session, x=0, y=0)
                bind_product_to_limpeza_blue_slot(session, slot.id, product(0))
            else:
                slot = create_item_slot(session, "individual-beta44", x=0, y=0)
                slot.metadata["price_mode"] = "two" if two_prices else "one"
                bind_product_to_item_slot(session, slot.id, product(0))
            rendered_root = page.node(slot.metadata["root_node_id"])
        elif kind.startswith("multi"):
            count = int(kind[5])
            result = create_multi_item_strip(
                session, count=count, x=0, y=0,
                price_mode="two" if two_prices else "one",
            )
            for index, sid in enumerate(result["slot_ids"]):
                bind_product_to_item_slot(session, sid, product(index))
            rendered_root = page.node(result["root_node_id"])
        else:
            mode = kind.split("-", 1)[1]
            result = apply_slot_composition(session, plan_promotion(mode),
                                             reuse_existing=False)
            for index, sid in enumerate(result.slot_ids):
                bind_product_to_item_slot(session, sid, product(index))
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
