from __future__ import annotations

import json
import shutil
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from srstudio.posters.core import PosterKind, PosterTemplate, PosterTemplateAnalyzer
from srstudio.posters.legacy_bridge import legacy_models_root


@dataclass(frozen=True, slots=True)
class PosterModelEntry:
    id: str
    name: str
    filename: str
    kind: PosterKind
    variant: str
    group: str
    path: str
    read_only: bool = False
    recommended: bool = False
    size: int = 0
    modified_at: str = ""
    metadata: dict[str, object] = field(default_factory=dict)


class PosterModelCatalog:
    """Persistent catalog for official, original, custom and versioned poster PPTX files.

    Official files live inside the application package and are never modified. A protected
    copy of every official model is seeded under ``~/.srstudio5/modelos/originais`` so an
    application update can never remove the user's model library. Custom models and backups
    are stored alongside that protected copy and reindexed automatically.
    """

    GROUP_OFFICIAL = "Oficiais"
    GROUP_ORIGINAL = "Originais"
    GROUP_CUSTOM = "Personalizados"
    GROUP_VERSION = "Versões"

    _MODEL_INFO: dict[str, tuple[str, PosterKind, str, bool]] = {
        "ATACADO.PPTX": ("Atacado · Oficial", PosterKind.WHOLESALE, "atacado", True),
        "CARTAZ_VENDA.PPTX": ("Cartaz Venda", PosterKind.PROMOTION, "venda", False),
        "CLUBE_EXCLUSIVO.PPTX": (
            "Clube Exclusivo",
            PosterKind.PROMOTION,
            "clube_exclusivo",
            False,
        ),
        "CLUBE_EXCLUSIVO_COM_LIMITE.PPTX": (
            "Clube Exclusivo · com limite",
            PosterKind.PROMOTION,
            "clube_exclusivo_limite",
            False,
        ),
        "SEGUNDA_DA_LIMPEZA_1_PRECO.PPTX": (
            "Promoção · 1 preço",
            PosterKind.PROMOTION,
            "1_preco",
            True,
        ),
        "SEGUNDA_DA_LIMPEZA_1_PRECO_COM_LIMITE.PPTX": (
            "Promoção · 1 preço · com limite",
            PosterKind.PROMOTION,
            "1_preco_limite",
            False,
        ),
        "SEGUNDA_DA_LIMPEZA_2_PRECOS.PPTX": (
            "Promoção · 2 preços",
            PosterKind.PROMOTION,
            "2_precos",
            True,
        ),
        "SEGUNDA_DA_LIMPEZA_2_PRECOS_COM_LIMITE.PPTX": (
            "Promoção · 2 preços · com limite",
            PosterKind.PROMOTION,
            "2_precos_limite",
            False,
        ),
    }

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root) if root is not None else Path.home() / ".srstudio5" / "modelos"
        self.originals_root = self.root / "originais"
        self.custom_root = self.root / "personalizados"
        self.versions_root = self.root / "versoes"
        self.catalog_path = self.root / "catalog.json"
        self.custom_kind_path = self.root / "custom-kinds.json"
        for folder in (self.root, self.originals_root, self.custom_root, self.versions_root):
            folder.mkdir(parents=True, exist_ok=True)
        self.migrate_legacy_folders()
        self.seed_originals()
        self.reindex()

    @property
    def official_root(self) -> Path:
        return legacy_models_root()

    def migrate_legacy_folders(self) -> int:
        """Import models left beside older launchers/installations without overwriting new data."""
        copied = 0
        for candidate in self._legacy_candidates():
            try:
                if candidate.resolve() == self.root.resolve() or not candidate.is_dir():
                    continue
            except OSError:
                continue

            for source in sorted(candidate.glob("*.pptx")):
                if source.name.upper() in self._MODEL_INFO:
                    destination = self.originals_root / source.name
                else:
                    destination = self.custom_root / source.name
                    self._set_custom_kind(source.name, self._infer_kind(source.name))
                copied += int(self._copy_if_missing(source, destination))

            old_originals = candidate / "originais"
            if old_originals.is_dir():
                for source in sorted(old_originals.glob("*.pptx")):
                    copied += int(self._copy_if_missing(source, self.originals_root / source.name))

            old_versions = candidate / "versoes"
            if old_versions.is_dir():
                for source in sorted(old_versions.glob("**/*.pptx")):
                    relative = source.relative_to(old_versions)
                    copied += int(self._copy_if_missing(source, self.versions_root / relative))
        return copied

    def seed_originals(self, *, force: bool = False) -> int:
        copied = 0
        for source in sorted(self.official_root.glob("*.pptx")):
            destination = self.originals_root / source.name
            if destination.exists() and not force:
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            copied += 1
        return copied

    def restore_originals(self) -> int:
        """Restore the protected original copies from immutable packaged files."""
        return self.seed_originals(force=True)

    def reindex(self) -> list[PosterModelEntry]:
        entries: list[PosterModelEntry] = []
        entries.extend(self._scan_folder(self.official_root, self.GROUP_OFFICIAL, read_only=True))
        entries.extend(self._scan_folder(self.originals_root, self.GROUP_ORIGINAL, read_only=True))

        # Compatibility: earlier SR Studio builds placed user models directly in /modelos.
        direct_user_files = [path for path in self.root.glob("*.pptx") if path.is_file()]
        entries.extend(self._entries_for_paths(direct_user_files, self.GROUP_CUSTOM, read_only=False))
        entries.extend(self._scan_folder(self.custom_root, self.GROUP_CUSTOM, read_only=False))
        entries.extend(self._scan_folder(self.versions_root, self.GROUP_VERSION, read_only=True, recursive=True))

        unique: dict[tuple[str, str], PosterModelEntry] = {}
        for entry in entries:
            unique[(entry.group, str(Path(entry.path).resolve()).casefold())] = entry
        ordered = sorted(
            unique.values(),
            key=lambda item: (
                self._group_order(item.group),
                0 if item.recommended else 1,
                item.kind.value,
                item.name.casefold(),
                item.filename.casefold(),
            ),
        )
        self._write_catalog(ordered)
        return ordered

    def list(
        self,
        kind: PosterKind | None = None,
        *,
        include_versions: bool = True,
        groups: set[str] | None = None,
    ) -> list[PosterModelEntry]:
        entries = self._read_catalog()
        if not entries:
            entries = self.reindex()
        result: list[PosterModelEntry] = []
        for entry in entries:
            if kind is not None and entry.kind != kind:
                continue
            if not include_versions and entry.group == self.GROUP_VERSION:
                continue
            if groups is not None and entry.group not in groups:
                continue
            if not Path(entry.path).is_file():
                continue
            result.append(entry)
        return result

    def install_custom(self, source: str | Path, kind: PosterKind | None = None) -> PosterModelEntry:
        source_path = Path(source)
        if not source_path.is_file() or source_path.suffix.lower() != ".pptx":
            raise ValueError("Selecione um arquivo PPTX válido.")
        destination = self.custom_root / source_path.name
        if destination.exists():
            self._backup_existing(destination)
        shutil.copy2(source_path, destination)
        selected_kind = kind or self._infer_kind(source_path.name)
        self._set_custom_kind(destination.name, selected_kind)
        self.reindex()
        entries = [item for item in self.list(selected_kind, include_versions=False) if Path(item.path) == destination]
        if entries:
            return entries[0]
        return self._entry_for(destination, self.GROUP_CUSTOM, read_only=False, forced_kind=selected_kind)

    def backup_custom(self, path: str | Path) -> Path:
        source = Path(path)
        if not source.is_file():
            raise FileNotFoundError(source)
        return self._backup_existing(source)

    def to_template(self, entry: PosterModelEntry, analyzer: PosterTemplateAnalyzer | None = None) -> PosterTemplate:
        inspector = analyzer or PosterTemplateAnalyzer()
        try:
            template = inspector.inspect(entry.path, entry.kind)
        except Exception:
            template = PosterTemplate(
                id=entry.id,
                name=entry.name,
                kind=entry.kind,
                source_pptx=entry.path,
            )
        template.id = entry.id
        template.name = f"{entry.group.upper()} · {entry.name}"
        template.source_pptx = entry.path
        template.metadata.update(entry.metadata)
        template.metadata.update(
            {
                "catalog_group": entry.group,
                "catalog_variant": entry.variant,
                "catalog_filename": entry.filename,
                "catalog_read_only": entry.read_only,
                "recommended": entry.recommended,
            }
        )
        if entry.filename.upper() in self._MODEL_INFO:
            template.metadata["legacy_engine"] = entry.kind.value
            template.metadata["legacy_model"] = entry.filename
        return template

    def summary(self) -> dict[str, int]:
        entries = self.list()
        counts = {
            self.GROUP_OFFICIAL: 0,
            self.GROUP_ORIGINAL: 0,
            self.GROUP_CUSTOM: 0,
            self.GROUP_VERSION: 0,
        }
        for item in entries:
            counts[item.group] = counts.get(item.group, 0) + 1
        counts["Total"] = len(entries)
        return counts

    def _scan_folder(
        self,
        folder: Path,
        group: str,
        *,
        read_only: bool,
        recursive: bool = False,
    ) -> list[PosterModelEntry]:
        pattern = "**/*.pptx" if recursive else "*.pptx"
        return self._entries_for_paths(sorted(folder.glob(pattern)), group, read_only=read_only)

    def _entries_for_paths(
        self,
        paths: list[Path],
        group: str,
        *,
        read_only: bool,
    ) -> list[PosterModelEntry]:
        return [self._entry_for(path, group, read_only=read_only) for path in paths if path.is_file()]

    def _entry_for(
        self,
        path: Path,
        group: str,
        *,
        read_only: bool,
        forced_kind: PosterKind | None = None,
    ) -> PosterModelEntry:
        known = self._MODEL_INFO.get(path.name.upper())
        if known is not None:
            display_name, kind, variant, recommended = known
        else:
            stored_kind = self._custom_kind_for(path.name) if group == self.GROUP_CUSTOM else None
            kind = forced_kind or stored_kind or self._infer_kind(path.name)
            variant = "personalizado" if group != self.GROUP_VERSION else "versao"
            display_name = self._friendly_name(path.stem)
            recommended = False
        stat = path.stat()
        slug = self._slug(f"{group}-{path.stem}-{path.parent.name}")
        return PosterModelEntry(
            id=slug,
            name=display_name,
            filename=path.name,
            kind=kind,
            variant=variant,
            group=group,
            path=str(path),
            read_only=read_only,
            recommended=recommended,
            size=stat.st_size,
            modified_at=datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
            metadata={"source": "SR Studio model catalog"},
        )

    def _backup_existing(self, source: Path) -> Path:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        folder = self.versions_root / source.stem
        folder.mkdir(parents=True, exist_ok=True)
        destination = folder / f"{stamp}_antes_substituir.pptx"
        shutil.copy2(source, destination)
        return destination

    def _write_catalog(self, entries: list[PosterModelEntry]) -> None:
        payload = {
            "format": "SRSTUDIO_POSTER_MODEL_CATALOG_1",
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "root": str(self.root),
            "entries": [
                {
                    **asdict(entry),
                    "kind": entry.kind.value,
                }
                for entry in entries
            ],
        }
        temporary = self.catalog_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.catalog_path)

    def _read_catalog(self) -> list[PosterModelEntry]:
        if not self.catalog_path.is_file():
            return []
        try:
            raw = json.loads(self.catalog_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return []
        result: list[PosterModelEntry] = []
        for item in raw.get("entries", []):
            if not isinstance(item, dict):
                continue
            try:
                data = dict(item)
                data["kind"] = PosterKind(str(data.get("kind") or PosterKind.PROMOTION.value))
                result.append(PosterModelEntry(**data))
            except (TypeError, ValueError):
                continue
        return result

    def _custom_kind_for(self, filename: str) -> PosterKind | None:
        mapping = self._read_custom_kinds()
        raw = mapping.get(filename.casefold())
        if not raw:
            return None
        try:
            return PosterKind(raw)
        except ValueError:
            return None

    def _set_custom_kind(self, filename: str, kind: PosterKind) -> None:
        mapping = self._read_custom_kinds()
        mapping[filename.casefold()] = kind.value
        temporary = self.custom_kind_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.custom_kind_path)

    def _read_custom_kinds(self) -> dict[str, str]:
        if not self.custom_kind_path.is_file():
            return {}
        try:
            raw = json.loads(self.custom_kind_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return {}
        return {str(key): str(value) for key, value in raw.items()} if isinstance(raw, dict) else {}

    def _legacy_candidates(self) -> tuple[Path, ...]:
        candidates = {
            Path.cwd() / "modelos",
            Path(sys.argv[0]).resolve().parent / "modelos",
            Path(sys.executable).resolve().parent / "modelos",
        }
        return tuple(sorted(candidates, key=lambda item: str(item).casefold()))

    @staticmethod
    def _copy_if_missing(source: Path, destination: Path) -> bool:
        if destination.exists():
            return False
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(source, destination)
        except OSError:
            return False
        return True

    @staticmethod
    def _infer_kind(filename: str) -> PosterKind:
        text = filename.upper()
        return PosterKind.WHOLESALE if "ATACADO" in text else PosterKind.PROMOTION

    @staticmethod
    def _friendly_name(stem: str) -> str:
        return " ".join(part.capitalize() for part in stem.replace("-", "_").split("_") if part)

    @staticmethod
    def _slug(value: str) -> str:
        cleaned = []
        for char in value.casefold():
            cleaned.append(char if char.isalnum() else "-")
        return "-".join(part for part in "".join(cleaned).split("-") if part)[:96]

    @staticmethod
    def _group_order(group: str) -> int:
        order = {
            PosterModelCatalog.GROUP_OFFICIAL: 0,
            PosterModelCatalog.GROUP_ORIGINAL: 1,
            PosterModelCatalog.GROUP_CUSTOM: 2,
            PosterModelCatalog.GROUP_VERSION: 3,
        }
        return order.get(group, 9)
