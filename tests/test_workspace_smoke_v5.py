from pathlib import Path

from srstudio.app.ai_view import SRIAView
from srstudio.app.export_view import ExportView
from srstudio.app.proof_view import ProofView
from srstudio.app.validation_view import ValidationView
from srstudio.app.workspace import SRStudioWorkspace
from srstudio.products.database import ProductDatabase
from srstudio.templates.registry import TemplateRegistry


def test_professional_workspace_modules_import() -> None:
    assert SRStudioWorkspace is not None
    assert SRIAView is not None
    assert ProofView is not None
    assert ValidationView is not None
    assert ExportView is not None


def test_professional_services_construct_in_isolated_paths(tmp_path: Path) -> None:
    templates = TemplateRegistry(tmp_path / "templates")
    assert len(templates.all()) >= 6
    database = ProductDatabase(tmp_path / "products.sqlite3")
    assert database.path.exists()
