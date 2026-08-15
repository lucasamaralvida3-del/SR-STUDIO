from __future__ import annotations

import hashlib
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from srstudio.images.library import ImageLibrary
from srstudio.importers.pptx.reader import PptxImporter
from srstudio.importers.pptx.semantic import SemanticMapper
from srstudio.templates.corpus import LayoutCorpus


TrainingProgress = Callable[[str, int, int, str], None]


@dataclass(slots=True)
class CanvaTrainingResult:
    files: int = 0
    slides: int = 0
    cards: int = 0
    images_learned: int = 0
    images_accepted: int = 0
    images_pending: int = 0
    layouts_observed: int = 0
    warnings: list[str] = field(default_factory=list)


class CanvaTrainingService:
    """Learn reusable SR layouts and product images from Canva-exported PPTX/ZIP files."""

    def __init__(
        self,
        image_library: ImageLibrary,
        layout_corpus: LayoutCorpus,
        imports_root: str | Path | None = None,
    ) -> None:
        self.image_library = image_library
        self.layout_corpus = layout_corpus
        self.imports_root = (
            Path(imports_root)
            if imports_root is not None
            else image_library.root.parent / "canva-training"
        )
        self.imports_root.mkdir(parents=True, exist_ok=True)
        self.importer = PptxImporter()
        self.mapper = SemanticMapper()

    def train(
        self,
        source: str | Path,
        *,
        on_progress: TrainingProgress | None = None,
    ) -> CanvaTrainingResult:
        path = Path(source)
        suffix = path.suffix.lower()
        if suffix == ".pptx":
            return self.train_many([path], on_progress=on_progress)
        if suffix != ".zip":
            raise ValueError("O treinamento Canva aceita arquivos PPTX ou ZIP com PPTX.")

        with tempfile.TemporaryDirectory(prefix="srstudio-canva-corpus-") as temp_name:
            temp = Path(temp_name)
            pptx_files = self._safe_extract_pptx(path, temp)
            if not pptx_files:
                raise RuntimeError("O ZIP não contém projetos PPTX do Canva.")
            return self.train_many(pptx_files, on_progress=on_progress)

    def train_many(
        self,
        files: list[Path],
        *,
        on_progress: TrainingProgress | None = None,
    ) -> CanvaTrainingResult:
        result = CanvaTrainingResult()
        total = len(files)
        for index, source in enumerate(files, start=1):
            if on_progress is not None:
                on_progress("file_start", index, total, source.name)
            try:
                self._train_pptx(source, result)
                result.files += 1
                if on_progress is not None:
                    on_progress("file_done", index, total, source.name)
            except Exception as exc:
                result.warnings.append(f"{source.name}: {exc}")
                if on_progress is not None:
                    on_progress("file_error", index, total, f"{source.name}: {exc}")
        return result

    def _train_pptx(self, source: Path, result: CanvaTrainingResult) -> None:
        digest = self._source_digest(source)
        media_dir = self.imports_root / digest / "media"
        media_dir.mkdir(parents=True, exist_ok=True)
        parsed = self.importer.import_file(source, media_dir=media_dir)
        result.warnings.extend(f"{source.name}: {warning}" for warning in parsed.warnings)

        for slide in parsed.slides:
            result.slides += 1
            cards = self.mapper.map_slide(slide)
            result.cards += len(cards)
            profile = self.layout_corpus.observe(slide, cards, str(source))
            if profile is not None:
                result.layouts_observed += 1

            for card in cards:
                if card.image is None or card.name is None:
                    continue
                image_path = Path(card.image.media_path)
                product_name = " ".join(card.name.text.split()).strip()
                if not product_name or not image_path.is_file():
                    continue
                confidence = float(card.confidence)
                if confidence < 0.58:
                    continue
                asset = self.image_library.learn_product_image(
                    image_path,
                    product_name,
                    confidence=confidence,
                    source_file=source.name,
                    slide_index=slide.index,
                    metadata={
                        "training_source": str(source),
                        "card_bounds": list(card.bounds) if card.bounds else [],
                        "campaign": self.layout_corpus.classify_campaign(slide, str(source)),
                        "canva_picture_fill": bool(card.image.metadata.get("picture_fill")),
                        "crop": dict(card.image.metadata.get("crop") or {}),
                    },
                )
                result.images_learned += 1
                if asset.review_status == "accepted":
                    result.images_accepted += 1
                else:
                    result.images_pending += 1

    @staticmethod
    def _safe_extract_pptx(source: Path, destination: Path) -> list[Path]:
        files: list[Path] = []
        root = destination.resolve()
        with zipfile.ZipFile(source) as archive:
            for member in archive.infolist():
                if member.is_dir() or not member.filename.lower().endswith(".pptx"):
                    continue
                relative = Path(member.filename.replace("\\", "/"))
                safe_name = Path(*[part for part in relative.parts if part not in {"", ".", ".."}])
                if not safe_name.parts:
                    continue
                target = (destination / safe_name).resolve()
                try:
                    target.relative_to(root)
                except ValueError:
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as incoming, target.open("wb") as outgoing:
                    shutil.copyfileobj(incoming, outgoing)
                files.append(target)
        return sorted(files, key=lambda item: item.name.casefold())

    @staticmethod
    def _source_digest(source: Path) -> str:
        digest = hashlib.sha256()
        with source.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()[:20]
