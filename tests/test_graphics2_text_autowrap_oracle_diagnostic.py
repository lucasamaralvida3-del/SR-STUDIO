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


def _line_snapshot(QtCore, QtGui, *, text: str, width: float, font, alignment=None):
    layout = QtGui.QTextLayout(text, font)
    option = QtGui.QTextOption()
    option.setWrapMode(QtGui.QTextOption.WrapMode.WordWrap)
    if alignment is not None:
        option.setAlignment(alignment)
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
                    "x": float(line.x()),
                    "y": float(line.y()),
                }
            )
    finally:
        layout.endLayout()
    return rows


def _line_texts(rows):
    return [row["text"] for row in rows]


def test_center_alignment_metric_oracle_diagnostic():
    _, QtCore, QtGui = _qt()
    font = QtGui.QFont("Arial")
    font.setPixelSize(24)
    text = "ALHO A GRANEL"
    metrics = QtGui.QFontMetricsF(font)
    width = max(metrics.horizontalAdvance("ALHO A"), metrics.horizontalAdvance("GRANEL")) + 1.0
    box_left = 10.0
    rows = _line_snapshot(QtCore, QtGui, text=text, width=width, font=font)
    reference_rows = _line_snapshot(
        QtCore,
        QtGui,
        text=text,
        width=width,
        font=font,
        alignment=QtCore.Qt.AlignHCenter,
    )
    assert len(rows) == 2
    assert [(r["start"], r["length"]) for r in rows] == [(r["start"], r["length"]) for r in reference_rows]

    image = QtGui.QImage(400, 160, QtGui.QImage.Format_ARGB32_Premultiplied)
    image.fill(QtCore.Qt.transparent)
    painter = QtGui.QPainter(image)
    painter.setFont(font)
    painter.setPen(QtGui.QColor("black"))
    try:
        for idx, (row, ref) in enumerate(zip(rows, reference_rows)):
            implementation_x = box_left + (width - row["natural"]) * 0.5
            fontmetrics_x = box_left + (width - row["font_advance"]) * 0.5
            reference_x = box_left + ref["x"]
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
                f"qtextlayout_reference_x={reference_x}",
                f"baseline={baseline}",
                "layout_primitive=QTextLayout/QTextLine",
                "draw_primitive=QPainter.drawText(QPointF,str)",
            )
            assert implementation_x == pytest.approx(reference_x, abs=1e-6)
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

    plain_full = _line_snapshot(QtCore, QtGui, text=text, width=10000.0, font=plain)[0]["natural"]
    tracked_full = _line_snapshot(QtCore, QtGui, text=text, width=10000.0, font=tracked)[0]["natural"]

    responsive_width = None
    responsive_plain = None
    responsive_tracked = None
    lower = max(40, int(min(plain_full, tracked_full) * 0.25))
    upper = int(max(plain_full, tracked_full))
    for tenths in range(lower * 10, upper * 10 + 1):
        candidate_width = tenths / 10.0
        p = _line_snapshot(QtCore, QtGui, text=text, width=candidate_width, font=plain)
        t = _line_snapshot(QtCore, QtGui, text=text, width=candidate_width, font=tracked)
        if _line_texts(p) != _line_texts(t):
            responsive_width = candidate_width
            responsive_plain = _line_texts(p)
            responsive_tracked = _line_texts(t)
            break

    spacing_type = tracked.letterSpacingType()
    spacing_type_text = getattr(spacing_type, "name", str(spacing_type))
    print(
        "G2_TRACKING_DIAG",
        f"platform={os.name}",
        f"requested={requested}",
        f"effective={tracked.letterSpacing()}",
        f"spacing_type={spacing_type_text}",
        f"plain_full_natural={plain_full}",
        f"tracked_full_natural={tracked_full}",
        f"plain_natural={[r['natural'] for r in plain_rows]}",
        f"tracked_natural={[r['natural'] for r in tracked_rows]}",
        f"plain_lines={_line_texts(plain_rows)!r}",
        f"tracked_lines={_line_texts(tracked_rows)!r}",
        f"responsive_width={responsive_width}",
        f"responsive_plain={responsive_plain!r}",
        f"responsive_tracked={responsive_tracked!r}",
    )
    assert tracked.letterSpacing() < 0
    assert tracked_full < plain_full
    assert responsive_width is not None

    for family in ("Anton", "High Cruiser"):
        requested_font = QtGui.QFont(family)
        info = QtGui.QFontInfo(requested_font)
        exact = info.exactMatch() if hasattr(info, "exactMatch") else None
        print(
            "G2_QFONTINFO_DIAG",
            f"platform={os.name}",
            f"requested={family!r}",
            f"resolved={info.family()!r}",
            f"exact={exact}",
        )
