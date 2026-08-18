from __future__ import annotations

import argparse
import hashlib
import io
import json
import posixpath
import re
import unicodedata
import zipfile
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath
from typing import Iterable
from xml.etree import ElementTree as ET

from PIL import Image

from srstudio.images.association import is_product_text_candidate, normalize_product_name
from srstudio.images.visual_dedup import (
    compact_rgb_signature,
    is_conservative_visual_duplicate,
    visual_duplicate_signals,
)


_SLIDE_RE = re.compile(r"^ppt/slides/slide(\d+)\.xml$")
_NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "pr": "http://schemas.openxmlformats.org/package/2006/relationships",
}
_EMBED = f"{{{_NS['r']}}}embed"


@dataclass(frozen=True, slots=True)
class MediaInventory:
    sha256: str
    package_path: str
    width: int = 0
    height: int = 0
    mime_type: str = ""
    perceptual_hash: str = ""
    rgb_signature: str = ""

    @property
    def aspect_ratio(self) -> float:
        return self.width / max(1, self.height)


@dataclass(slots=True)
class PptxFileInventory:
    path: str
    file_sha256: str
    logical_sha256: str
    slides: int
    raw_image_refs: int
    media_files: int
    unique_media_sha256: int
    product_text_candidates: int
    unique_products: list[str]
    template_media_sha256: list[str]
    media: list[MediaInventory] = field(default_factory=list)
    content_mode: str = "mixed"
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class CorpusInventoryMetrics:
    files_found: int = 0
    unique_files_exact: int = 0
    logical_documents: int = 0
    slides: int = 0
    raw_image_refs: int = 0
    media_file_occurrences: int = 0
    unique_media_exact: int = 0
    product_text_candidates: int = 0
    unique_products: int = 0
    exact_duplicate_file_groups: int = 0
    logical_duplicate_groups: int = 0
    near_duplicate_pairs: int = 0
    geometry_rejected_dhash_pairs: int = 0
    content_rejected_dhash_pairs: int = 0
    text_only_files: int = 0
    template_heavy_files: int = 0
    mixed_files: int = 0


