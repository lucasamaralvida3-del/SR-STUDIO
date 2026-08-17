from __future__ import annotations

"""Recuperação conservadora de artwork raster do PPTX no Graphics2."""

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from srstudio.importers.pptx.reader import PptxElement, PptxImporter

from .model import AssetRef, GraphicsDocument, GraphicsNode, GraphicsPage, NodeKind, Transform


@dataclass(slots=True)
class PptxArtworkIssue:
    slide_index: int
    shape_name: str
    code: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PptxArtworkRecoveryReport:
    source_images: int = 0
    source_large_artworks: int = 0
    matched_images: int = 0
    recovered_nodes: int = 0
    repaired_assets: int = 0
    ready_images: int = 0
    ready_large_artworks: int = 0
    missing_media: int = 0
    ambiguous_images: int = 0
    issues: list[PptxArtworkIssue] = field(default_factory=list)

    @property
    def coverage(self) -> float:
        return 1.0 if self.source_images == 0 else self.ready_images / self.source_images

    @property
    def large_artwork_coverage(self) -> float:
        return 1.0 if self.source_large_artworks == 0 else self.ready_large_artworks / self.source_large_artworks

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["coverage"] = self.coverage
        payload["large_artwork_coverage"] = self.large_artwork_coverage
        payload["issues"] = [issue.to_dict() for issue in self.issues]
        return payload


def recover_pptx_artwork(
    source: str | Path,
    document: GraphicsDocument,
    *,
    cache_dir: str | Path | None = None,
) -> PptxArtworkRecoveryReport:
    """Garante node + asset local para toda imagem nativa do PPTX.

    A primeira passagem continua sendo o importador legado. Esta segunda
    passagem é exclusiva do Graphics2 e existe para que fundos, faixas,
    cabeçalhos e ornamentos não dependam do reconhecimento de produto.
    """

    path = Path(source)
    report = PptxArtworkRecoveryReport()
    if path.suffix.lower() != ".pptx" or not path.is_file():
        document.metadata["pptx_artwork_recovery"] = report.to_dict()
        return report

    cache_root = Path(cache_dir) if cache_dir is not None else Path.home() / ".srstudio5" / "imports-g2" / "artwork"
    try:
        parsed = PptxImporter().import_file(path, media_dir=cache_root / "media")
    except Exception as exc:
        report.issues.append(PptxArtworkIssue(0, "", "PPTX_ARTWORK_READ_FAILED", str(exc)))
        document.metadata["pptx_artwork_recovery"] = report.to_dict()
        return report

    for warning in parsed.warnings:
        report.issues.append(PptxArtworkIssue(0, "", "PPTX_ARTWORK_SOURCE_WARNING", str(warning)))

    for slide in parsed.slides:
        page_index = int(slide.index) - 1
        if not 0 <= page_index < len(document.pages):
            continue
        page = document.pages[page_index]
        for element in (item for item in slide.elements if item.kind == "image"):
            report.source_images += 1
            large = _is_large_artwork(element, slide.width, slide.height)
            if large:
                report.source_large_artworks += 1

            local = Path(str(element.media_path or ""))
            if not local.is_file():
                report.missing_media += 1
                report.issues.append(PptxArtworkIssue(slide.index, element.name, "PPTX_ARTWORK_MEDIA_MISSING", str(element.media_path)))
                continue

            target = _element_rect(element, slide.width, slide.height, page)
            candidates = _candidate_nodes(page, element.name)
            node = _resolve_candidate(candidates, target)
            if node is None and candidates:
                report.ambiguous_images += 1
                report.issues.append(PptxArtworkIssue(slide.index, element.name, "PPTX_ARTWORK_AMBIGUOUS", f"{len(candidates)} candidatos"))
                continue
            if node is None:
                node = _recover_node(document, page, element, slide.width, slide.height, local)
                report.recovered_nodes += 1
            else:
                report.matched_images += 1
                if _repair_asset(document, node, local):
                    report.repaired_assets += 1
                _enrich_existing_node(node, element, local)

            if _node_asset_ready(document, node):
                report.ready_images += 1
                if large:
                    report.ready_large_artworks += 1

    document.metadata["pptx_artwork_recovery"] = report.to_dict()
    return report


def _candidate_nodes(page: GraphicsPage, source_name: str) -> list[GraphicsNode]:
    wanted = str(source_name or "").strip()
    if not wanted:
        return []
    return [
        node
        for node in page.nodes.values()
        if node.kind in {NodeKind.IMAGE, NodeKind.BACKGROUND}
        and not node.metadata.get("semantic_synthetic_image_slot")
        and str(node.metadata.get("source_name") or node.name or "").strip() == wanted
    ]


def _resolve_candidate(candidates: list[GraphicsNode], target: tuple[float, float, float, float]) -> GraphicsNode | None:
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        return None
    tx, ty, tw, th = target
    ranked = sorted(
        (
            abs(node.transform.x - tx)
            + abs(node.transform.y - ty)
            + abs(node.transform.width - tw)
            + abs(node.transform.height - th),
            node,
        )
        for node in candidates
    )
    if ranked[0][0] <= 4.0 and (len(ranked) == 1 or ranked[1][0] - ranked[0][0] > 1.0):
        return ranked[0][1]
    return None


