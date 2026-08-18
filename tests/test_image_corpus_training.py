from dataclasses import dataclass, field
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from srstudio.images.corpus_training import CorpusStateError, CorpusStateStore, ProductImageCorpusTrainer


@dataclass
class Element:
    kind: str
    x: int
    y: int
    width: int
    height: int
    text: str = ""
    media_path: str = ""
    name: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class Slide:
    index: int
    width: int = 1000
    height: int = 1000
    elements: list = field(default_factory=list)


@dataclass
class Result:
    slides: list
    warnings: list = field(default_factory=list)


class FakeImporter:
    def __init__(self):
        self.calls = 0

    def import_file(self, source, media_dir=None):
        self.calls += 1
        media_dir = Path(media_dir)
        media_dir.mkdir(parents=True, exist_ok=True)
        image = media_dir / "product.png"
        canvas = Image.new("RGBA", (320, 320), (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)
        draw.rectangle((70, 30, 250, 290), fill=(220, 40, 30, 255))
        draw.rectangle((90, 80, 230, 130), fill=(255, 230, 40, 255))
        draw.rectangle((100, 160, 220, 250), fill=(250, 250, 250, 255))
        canvas.save(image)
        return Result([
            Slide(1, elements=[
                Element("image", 100, 100, 300, 300, media_path=str(image), name="product", metadata={"z_index": 5}),
                Element("text", 120, 300, 260, 50, text="CAFÉ VASCONCELOS 500 G", name="name", metadata={"z_index": 10}),
                Element("text", 140, 360, 120, 50, text="R$ 18,99", name="price", metadata={"z_index": 11}),
            ])
        ])


class FakeLibrary:
    def __init__(self):
        self.learned = []

    def learn_product_image(self, path, product_name, **kwargs):
        self.learned.append((str(path), product_name, kwargs))
        return object()


def test_incremental_training_skips_unchanged_source(tmp_path):
    source = tmp_path / "corpus.pptx"
    source.write_bytes(b"synthetic-pptx")
    importer = FakeImporter()
    library = FakeLibrary()
    trainer = ProductImageCorpusTrainer(library, imports_root=tmp_path / "imports", importer=importer)

    first = trainer.train([source])
    assert first.metrics.files_processed == 1
    assert first.metrics.files_skipped == 0
    assert importer.calls == 1
    # One document is deliberately insufficient for production auto-approval.
    # It remains a usable probable candidate while the incremental state is saved.
    assert first.metrics.accepted == 0
    assert first.metrics.probable == 1
    assert library.learned
    learned_count = len(library.learned)

    second = trainer.train([source])
    assert second.metrics.files_processed == 0
    assert second.metrics.files_skipped == 1
    assert importer.calls == 1
    assert len(library.learned) == learned_count


def test_changed_source_supersedes_old_evidence(tmp_path):
    source = tmp_path / "corpus.pptx"
    source.write_bytes(b"version-one")
    trainer = ProductImageCorpusTrainer(FakeLibrary(), imports_root=tmp_path / "imports", importer=FakeImporter())
    trainer.train([source])
    source.write_bytes(b"version-two")
    trainer.train([source])
    state = trainer.state.load()
    active = [record for record in state["files"].values() if record.get("active", True)]
    inactive = [record for record in state["files"].values() if not record.get("active", True)]
    assert len(active) == 1
    assert len(inactive) == 1
    assert inactive[0]["superseded_by"] == active[0]["source_sha256"]


def test_corrupt_state_fails_closed_instead_of_resetting(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(CorpusStateError):
        CorpusStateStore(path).load()


def test_state_save_keeps_logical_backup(tmp_path):
    store = CorpusStateStore(tmp_path / "state.json")
    first = store.empty()
    first["updated_at"] = "first"
    store.save(first)
    second = store.load()
    second["updated_at"] = "second"
    store.save(second)
    backup = Path(str(store.path) + ".bak")
    assert backup.exists()
    assert '"updated_at": "first"' in backup.read_text(encoding="utf-8")
