from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

from PIL import Image, ImageDraw

from srstudio.images.corpus_training import _ImageCandidate
from srstudio.images.precision_training import (
    PRECISION_TRAINER_VERSION,
    PrecisionProductImageCorpusTrainer,
)


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


class Library:
    AUTO_ACCEPT_CONFIDENCE = .82

    def __init__(self):
        self.learned = []

    def all(self, **kwargs):
        return []

    def learn_product_image(self, path, product_name, **kwargs):
        self.learned.append((str(path), product_name, kwargs))
        return SimpleNamespace(id=None)


class Importer:
    pass


class CountingImporter:
    def __init__(self):
        self.calls = 0

    def import_file(self, source, media_dir=None):
        self.calls += 1
        media_dir = Path(media_dir)
        media_dir.mkdir(parents=True, exist_ok=True)
        image_path = media_dir / "product.png"
        image = Image.new("RGB", (320, 480), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle((60, 30, 260, 450), fill=(210, 25, 35))
        draw.rectangle((90, 100, 230, 180), fill=(250, 220, 20))
        image.save(image_path)
        return Result(
            [
                Slide(
                    1,
                    elements=[
                        Element(
                            "image",
                            100,
                            100,
                            300,
                            420,
                            media_path=str(image_path),
                            name="product",
                            metadata={"z_index": 5},
                        ),
                        Element(
                            "text",
                            120,
                            540,
                            280,
                            50,
                            text="CAFÉ VASCONCELOS 500 G",
                            name="name",
                            metadata={"z_index": 10},
                        ),
                        Element(
                            "text",
                            160,
                            600,
                            120,
                            40,
                            text="R$ 18,99",
                            name="price",
                            metadata={"z_index": 11},
                        ),
                    ],
                )
            ]
        )


def _trainer(tmp_path):
    trainer = PrecisionProductImageCorpusTrainer(Library(), imports_root=tmp_path / "imports", importer=Importer())
    trainer._product_likelihood = lambda *args: .85
    return trainer


def test_repeated_shapes_with_same_sha_are_one_logical_image(tmp_path):
    trainer = _trainer(tmp_path)
    image_path = tmp_path / "same.png"
    Image.new("RGB", (200, 300), (200, 40, 30)).save(image_path)
    text = Element("text", 120, 360, 260, 50, text="CAFÉ VASCONCELOS 500G", metadata={"z_index": 10})
    duplicate_a = _ImageCandidate("a" * 64, str(image_path), "a", "rId1", (100, 100, 300, 300), 5, "", .09)
    duplicate_b = _ImageCandidate("a" * 64, str(image_path), "b", "rId2", (100, 100, 300, 300), 6, "", .09)
    slide = Slide(1, elements=[text])

    evidence = trainer._pair_slide(slide, [text], [duplicate_a, duplicate_b], {"a" * 64: {1}}, 1, set(), "same.pptx")

    assert len(evidence) == 1
    assert evidence[0].image_sha256 == "a" * 64
    assert evidence[0].confidence >= .90


def test_weak_singleton_is_retained_but_cannot_auto_accept(tmp_path):
    trainer = _trainer(tmp_path)
    trainer._product_likelihood = lambda *args: .80
    image_path = tmp_path / "far.png"
    Image.new("RGB", (200, 300), (20, 100, 220)).save(image_path)
    text = Element("text", 760, 800, 200, 50, text="PEIXE PIRAMUTABA PESQUALI 1KG", metadata={"z_index": 10})
    image = _ImageCandidate("b" * 64, str(image_path), "product", "rId1", (20, 20, 140, 200), 5, "", .028)
    slide = Slide(1, elements=[text])

    evidence = trainer._pair_slide(slide, [text], [image], {"b" * 64: {1}}, 1, set(), "weak.pptx")

    assert len(evidence) == 1
    assert evidence[0].metadata["pair_score"] < .39
    assert evidence[0].confidence <= .89


def test_logical_document_fingerprint_collapses_export_copies():
    base_record = {
        "slides": 2,
        "raw_image_refs": 4,
        "image_sha256": ["a" * 64, "b" * 64],
        "product_names": ["CAFÉ VASCONCELOS 500 G", "MONSTER 473ML"],
        "evidence": [
            {"source_slide": 1, "product_name": "CAFÉ VASCONCELOS 500 G", "image_sha256": "a" * 64},
            {"source_slide": 2, "product_name": "MONSTER 473ML", "image_sha256": "b" * 64},
        ],
    }
    copy_record = {
        **base_record,
        "source_file": "OFERTAS QUINTA FILÉ NOVO(1).pptx",
        "source_sha256": "f" * 64,
    }
    original_record = {
        **base_record,
        "source_file": "OFERTAS QUINTA FILÉ NOVO.pptx",
        "source_sha256": "e" * 64,
    }

    assert PrecisionProductImageCorpusTrainer._logical_document_fingerprint(copy_record) == (
        PrecisionProductImageCorpusTrainer._logical_document_fingerprint(original_record)
    )


def test_logical_document_fingerprint_changes_when_product_image_pair_changes():
    first = {
        "slides": 1,
        "raw_image_refs": 1,
        "image_sha256": ["a" * 64],
        "product_names": ["TODDY 370G"],
        "evidence": [{"source_slide": 1, "product_name": "TODDY 370G", "image_sha256": "a" * 64}],
    }
    second = {
        **first,
        "product_names": ["TODDY 750G"],
        "evidence": [{"source_slide": 1, "product_name": "TODDY 750G", "image_sha256": "a" * 64}],
    }
    assert PrecisionProductImageCorpusTrainer._logical_document_fingerprint(first) != (
        PrecisionProductImageCorpusTrainer._logical_document_fingerprint(second)
    )


def test_processed_record_carries_raw_and_logical_source_identity(tmp_path):
    source = tmp_path / "corpus.pptx"
    source.write_bytes(b"synthetic-pptx")
    trainer = PrecisionProductImageCorpusTrainer(
        Library(),
        imports_root=tmp_path / "imports",
        importer=CountingImporter(),
    )
    digest = "d" * 64

    record = trainer._process_pptx(source, digest)

    assert record["precision_trainer_version"] == PRECISION_TRAINER_VERSION
    assert len(record["source_document_id"]) == 64
    assert record["evidence"]
    metadata = record["evidence"][0]["metadata"]
    assert metadata["source_document_id"] == record["source_document_id"]
    assert metadata["source_sha256"] == digest


def test_stale_precision_record_is_reprocessed_incrementally(tmp_path):
    source = tmp_path / "corpus.pptx"
    source.write_bytes(b"synthetic-pptx")
    importer = CountingImporter()
    trainer = PrecisionProductImageCorpusTrainer(
        Library(),
        imports_root=tmp_path / "imports",
        importer=importer,
    )

    trainer.train([source])
    assert importer.calls == 1

    state = trainer.state.load()
    for record in state["files"].values():
        record.pop("precision_trainer_version", None)
    trainer.state.save(state)

    report = trainer.train([source])

    assert importer.calls == 2
    assert report.metrics.files_processed == 1
    assert any(PRECISION_TRAINER_VERSION in warning for warning in report.warnings)
