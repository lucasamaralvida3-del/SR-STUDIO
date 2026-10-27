"""Render real editable slots for human review; never certifies visual fidelity.

Optional --product-image is a local approved photograph and is not committed.
Without it the picture/name explicitly identify a synthetic QA specimen.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--product-image", type=Path)
    parser.add_argument("--product-name", default="PRODUTO DE TESTE 500G")
    parser.add_argument("--qml", action="store_true")
    args = parser.parse_args()
    os.environ.setdefault("QT_QPA_PLATFORM", "windows" if os.name == "nt" else "offscreen")
    # Keep QA autosaves inside the output folder, away from real projects.
    os.environ["SR_STUDIO_G2_AUTOSAVE_ROOT"] = str(args.output.resolve() / "qa-autosave")
    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QFontDatabase, QGuiApplication
    app = QGuiApplication.instance() or QGuiApplication([])
    if os.name == "nt":
        assert "Impact" in QFontDatabase.families(), "Native Windows fonts are required for visual review"
    args.output.mkdir(parents=True, exist_ok=True)
    from srstudio.graphics2.slot_preview import _sample_image
    photo = args.product_image.resolve() if args.product_image else _sample_image(args.output / "qa-product.png")
    from srstudio.graphics2.model import GraphicsDocument
    from srstudio.graphics2.operations import GraphicsSession
    from srstudio.graphics2.item_slot_host import ItemSlotCommandRouter, launch_qt_quick_editor
    from srstudio.graphics2.item_slots import bind_product_to_item_slot
    from srstudio.graphics2.slot_limpeza_blue import bind_product_to_limpeza_blue_slot
    from srstudio.graphics2.campaign_tools import apply_campaign_preset
    from srstudio.graphics2.builtin_campaign_catalog import builtin_campaign_assets
    from srstudio.graphics2.multi_item_strip import create_multi_item_strip
    from srstudio.graphics2.qt_renderer import render_png, render_pdf
    from srstudio.graphics2.package import save_package
    s = GraphicsSession(GraphicsDocument(name="Beta57 QA — source constructors"))
    backgrounds = [a for a in builtin_campaign_assets() if a["kind"] == "background"]
    background = next(a for a in backgrounds if a["campaign_id"] == "quarta-cafe")
    apply_campaign_preset(s, background["id"])
    r = ItemSlotCommandRouter(s)
    for preset, x, y in [("limpeza-blue-v1", 30, 400), ("individual-beta44", 570, 340)]:
        added = r.dispatch({"name": "add_item_slot", "preset_id": preset, "x": x, "y": y})
        assert added.ok, added.message
        sid = added.payload["slot_id"]
        p = {"id": sid, "name": args.product_name, "price": "35,90", "promotion_price": "32,86",
             "club_price": "31,99", "unit": "UN", "image_path": str(photo)}
        binder = bind_product_to_limpeza_blue_slot if preset == "limpeza-blue-v1" else bind_product_to_item_slot
        assert binder(s, sid, p)
    for count, y in [(5, 870), (6, 1110)]:
        strip = create_multi_item_strip(s, count=count, y=y)
        for sid, value in zip(strip["slot_ids"], ["31,99", "3,99", "131,99", "31,99", "31,99", "31,99"]):
            assert bind_product_to_item_slot(s, sid, {
                "id": sid, "name": args.product_name, "price": "35,90", "promotion_price": "32,86",
                "club_price": value, "unit": "UN", "image_path": str(photo)})
    # Exercise the actual payload migration before rendering and persistence.
    r.payload()
    save_package(s.document, args.output / "slots.srscene")
    png = render_png(s.document, args.output / "slots.png", target_width=1600)
    pdf = render_pdf(s.document, args.output / "slots.pdf")
    assert png.ok and pdf.ok
    report = {"png_warnings": [w.code for w in png.warnings],
              "pdf_warnings": [w.code for w in pdf.warnings],
              "font": "Impact", "visual_review": "pending", "slot_count": len(s.page.slots)}
    (args.output / "render-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    if args.qml:
        captured = []
        def capture():
            window = next(w for w in app.topLevelWindows() if hasattr(w, "grabWindow"))
            window.setProperty("zoom", .45)
            def grab():
                image = window.grabWindow()
                captured.append(not image.isNull() and image.save(str(args.output / "editor.png")))
                app.quit()
            QTimer.singleShot(1500, grab)
        QTimer.singleShot(1500, capture)
        launch_qt_quick_editor(s.document, graphics_api="software")
        assert captured == [True], "Actual QML window capture failed"


if __name__ == "__main__":
    main()
