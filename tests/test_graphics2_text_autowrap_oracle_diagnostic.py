from __future__ import annotations

import os

import pytest


def _qt():
    pytest.importorskip("PySide6")
    if os.name != "nt":
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import QtCore, QtGui
    from PySide6.QtGui import QGuiApplication

    app = QGuiApplication.instance() or QGuiApplication(["g2-text-oracle-diagnostic"])
    return app, QtCore, QtGui


def _line_snapshot(QtCore, QtGui, *, text: str, width: float, font):
    layout = QtGui.QTextLayout(text, font)
    option = QtGui.QTextOption()
    option.setWrapMode(QtGui.QTextOption.WrapMode.WordWrap)
    layout.setTextOption(option)
    rows = []
    layout.beginLayout()
    try:
        while True:
            line = layout.createLine()
            if not line.isValid():
                break
            line.setLineWidth(width)
            start = int(line.textStart())
            length = int(line.textLength())
            line_text = text[start : start + length]
            rows.append(
                {
                    "text": line_text,
                    "start": start,
                    "length": length,
                    "natural": float(line.naturalTextWidth()),
                    "horizontal": float(line.horizontalAdvance()) if hasattr(line, "horizontalAdvance") else None,
                    "font_advance": float(QtGui.QFontMetricsF(font).horizontalAdvance(line_text)),
                }
            )
    finally:
        layout.endLayout()
    return rows


def test_center_alignment_metric_oracle_diagnostic():
    _, QtCore, QtGui = _qt()
    font = QtGui.QFont("Arial")
    font.setPixelSize(24)
    text = "ALHO A GRANEL"
    metrics = QtGui.QFontMetricsF(font)
    width = max(metrics.horizontalAdvance("ALHO A"), metrics.horizontalAdvance("GRANEL")) + 1.0
    box_left = 10.0
    rows = _line_snapshot(QtCore, QtGui, text=text, width=width, font=font)
    assert len(rows) == 2
    image = QtGui.QImage(400, 160, QtGui.QImage.Format_ARGB32_Premultiplied)
    image.fill(QtCore.Qt.transparent)
    painter = QtGui.QPainter(image)
    painter.setFont(font)
    painter.setPen(QtGui.QColor("black"))
    try:
        for idx, row in enumerate(rows):
            implementation_x = box_left + (width - row["natural"]) * 0.5
            fontmetrics_x = box_left + (width - row["font_advance"]) * 0.5
            baseline = 40.0 + idx * 31.25
            painter.drawText(QtCore.QPointF(implementation_x, baseline), row["text"])
            print(
                "G2_CENTER_DIAG",
                f"platform={os.name}",
                f"text={row['text']!r}",
                f"font={font.family()!r}",
                f"tracking_requested={0.0}",
                f"tracking_effective={font.letterSpacing()}",
                f"box_width={width}",
                f"naturalTextWidth={row['natural']}",
                f"fontMetricsAdvance={row['font_advance']}",
                f"horizontalAdvance={row['horizontal']}",
                f"start={row['start']}",
                f"length={row['length']}",
                f"implementation_x={implementation_x}",
                f"fontmetrics_expected_x={fontmetrics_x}",
                f"baseline={baseline}",
                "draw_primitive=QPainter.drawText(QPointF,str)",
            )
    finally:
        painter.end()


def test_tracking_effect_and_qfontinfo_diagnostic():
    _, QtCore, QtGui = _qt()
    text = "CREME DE AMENDOIM BOM PRINCÍPIO 250G"
    plain = QtGui.QFont("Arial")
    plain.setPixelSize(23)
    tracked = QtGui.QFont("Arial")
    tracked.setPixelSize(23)
    requested = -0.66
    tracked.setLetterSpacing(QtGui.QFont.AbsoluteSpacing, requested)
    width = QtGui.QFontMetricsF(plain).horizontalAdvance(text) * 0.58
    plain_rows = _line_snapshot(QtCore, QtGui, text=text, width=width, font=plain)
    tracked_rows = _line_snapshot(QtCore, QtGui, text=text, width=width, font=tracked)
    print(
        "G2_TRACKING_DIAG",
        f"platform={os.name}",
        f"requested={requested}",
        f"effective={tracked.letterSpacing()}",
        f"spacing_type={int(tracked.letterSpacingType())}",
        f"plain_natural={[r['natural'] for r in plain_rows]}",
        f"tracked_natural={[r['natural'] for r in tracked_rows]}",
        f"plain_lines={[r['text'] for r in plain_rows]!r}",
        f"tracked_lines={[r['text'] for r in tracked_rows]!r}",
    )
    assert tracked.letterSpacing() < 0
    assert [r["natural"] for r in tracked_rows] != [r["natural"] for r in plain_rows]
    for family in ("Anton", "High Cruiser"):
        requested_font = QtGui.QFont(family)
        info = QtGui.QFontInfo(requested_font)
        exact = info.exactMatch() if hasattr(info, "exactMatch") else None
        print(
            "G2_QFONTINFO_DIAG",
            f"requested={family!r}",
            f"resolved={info.family()!r}",
            f"exact={exact}",
        )
