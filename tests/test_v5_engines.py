from pathlib import Path

from srstudio.editor.history import CommandHistory, LambdaCommand
from srstudio.editor.layout import LayoutEngine, Rect
from srstudio.products.database import ProductDatabase, ProductRecord
from srstudio.settings.store import SettingsStore, StudioSettings


def test_history_undo_redo():
    state = {"value": 0}
    history = CommandHistory()
    history.execute(LambdaCommand("incrementar", lambda: state.__setitem__("value", 1), lambda: state.__setitem__("value", 0)))
    assert state["value"] == 1
    assert history.undo() == "incrementar"
    assert state["value"] == 0
    assert history.redo() == "incrementar"
    assert state["value"] == 1


def test_layout_has_no_collisions():
    engine = LayoutEngine(margin=20, gap=10)
    plan = engine.grid(12, 800, 1100, columns=3)
    assert len(plan.slots) == 12
    assert engine.collision_pairs([slot.rect for slot in plan.slots]) == []


def test_rect_collision():
    assert Rect(0, 0, 10, 10).intersects(Rect(5, 5, 10, 10))
    assert not Rect(0, 0, 10, 10).intersects(Rect(10, 0, 5, 5))


def test_rebalance_pages():
    engine = LayoutEngine()
    assert engine.rebalance(31, 14) == (11, 10, 10)


def test_product_database_roundtrip(tmp_path: Path):
    db = ProductDatabase(tmp_path / "products.db")
    db.upsert(ProductRecord(code="1", ean="789", name="CAFÉ TESTE 500G", unit="UN", last_price="15.99"))
    result = db.search("CAFÉ")
    assert len(result) == 1
    assert result[0]["ean"] == "789"
    db.record_price("789", "15.99", "Quarta Café")
    assert db.price_history("789")[0]["price"] == "15.99"


def test_settings_roundtrip(tmp_path: Path):
    store = SettingsStore(tmp_path / "settings.json")
    settings = StudioSettings(theme="dark", autosave_seconds=30)
    store.save(settings)
    loaded = store.load()
    assert loaded.theme == "dark"
    assert loaded.autosave_seconds == 30