@dataclass(slots=True)
class CorpusInventoryReport:
    metrics: CorpusInventoryMetrics
    files: list[PptxFileInventory]
    exact_duplicate_files: list[list[str]] = field(default_factory=list)
    logical_duplicate_files: list[list[str]] = field(default_factory=list)
    near_duplicate_pairs: list[dict] = field(default_factory=list)
    media_reuse: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class PptxCorpusInventory:
    """Fast, structure-first inventory that never needs OCR or slide screenshots."""

    def scan(self, sources: Iterable[str | Path]) -> CorpusInventoryReport:
        warnings: list[str] = []
        paths = self.discover_sources(sources, warnings)
        files: list[PptxFileInventory] = []
        for path in paths:
            try:
                files.append(self.scan_file(path))
            except Exception as exc:
                warnings.append(f"{path}: {exc}")

        by_file_sha: dict[str, list[PptxFileInventory]] = defaultdict(list)
        by_logical_sha: dict[str, list[PptxFileInventory]] = defaultdict(list)
        product_names: set[str] = set()
        media_by_sha: dict[str, MediaInventory] = {}
        media_file_sources: dict[str, set[str]] = defaultdict(set)
        media_logical_sources: dict[str, set[str]] = defaultdict(set)
        media_occurrences: dict[str, int] = defaultdict(int)

        for item in files:
            by_file_sha[item.file_sha256].append(item)
            by_logical_sha[item.logical_sha256].append(item)
            product_names.update(item.unique_products)
            for media in item.media:
                media_by_sha.setdefault(media.sha256, media)
                media_file_sources[media.sha256].add(item.file_sha256)
                media_logical_sources[media.sha256].add(item.logical_sha256)
                media_occurrences[media.sha256] += 1

        exact_groups = [
            [row.path for row in group]
            for group in by_file_sha.values()
            if len(group) > 1
        ]
        logical_groups = [
            [row.path for row in group]
            for group in by_logical_sha.values()
            if len({row.file_sha256 for row in group}) > 1
        ]
        near_pairs, geometry_rejected, content_rejected = self._near_duplicate_pairs(media_by_sha.values())

        media_reuse = [
            {
                "sha256": sha256,
                "file_count": len(media_file_sources[sha256]),
                "logical_document_count": len(media_logical_sources[sha256]),
                "package_occurrences": media_occurrences[sha256],
            }
            for sha256 in sorted(media_by_sha)
        ]
        media_reuse.sort(
            key=lambda row: (row["logical_document_count"], row["file_count"], row["package_occurrences"]),
            reverse=True,
        )

        metrics = CorpusInventoryMetrics(
            files_found=len(files),
            unique_files_exact=len(by_file_sha),
            logical_documents=len(by_logical_sha),
            slides=sum(item.slides for item in files),
            raw_image_refs=sum(item.raw_image_refs for item in files),
            media_file_occurrences=sum(item.media_files for item in files),
            unique_media_exact=len(media_by_sha),
            product_text_candidates=sum(item.product_text_candidates for item in files),
            unique_products=len(product_names),
            exact_duplicate_file_groups=len(exact_groups),
            logical_duplicate_groups=len(logical_groups),
            near_duplicate_pairs=len(near_pairs),
            geometry_rejected_dhash_pairs=geometry_rejected,
            content_rejected_dhash_pairs=content_rejected,
            text_only_files=sum(item.content_mode == "text-only" for item in files),
            template_heavy_files=sum(item.content_mode == "template-heavy" for item in files),
            mixed_files=sum(item.content_mode == "mixed" for item in files),
        )
        return CorpusInventoryReport(
            metrics=metrics,
            files=files,
            exact_duplicate_files=exact_groups,
            logical_duplicate_files=logical_groups,
            near_duplicate_pairs=near_pairs,
            media_reuse=media_reuse,
            warnings=warnings,
        )

    def scan_file(self, path: str | Path) -> PptxFileInventory:
        source = Path(path)
        file_sha256 = _sha256_file(source)
        warnings: list[str] = []
        with zipfile.ZipFile(source) as archive:
            names = set(archive.namelist())
            slide_names = sorted(
                (name for name in names if _SLIDE_RE.match(name)),
                key=lambda value: int(_SLIDE_RE.match(value).group(1)),
            )
            media_paths = sorted(name for name in names if name.startswith("ppt/media/") and not name.endswith("/"))
            media: list[MediaInventory] = []
            media_sha_by_path: dict[str, str] = {}
            for media_path in media_paths:
                blob = archive.read(media_path)
                sha256 = hashlib.sha256(blob).hexdigest()
                media_sha_by_path[media_path] = sha256
                media.append(_media_inventory(media_path, blob, sha256, warnings))

            raw_refs = 0
            products: set[str] = set()
            product_text_count = 0
            slide_semantics: list[dict] = []
            media_slide_usage: dict[str, set[int]] = defaultdict(set)

            for slide_name in slide_names:
                slide_index = int(_SLIDE_RE.match(slide_name).group(1))
                root = ET.fromstring(archive.read(slide_name))
                shape_texts = _shape_texts(root)
                for text in shape_texts:
                    if is_product_text_candidate(text):
                        product_text_count += 1
                        normalized = normalize_product_name(text)
                        if normalized:
                            products.add(normalized)

                relationships = _slide_relationships(archive, slide_name, names)
                slide_media: list[str] = []
                for blip in root.findall(".//a:blip", _NS):
                    rid = blip.attrib.get(_EMBED, "")
                    target = relationships.get(rid, "")
                    if not target:
                        continue
                    raw_refs += 1
                    media_sha = media_sha_by_path.get(target, "")
                    if media_sha:
                        slide_media.append(media_sha)
                        media_slide_usage[media_sha].add(slide_index)

                slide_semantics.append(
                    {
                        "texts": [_normalize_layout_text(text) for text in shape_texts if text.strip()],
                        "media_sha256": sorted(slide_media),
                    }
                )

            slide_count = len(slide_names)
            template_sha = {
                sha256
                for sha256, used_slides in media_slide_usage.items()
                if len(used_slides) >= 3 and len(used_slides) / max(1, slide_count) >= 0.30
            }
            referenced_unique = set(media_slide_usage)
            template_ratio = len(template_sha) / max(1, len(referenced_unique))
            if not referenced_unique:
                content_mode = "text-only"
            elif product_text_count and template_ratio >= 0.70:
                content_mode = "template-heavy"
            else:
                content_mode = "mixed"

            semantic_payload = {
                "slides": slide_semantics,
                "media_sha256": sorted(media_sha_by_path.values()),
            }
            logical_sha256 = hashlib.sha256(
                json.dumps(semantic_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()

        return PptxFileInventory(
            path=str(source),
            file_sha256=file_sha256,
            logical_sha256=logical_sha256,
            slides=len(slide_names),
            raw_image_refs=raw_refs,
            media_files=len(media),
            unique_media_sha256=len({item.sha256 for item in media}),
            product_text_candidates=product_text_count,
            unique_products=sorted(products),
            template_media_sha256=sorted(template_sha),
            media=media,
            content_mode=content_mode,
            warnings=warnings,
        )

    @staticmethod
    def discover_sources(sources: Iterable[str | Path], warnings: list[str]) -> list[Path]:
        result: list[Path] = []
        for item in sources:
            path = Path(item)
            if path.is_dir():
                result.extend(sorted(path.rglob("*.pptx")))
            elif path.is_file() and path.suffix.lower() == ".pptx":
                result.append(path)
            else:
                warnings.append(f"Unsupported or missing inventory source: {path}")
        return result

    @staticmethod
    def _near_duplicate_pairs(
        media: Iterable[MediaInventory],
        max_distance: int = 4,
    ) -> tuple[list[dict], int, int]:
        tree = _HammingBKTree()
        result: list[dict] = []
        geometry_rejected = 0
        content_rejected = 0
        seen_pairs: set[tuple[str, str]] = set()
        for item in sorted(media, key=lambda row: row.sha256):
            if not item.perceptual_hash:
                continue
            value = int(item.perceptual_hash, 16)
            for distance, other in tree.search(value, max_distance):
                pair = tuple(sorted((item.sha256, other.sha256)))
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                signals = visual_duplicate_signals(
                    item.perceptual_hash,
                    other.perceptual_hash,
                    (item.width, item.height),
                    (other.width, other.height),
                    left_rgb_signature=item.rgb_signature,
                    right_rgb_signature=other.rgb_signature,
                )
                geometry_ok = signals.same_orientation and signals.aspect_delta <= 0.08
                content_ok = signals.content_distance is None or signals.content_distance <= 0.12
                compatible = is_conservative_visual_duplicate(
                    item.perceptual_hash,
                    other.perceptual_hash,
                    (item.width, item.height),
                    (other.width, other.height),
                    left_rgb_signature=item.rgb_signature,
                    right_rgb_signature=other.rgb_signature,
                    max_hamming_distance=max_distance,
                )
                rejection_reason = ""
                if not geometry_ok:
                    geometry_rejected += 1
                    rejection_reason = "geometry"
                elif not content_ok:
                    content_rejected += 1
                    rejection_reason = "content"
                result.append(
                    {
                        "left_sha256": pair[0],
                        "right_sha256": pair[1],
                        "dhash_distance": distance,
                        "aspect_delta": round(signals.aspect_delta, 6),
                        "content_distance": (
                            round(signals.content_distance, 6)
                            if signals.content_distance is not None
                            else None
                        ),
                        "geometry_compatible": geometry_ok,
                        "content_compatible": content_ok,
                        "duplicate_compatible": compatible,
                        "rejection_reason": rejection_reason,
                    }
                )
            tree.add(value, item)
        result.sort(key=lambda row: (row["dhash_distance"], row["left_sha256"], row["right_sha256"]))
        return result, geometry_rejected, content_rejected


@dataclass
class _BKNode:
    value: int
    items: list[MediaInventory]
    children: dict[int, "_BKNode"] = field(default_factory=dict)


class _HammingBKTree:
    def __init__(self) -> None:
        self.root: _BKNode | None = None

    def add(self, value: int, item: MediaInventory) -> None:
        if self.root is None:
            self.root = _BKNode(value, [item])
            return
        node = self.root
        while True:
            distance = (value ^ node.value).bit_count()
            if distance == 0:
                node.items.append(item)
                return
            child = node.children.get(distance)
            if child is None:
                node.children[distance] = _BKNode(value, [item])
                return
            node = child

    def search(self, value: int, max_distance: int) -> list[tuple[int, MediaInventory]]:
        if self.root is None:
            return []
        result: list[tuple[int, MediaInventory]] = []
        stack = [self.root]
        while stack:
            node = stack.pop()
            distance = (value ^ node.value).bit_count()
            if distance <= max_distance:
                result.extend((distance, item) for item in node.items)
            lower = max(0, distance - max_distance)
            upper = distance + max_distance
            stack.extend(child for edge, child in node.children.items() if lower <= edge <= upper)
        return result


def _shape_texts(root: ET.Element) -> list[str]:
    result: list[str] = []
    for shape in root.findall(".//p:sp", _NS):
        text = " ".join((node.text or "").strip() for node in shape.findall(".//a:t", _NS) if (node.text or "").strip())
        text = " ".join(text.split())
        if text:
            result.append(text)
    for cell in root.findall(".//a:tc", _NS):
        text = " ".join((node.text or "").strip() for node in cell.findall(".//a:t", _NS) if (node.text or "").strip())
        text = " ".join(text.split())
        if text:
            result.append(text)
    return result


def _slide_relationships(archive: zipfile.ZipFile, slide_name: str, names: set[str]) -> dict[str, str]:
    slide = PurePosixPath(slide_name)
    rels_name = str(slide.parent / "_rels" / f"{slide.name}.rels")
    if rels_name not in names:
        return {}
    root = ET.fromstring(archive.read(rels_name))
    result: dict[str, str] = {}
    for relation in root.findall("pr:Relationship", _NS):
        rid = relation.attrib.get("Id", "")
        target = relation.attrib.get("Target", "")
        if not rid or not target or relation.attrib.get("TargetMode") == "External":
            continue
        resolved = posixpath.normpath(posixpath.join(str(slide.parent), target))
        result[rid] = resolved
    return result


def _media_inventory(package_path: str, blob: bytes, sha256: str, warnings: list[str]) -> MediaInventory:
    try:
        with Image.open(io.BytesIO(blob)) as image:
            width, height = image.size
            mime = Image.MIME.get(image.format or "", "")
            return MediaInventory(
                sha256=sha256,
                package_path=package_path,
                width=int(width),
                height=int(height),
                mime_type=mime,
                perceptual_hash=_dhash(image),
                rgb_signature=compact_rgb_signature(image),
            )
    except Exception as exc:
        warnings.append(f"{package_path}: image metadata unavailable: {exc}")
        return MediaInventory(sha256=sha256, package_path=package_path)


def _dhash(image: Image.Image) -> str:
    gray = image.convert("L").resize((9, 8))
    pixels = list(gray.getdata())
    value = 0
    for row in range(8):
        for col in range(8):
            value = (value << 1) | int(pixels[row * 9 + col] > pixels[row * 9 + col + 1])
    return f"{value:016x}"


def _normalize_layout_text(value: str) -> str:
    text = "".join(ch for ch in unicodedata.normalize("NFKD", str(value)) if not unicodedata.combining(ch))
    return " ".join(text.upper().split())


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def report_payload(report: CorpusInventoryReport) -> dict:
    return {
        "metrics": asdict(report.metrics),
        "files": [
            {
                **{key: value for key, value in asdict(item).items() if key != "media"},
                "media": [asdict(media) for media in item.media],
            }
            for item in report.files
        ],
        "exact_duplicate_files": report.exact_duplicate_files,
        "logical_duplicate_files": report.logical_duplicate_files,
        "near_duplicate_pairs": report.near_duplicate_pairs,
        "media_reuse": report.media_reuse,
        "warnings": report.warnings,
    }


def write_report(path: str | Path, report: CorpusInventoryReport) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(report_payload(report), ensure_ascii=False, indent=2), encoding="utf-8")
    json.loads(tmp.read_text(encoding="utf-8"))
    tmp.replace(target)
    return target


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inventário estrutural do corpus PPTX para Produto↔Imagem.")
    parser.add_argument("sources", nargs="+", help="PPTX ou diretórios contendo PPTX")
    parser.add_argument("--report", default=None, help="Grava relatório JSON detalhado")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    report = PptxCorpusInventory().scan(args.sources)
    payload = report_payload(report)
    if args.report:
        payload["report_path"] = str(write_report(args.report, report))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