def _element_rect(element: PptxElement, slide_width: int, slide_height: int, page: GraphicsPage) -> tuple[float, float, float, float]:
    sw, sh = max(float(slide_width), 1.0), max(float(slide_height), 1.0)
    return (
        float(element.x) / sw * page.width,
        float(element.y) / sh * page.height,
        float(element.width) / sw * page.width,
        float(element.height) / sh * page.height,
    )


def _is_large_artwork(element: PptxElement, slide_width: int, slide_height: int) -> bool:
    sw, sh = max(float(slide_width), 1.0), max(float(slide_height), 1.0)
    area_ratio = max(0.0, float(element.width)) * max(0.0, float(element.height)) / (sw * sh)
    return area_ratio >= 0.18 or float(element.width) / sw >= 0.72 or float(element.height) / sh >= 0.72


def _recover_node(document: GraphicsDocument, page: GraphicsPage, element: PptxElement, sw: int, sh: int, local: Path) -> GraphicsNode:
    x, y, width, height = _element_rect(element, sw, sh, page)
    meta = dict(element.metadata or {})
    asset = _ensure_asset(document, local, meta)
    node = GraphicsNode(
        kind=NodeKind.IMAGE,
        name=str(element.name or "Artwork PPTX"),
        transform=Transform(x=x, y=y, width=max(0.0, width), height=max(0.0, height), rotation=float(meta.get("rotation", 0.0) or 0.0)),
        z_index=int(meta.get("z_index", 0) or 0),
        locked=True,
        visible=True,
        opacity=min(1.0, max(0.0, float(meta.get("opacity", 1.0) or 1.0))),
        asset_id=asset.id,
        style={
            "fit": "cover" if meta.get("crop") or meta.get("picture_fill") else "contain",
            "crop": dict(meta.get("crop") or {}),
            "fill_rect": dict(meta.get("fill_rect") or {}),
            "flip_x": bool(meta.get("flip_h", False)),
            "flip_y": bool(meta.get("flip_v", False)),
            "zoom": 1.0,
            "focus_x": 0.5,
            "focus_y": 0.5,
        },
        metadata={
            "source": "pptx-artwork-recovery",
            "source_name": str(element.name or ""),
            "bound_image_source": str(local),
            "pptx_artwork_recovered": True,
            "pptx_internal_media": str(meta.get("internal_media") or ""),
            "pptx_relationship_id": str(meta.get("relationship_id") or ""),
            "grouped": bool(meta.get("grouped", False)),
            "group_depth": int(meta.get("group_depth", 0) or 0),
            "group_name": str(meta.get("group_name") or ""),
        },
    )
    page.add_node(node)
    return node


def _enrich_existing_node(node: GraphicsNode, element: PptxElement, local: Path) -> None:
    meta = dict(element.metadata or {})
    node.metadata["pptx_artwork_verified"] = True
    node.metadata["pptx_artwork_source"] = str(local)
    node.metadata.setdefault("source_name", str(element.name or node.name or ""))
    bound = str(node.metadata.get("bound_image_source") or "").strip()
    if not bound or not _local_exists(bound):
        node.metadata["bound_image_source"] = str(local)
    node.style.setdefault("crop", dict(meta.get("crop") or {}))
    node.style.setdefault("fill_rect", dict(meta.get("fill_rect") or {}))
    node.style.setdefault("flip_x", bool(meta.get("flip_h", False)))
    node.style.setdefault("flip_y", bool(meta.get("flip_v", False)))


def _repair_asset(document: GraphicsDocument, node: GraphicsNode, local: Path) -> bool:
    current = document.assets.get(node.asset_id) if node.asset_id else None
    if current is not None and _local_exists(current.source):
        return False
    asset = _ensure_asset(document, local, node.metadata)
    changed = node.asset_id != asset.id or current is None
    node.asset_id = asset.id
    return changed


def _ensure_asset(document: GraphicsDocument, local: Path, metadata: dict[str, Any]) -> AssetRef:
    source = str(local)
    for asset in document.assets.values():
        if str(asset.source or "") == source:
            return asset
    asset = AssetRef(kind="image", source=source, embedded=False, metadata={"source": "pptx-artwork-recovery", "pptx_internal_media": str(metadata.get("internal_media") or "")})
    document.assets[asset.id] = asset
    return asset


def _node_asset_ready(document: GraphicsDocument, node: GraphicsNode) -> bool:
    asset = document.assets.get(node.asset_id) if node.asset_id else None
    return bool((asset is not None and _local_exists(asset.source)) or _local_exists(node.metadata.get("bound_image_source")))


def _local_exists(value: object) -> bool:
    text = str(value or "").strip()
    if not text or text.startswith(("http://", "https://", "data:", "image://")):
        return False
    if text.startswith("file:"):
        text = text[5:]
        if text.startswith("///"):
            text = text[2:]
        elif text.startswith("//"):
            text = text[1:]
        if len(text) >= 3 and text[0] == "/" and text[2] == ":":
            text = text[1:]
    try:
        return Path(text).is_file()
    except OSError:
        return False
