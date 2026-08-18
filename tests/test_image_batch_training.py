import json

from srstudio.images import batch_training
from srstudio.images.corpus_training import CorpusTrainingMetrics, CorpusTrainingReport


class FakeLibrary:
    index_path = None

    def all(self, **kwargs):
        return []

    def find_for_product(self, product_name):
        return []


class FakeTrainer:
    last = None

    def __init__(self, library, *, imports_root, state_path=None):
        self.library = library
        self.imports_root = imports_root
        self.state_path = state_path
        self.calls = []
        FakeTrainer.last = self

    def train(self, sources, *, force=False):
        self.calls.append((list(sources), force))
        metrics = CorpusTrainingMetrics(
            files_discovered=2,
            files_processed=1,
            files_skipped=1,
            unique_products=7,
            accepted=3,
            review=2,
        )
        return CorpusTrainingReport(
            metrics,
            decisions=[],
            warnings=["sample warning"],
            processed_files=["new.pptx"],
            skipped_files=["old.pptx"],
        )


def test_batch_training_uses_safe_contract_and_emits_rebuildable_report(tmp_path, monkeypatch):
    library = FakeLibrary()
    monkeypatch.setattr(batch_training, "SafeImageLibrary", lambda root: library)
    monkeypatch.setattr(batch_training, "PrecisionProductImageCorpusTrainer", FakeTrainer)

    result = batch_training.run_batch_training(
        ["new.pptx", "old.pptx"],
        library_root=tmp_path / "library",
        imports_root=tmp_path / "imports",
        force=True,
    )

    assert FakeTrainer.last.calls == [(["new.pptx", "old.pptx"], True)]
    assert result.report.metrics.files_processed == 1
    assert result.report.metrics.files_skipped == 1
    assert result.aliases.aliases_added == 0

    report_path = batch_training.write_report(tmp_path / "report.json", result)
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["metrics"]["unique_products"] == 7
    assert payload["metrics"]["accepted"] == 3
    assert payload["processed_files"] == ["new.pptx"]
    assert payload["skipped_files"] == ["old.pptx"]
    assert payload["warnings"] == ["sample warning"]
