from __future__ import annotations

import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from srstudio.posters.core import EMU_PER_MM, NS, PosterKind, PosterTemplate, PosterTemplateAnalyzer


class SRPosterTemplateAnalyzer(PosterTemplateAnalyzer):
    """SR-aware PPTX analyzer that ignores design-time helper shapes outside the printable slide."""

    def inspect(self, path: str | Path, kind: PosterKind = PosterKind.PROMOTION) -> PosterTemplate:
        source = Path(path)
        with zipfile.ZipFile(source) as archive:
            presentation = ET.fromstring(archive.read("ppt/presentation.xml"))
            slide_size = presentation.find("p:sldSz", NS)
            width_emu = int(slide_size.get("cx", "5400000")) if slide_size is not None else 5_400_000
            height_emu = int(slide_size.get("cy", "7560000")) if slide_size is not None else 7_560_000
            slide_xml = archive.read("ppt/slides/slide1.xml")

        root = ET.fromstring(slide_xml)
        all_shapes = self._read_shapes(root)
        width_mm = width_emu / EMU_PER_MM
        height_mm = height_emu / EMU_PER_MM
        printable_shapes = [
            shape
            for shape in all_shapes
            if self._overlaps_page(shape.x_mm, shape.y_mm, shape.width_mm, shape.height_mm, width_mm, height_mm)
        ]
        roles = super()._infer_roles(printable_shapes, kind, height_emu)
        return PosterTemplate(
            id=f"pptx-{source.stem.casefold().replace(' ', '-')}",
            name=f"{source.stem} · PPTX",
            kind=kind,
            width_mm=width_mm,
            height_mm=height_mm,
            background="#FFFFFF",
            accent="#0B4AA1",
            source_pptx=str(source),
            fields={role: shape for role, shape in roles.items()},
            metadata={
                "slide_width_emu": width_emu,
                "slide_height_emu": height_emu,
                "recognized_roles": sorted(roles),
                "shape_count": len(all_shapes),
                "printable_shape_count": len(printable_shapes),
                "ignored_helper_shapes": len(all_shapes) - len(printable_shapes),
            },
        )

    @staticmethod
    def _overlaps_page(
        x: float,
        y: float,
        width: float,
        height: float,
        page_width: float,
        page_height: float,
    ) -> bool:
        if width <= 0 or height <= 0:
            return False
        right = x + width
        bottom = y + height
        # Design-time notes used in the user's historical PPTX are deliberately
        # positioned fully outside the slide. A shape is content only when it
        # overlaps the printable page by a meaningful amount.
        overlap_width = max(0.0, min(right, page_width) - max(x, 0.0))
        overlap_height = max(0.0, min(bottom, page_height) - max(y, 0.0))
        if overlap_width <= 0 or overlap_height <= 0:
            return False
        visible_area = overlap_width * overlap_height
        shape_area = width * height
        return visible_area / max(shape_area, 0.0001) >= 0.25
