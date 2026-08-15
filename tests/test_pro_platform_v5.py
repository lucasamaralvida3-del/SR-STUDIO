from pathlib import Path

from srstudio.app.commands import CommandRegistry, StudioCommand
from srstudio.assets.fonts import FontCatalog
from srstudio.diagnostics.crash_guard import CrashGuard
from srstudio.extensions.registry import Extension, ExtensionManifest, ExtensionRegistry
from srstudio.projects.recent import RecentProjectsStore
from srstudio.settings.features import FeatureFlagStore, FeatureFlags


def test_command_registry_search_and_execute() -> None:
    called = []
    registry = CommandRegistry()
    registry.register(StudioCommand("project.save", "Salvar projeto", "Projeto", "Ctrl+S", ("gravar",), lambda: called.append(True)))
    assert registry.search("salvar")[0].id == "project.save"
    registry.execute("project.save")
    assert called == [True]


def test_recent_projects_store_roundtrip(tmp_path: Path) -> None:
    project = tmp_path / "oferta.srproject"
    project.write_text("{}", encoding="utf-8")
    store = RecentProjectsStore(tmp_path / "recent.json")
    items = store.touch(project, "Oferta")
    assert items[0].name == "Oferta"
    store.set_favorite(project, True)
    assert store.load()[0].favorite is True


def test_feature_flags_roundtrip(tmp_path: Path) -> None:
    store = FeatureFlagStore(tmp_path / "features.json")
    flags = FeatureFlags()
    flags.set("developer_mode", True)
    store.save(flags)
    assert store.load().enabled("developer_mode") is True


def test_crash_guard_records_report(tmp_path: Path) -> None:
    guard = CrashGuard(tmp_path, version="5.0-test")
    try:
        raise RuntimeError("teste")
    except RuntimeError as exc:
        report = guard.capture(type(exc), exc, exc.__traceback__, "promo.srproject")
    assert report.exception_type == "RuntimeError"
    assert guard.should_offer_safe_mode() is True
    guard.clear()
    assert guard.last_report() is None


def test_extension_registry_explicit_activation() -> None:
    events = []
    registry = ExtensionRegistry()
    registry.register(Extension(ExtensionManifest("demo", "Demo", "1.0"), lambda ctx: events.append(ctx)))
    assert registry.activate_all("ok") == ["demo"]
    assert events == ["ok"]


def test_font_catalog_substitution(tmp_path: Path) -> None:
    font = tmp_path / "SR-Test.ttf"
    font.write_bytes(b"fake")
    catalog = FontCatalog()
    catalog.register("SR Test", font)
    catalog.set_substitution("Montserrat", "SR Test")
    assert catalog.resolve("Montserrat") is not None
    assert catalog.missing(["Montserrat", "Outra"]) == ["Outra"]
