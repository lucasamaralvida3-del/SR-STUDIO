from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from srstudio.images.corpus_training import _ImageCandidate
from srstudio.images.precision_training import PrecisionProductImageCorpusTrainer


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


class Library:
    AUTO_ACCEPT_CONFIDENCE = .82

    def all(self, **kwargs):
        return []


class Importer:
    pass


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
