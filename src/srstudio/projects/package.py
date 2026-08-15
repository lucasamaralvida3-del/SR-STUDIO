from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

from srstudio.core.models import StudioProject
from srstudio.projects.store import ProjectStore


class ProjectPackage:
    """Empacota projeto + imagens em um único arquivo .srpack portátil."""

    def __init__(self, store: ProjectStore) -> None:
        self.store = store

    def create(self, project: StudioProject, destination: str | Path) -> Path:
        target = Path(destination)
        if target.suffix.lower() != ".srpack":
            target = target.with_suffix(".srpack")
        target.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_copy = StudioProject.from_dict(project.to_dict())
            assets = root / "assets"
            assets.mkdir()
            copied: dict[str, str] = {}
            for product in project_copy.products:
                source = Path(product.image_path) if product.image_path else None
                if source is None or not source.exists() or not source.is_file():
                    continue
                key = str(source.resolve())
                if key not in copied:
                    filename = f"{len(copied)+1:04d}_{source.name}"
                    shutil.copy2(source, assets / filename)
                    copied[key] = filename
                product.image_path = f"assets/{copied[key]}"
            project_path = root / "project.srproject"
            self.store.save(project_copy, project_path)
            manifest = {
                "format": "srpack",
                "version": 1,
                "project": "project.srproject",
                "assets": sorted(copied.values()),
            }
            (root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for file in root.rglob("*"):
                    if file.is_file():
                        archive.write(file, file.relative_to(root).as_posix())
        return target

    def extract(self, package: str | Path, destination: str | Path) -> StudioProject:
        package_path = Path(package)
        target = Path(destination)
        target.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(package_path) as archive:
            for member in archive.infolist():
                member_path = Path(member.filename)
                if member_path.is_absolute() or ".." in member_path.parts:
                    raise ValueError("Pacote contém caminho inválido")
                archive.extract(member, target)
        manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
        project = self.store.load(target / manifest["project"])
        for product in project.products:
            if product.image_path and not Path(product.image_path).is_absolute():
                product.image_path = str((target / product.image_path).resolve())
        return project
