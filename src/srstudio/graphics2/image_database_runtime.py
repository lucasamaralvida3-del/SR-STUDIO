from __future__ import annotations

"""Existing SR Studio Image Database adapter for Graphics Engine 2.

This module never creates a second catalog. It resolves the same persistent
``<SR Studio data dir>/images`` library used by the desktop shell and reuses
``SafeImageLibrary`` + ``ProductImageLookupService`` for lookup/ranking.

A packaged seed, when present, is only a bootstrap transport for a clean
installation. It is extracted once into the official persistent library root;
all runtime reads/writes continue against that single root.
"""

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from types import MethodType
from typing import Any, Iterable
import json
import os
import shutil
import sys
import tempfile
import zipfile

from srstudio.images.association import normalize_product_name
from srstudio.images.lookup import ProductImageCandidate, ProductImageLookupResult, ProductImageLookupService
from srstudio.images.safe_library import ImageLibraryCorruptionError, SafeImageLibrary

SEED_SCHEMA = "SRSTUDIO_IMAGE_DB_SEED_1"
DEFAULT_DATA_DIR = Path.home() / ".srstudio5"
DATA_DIR_ENV = "SR_STUDIO_DATA_DIR"
SEED_ENV = "SR_STUDIO_IMAGE_DB_SEED"


class ImageDatabaseIntegrityError(RuntimeError):
    """Raised when Image Database state cannot be trusted."""


class GraphicsImageDatabaseRuntime:
    def __init__(
        self,
        data_dir: str | Path | None = None,
        *,
        seed_path: str | Path | None = None,
        require_library: bool = False,
    ) -> None:
        self.data_dir = self.resolve_data_dir(data_dir)
        self.library_root = self.data_dir / "images"
        self.seed_path = Path(seed_path).expanduser().resolve() if seed_path else self.discover_seed()
        self.require_library = bool(require_library)
        self.library: SafeImageLibrary | None = None
        self.lookup_service: ProductImageLookupService | None = None
        self.status = "uninitialized"
        self.error = ""
        self.seed_manifest: dict[str, Any] = {}
        self._lookup_cache: dict[tuple[str, tuple[str, ...]], ProductImageLookupResult] = {}
        self._validated_assets: dict[str, tuple[int, int, str]] = {}
        self._session = None
        self._original_bind_product = None
        self._original_dispatch = None
        self._initialize()

    @classmethod
    def from_environment(cls, *, require_library: bool = False) -> "GraphicsImageDatabaseRuntime":
        return cls(None, require_library=require_library)

    @staticmethod
    def resolve_data_dir(value: str | Path | None = None) -> Path:
        configured = str(value or os.environ.get(DATA_DIR_ENV) or "").strip()
        return Path(configured).expanduser().resolve() if configured else DEFAULT_DATA_DIR.expanduser().resolve()

    @staticmethod
    def discover_seed() -> Path | None:
        configured = str(os.environ.get(SEED_ENV) or "").strip()
        if configured:
            candidate = Path(configured).expanduser()
            return candidate.resolve() if candidate.is_file() else None
        if not bool(getattr(sys, "frozen", False)):
            return None
        executable_root = Path(sys.executable).resolve().parent
        candidates = (
            executable_root / "ImageDatabaseSeed" / "image-db-library-v1.zip",
            executable_root.parent / "ImageDatabaseSeed" / "image-db-library-v1.zip",
        )
        return next((path for path in candidates if path.is_file()), None)

    @property
    def available(self) -> bool:
        return self.library is not None and self.lookup_service is not None and self.status == "ready"

    def _initialize(self) -> None:
        try:
            index = self.library_root / "index.json"
            if not index.is_file() and self.seed_path is not None:
                self._bootstrap_seed(self.seed_path)
            if not index.is_file():
                self.status = "missing"
                self.error = f"Catálogo de imagens ausente: {index}"
                if self.require_library:
                    raise ImageDatabaseIntegrityError(self.error)
                return
            library = SafeImageLibrary(self.library_root)
            self._validate_library_index(library, verify_hashes=False)
            self.library = library
            self.lookup_service = ProductImageLookupService(library)
            self.status = "ready"
        except Exception as exc:
            self.status = "invalid"
            self.error = f"{type(exc).__name__}: {exc}"
            if self.require_library:
                raise

    def _bootstrap_seed(self, seed: Path) -> None:
        if self.library_root.joinpath("index.json").exists():
            return
        manifest, payload = self._read_seed(seed)
        self._validate_seed_manifest(manifest, payload)
        parent = self.library_root.parent
        parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix="image-db-seed-", dir=parent))
        try:
            assets_dir = staging / "assets"
            assets_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(seed) as archive:
                for info in archive.infolist():
                    name = info.filename.replace("\\", "/")
                    if info.is_dir() or not name.startswith("assets/"):
                        continue
                    relative = Path(name)
                    if relative.is_absolute() or ".." in relative.parts or len(relative.parts) != 2:
                        raise ImageDatabaseIntegrityError(f"Caminho inseguro no seed: {name}")
                    target = assets_dir / relative.name
                    with archive.open(info) as source, target.open("wb") as output:
                        shutil.copyfileobj(source, output)

            relocated: dict[str, dict[str, Any]] = {}
            for asset_id, raw in payload.items():
                data = dict(raw)
                if str(data.get("id") or "") != str(asset_id):
                    raise ImageDatabaseIntegrityError(f"image_id inconsistente no seed: {asset_id}")
                seed_relative = str(data.get("path") or "").replace("\\", "/")
                filename = Path(seed_relative).name
                target = assets_dir / filename
                if not target.is_file():
                    raise ImageDatabaseIntegrityError(f"Arquivo referenciado ausente no seed: {asset_id}")
                data["path"] = str((self.library_root / "assets" / filename).resolve())
                relocated[str(asset_id)] = data

            (staging / "index.json").write_text(
                json.dumps(relocated, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            (staging / "seed-manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            check = SafeImageLibrary(staging)
            self._validate_library_index(check, verify_hashes=True, path_root=staging)
            if self.library_root.exists():
                entries = list(self.library_root.iterdir())
                only_empty_assets = bool(entries) and all(
                    entry.name == "assets" and entry.is_dir() and not any(entry.iterdir())
                    for entry in entries
                )
                if entries and not only_empty_assets:
                    raise ImageDatabaseIntegrityError(
                        f"Banco existente apareceu durante bootstrap: {self.library_root}"
                    )
                shutil.rmtree(self.library_root, ignore_errors=False)
            staging.replace(self.library_root)
            staging = Path()
        finally:
            if staging and staging.exists():
                shutil.rmtree(staging, ignore_errors=True)

    @staticmethod
    def _read_seed(seed: Path) -> tuple[dict[str, Any], dict[str, Any]]:
        if not seed.is_file():
            raise ImageDatabaseIntegrityError(f"Seed do Image Database ausente: {seed}")
        try:
            with zipfile.ZipFile(seed) as archive:
                names = set(archive.namelist())
                if "seed-manifest.json" not in names or "index.json" not in names:
                    raise ImageDatabaseIntegrityError("Seed sem manifesto ou index.json")
                manifest = json.loads(archive.read("seed-manifest.json").decode("utf-8"))
                payload = json.loads(archive.read("index.json").decode("utf-8"))
        except (OSError, zipfile.BadZipFile, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ImageDatabaseIntegrityError(f"Seed inválido: {exc}") from exc
        if not isinstance(manifest, dict) or not isinstance(payload, dict):
            raise ImageDatabaseIntegrityError("Seed deve conter objetos JSON válidos")
        return manifest, payload

    @staticmethod
    def _require(mapping: dict[str, Any], key: str) -> Any:
        if key not in mapping:
            raise ImageDatabaseIntegrityError(f"Campo obrigatório ausente: {key}")
        return mapping[key]

    def _validate_seed_manifest(self, manifest: dict[str, Any], payload: dict[str, Any]) -> None:
        if self._require(manifest, "schema") != SEED_SCHEMA:
            raise ImageDatabaseIntegrityError("Schema do seed não reconhecido")
        expected_images = self._require(manifest, "total_images")
        expected_products = self._require(manifest, "total_products")
        expected_index_sha = str(self._require(manifest, "index_sha256")).lower()
        if type(expected_images) is not int or expected_images <= 0:
            raise ImageDatabaseIntegrityError("total_images inválido no seed")
        if type(expected_products) is not int or expected_products <= 0:
            raise ImageDatabaseIntegrityError("total_products inválido no seed")
        if len(payload) != expected_images:
            raise ImageDatabaseIntegrityError(
                f"Contagem do seed diverge: index={len(payload)} manifest={expected_images}"
            )
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        if sha256(canonical).hexdigest() != expected_index_sha:
            raise ImageDatabaseIntegrityError("SHA-256 lógico do index do seed diverge")
        for key in ("catalog_version", "source_release", "source_artifact", "provenance_status", "dedup_status"):
            value = self._require(manifest, key)
            if value in (None, ""):
                raise ImageDatabaseIntegrityError(f"Campo obrigatório vazio no seed: {key}")
        self.seed_manifest = dict(manifest)

    def _validate_library_index(
        self,
        library: SafeImageLibrary,
        *,
        verify_hashes: bool,
        path_root: Path | None = None,
    ) -> dict[str, int]:
        try:
            payload = library._load()
        except ImageLibraryCorruptionError:
            raise
        if not payload:
            raise ImageDatabaseIntegrityError(f"Catálogo de imagens vazio: {library.index_path}")
        accepted = pending = 0
        root = (path_root or library.root).resolve()
        assets_root = (root / "assets").resolve()
        for asset_id, raw in payload.items():
            if not isinstance(raw, dict):
                raise ImageDatabaseIntegrityError(f"Registro inválido no Image DB: {asset_id}")
            if str(self._require(raw, "id")) != str(asset_id):
                raise ImageDatabaseIntegrityError(f"image_id inexistente/inconsistente: {asset_id}")
            metadata = self._require(raw, "metadata")
            if not isinstance(metadata, dict):
                raise ImageDatabaseIntegrityError(f"metadata inválido: {asset_id}")
            canonical_sha = str(self._require(metadata, "sha256_full")).strip().lower()
            if len(canonical_sha) != 64 or any(ch not in "0123456789abcdef" for ch in canonical_sha):
                raise ImageDatabaseIntegrityError(f"SHA-256 ausente/inválido: {asset_id}")
            provenance = metadata.get("source_provenance") or metadata.get("provenance")
            if not provenance:
                raise ImageDatabaseIntegrityError(f"Provenance ausente: {asset_id}")
            raw_path = Path(str(self._require(raw, "path")))
            path = raw_path
            if path_root is not None:
                path = assets_root / raw_path.name
            else:
                path = path.expanduser().resolve()
                try:
                    path.relative_to(assets_root)
                except ValueError as exc:
                    raise ImageDatabaseIntegrityError(
                        f"Arquivo do Image DB fora do root oficial: {asset_id}: {path}"
                    ) from exc
            if not path.is_file():
                raise ImageDatabaseIntegrityError(f"Arquivo referenciado ausente: {asset_id}: {path}")
            if verify_hashes and self._sha256_file(path) != canonical_sha:
                raise ImageDatabaseIntegrityError(f"Hash físico diverge: {asset_id}")
            status = str(self._require(raw, "review_status"))
            if status == "accepted":
                accepted += 1
            elif status == "pending":
                pending += 1
        return {"total_images": len(payload), "accepted": accepted, "pending": pending}

    def validate_full(self) -> dict[str, int]:
        if self.library is None:
            raise ImageDatabaseIntegrityError(self.error or "Image Database indisponível")
        return self._validate_library_index(self.library, verify_hashes=True)

    def lookup_product(
        self,
        product_name: str,
        *,
        aliases: Iterable[str] = (),
        alternatives: int = 4,
    ) -> ProductImageLookupResult:
        if not self.available or self.lookup_service is None:
            return ProductImageLookupResult(None, (), 0.0)
        normalized = normalize_product_name(product_name)
        alias_tuple = tuple(str(value) for value in aliases if str(value).strip())
        cache_key = (normalized, tuple(normalize_product_name(value) for value in alias_tuple))
        cached = self._lookup_cache.get(cache_key)
        if cached is not None:
            return cached
        result = self.lookup_service.find_image(
            product_name,
            aliases=alias_tuple,
            alternatives=max(0, alternatives),
        )
        self._lookup_cache[cache_key] = result
        return result

    def product_candidates(self, product: dict[str, Any], *, limit: int = 5) -> list[dict[str, Any]]:
        if not self.available or self.library is None:
            return []
        name = self._product_name(product)
        aliases = self._product_aliases(product)
        lookup = self.lookup_product(name, aliases=aliases, alternatives=max(3, limit))
        rows: list[dict[str, Any]] = []
        seen: set[str] = set()

        def add(candidate: ProductImageCandidate, *, automatic: bool) -> None:
            asset = candidate.asset
            asset_id = str(getattr(asset, "id", ""))
            if not asset_id or asset_id in seen:
                return
            self._validate_asset(asset, verify_hash=True)
            seen.add(asset_id)
            rows.append(self._candidate_dict(candidate, automatic=automatic))

        if lookup.best_match is not None:
            add(lookup.best_match, automatic=True)
        for candidate in lookup.alternatives:
            add(candidate, automatic=False)

        for asset in self.library.find_for_product(name):
            if len(rows) >= limit:
                break
            asset_id = str(getattr(asset, "id", ""))
            if not asset_id or asset_id in seen or str(getattr(asset, "review_status", "")) == "rejected":
                continue
            candidate = ProductImageCandidate(
                asset=asset,
                score=round(max(0.0, min(1.0, float(getattr(asset, "confidence", 0.0)))), 6),
                reason="candidato exato · revisão",
                match_type="review-required",
                quality_score=float((getattr(asset, "metadata", {}) or {}).get("quality_score") or 0.0),
                identity_score=1.0,
                provenance=ProductImageLookupService._asset_provenance(asset),
            )
            add(candidate, automatic=False)
        return rows[:limit]

    def augment_payload(self, payload: dict[str, Any]) -> None:
        editor = payload.get("editor")
        if not isinstance(editor, dict):
            return
        products = editor.get("products")
        if not isinstance(products, list):
            return
        for product in products:
            if not isinstance(product, dict):
                continue
            name = self._product_name(product)
            normalized = normalize_product_name(name)
            product["image_db_normalized_name"] = normalized
            if not self.available:
                product["image_db_status"] = "unavailable"
                product["image_db_message"] = self.error or "Banco de Imagens indisponível"
                product["image_db_candidates"] = []
                product["image_db_preview"] = ""
                product["image_db_found"] = False
                continue
            candidates = self.product_candidates(product)
            confident = next((row for row in candidates if row["automatic"]), None)
            product["image_db_candidates"] = candidates
            product["image_db_found"] = confident is not None
            product["image_db_preview"] = str(confident["path"]) if confident else ""
            product["image_db_confidence"] = float(confident["confidence"]) if confident else 0.0
            if confident:
                product["image_db_status"] = "match"
                product["image_db_message"] = f"Imagem encontrada · {confident['confidence']:.0%}"
            elif candidates:
                product["image_db_status"] = "candidates"
                product["image_db_message"] = f"{len(candidates)} candidato(s) · escolha manual"
            else:
                product["image_db_status"] = "missing"
                product["image_db_message"] = "Imagem não encontrada"

    def attach(self, session: Any, router: Any) -> None:
        if self._session is session:
            return
        self._session = session
        original_bind = session.bind_product
        original_dispatch = router.dispatch
        self._original_bind_product = original_bind
        self._original_dispatch = original_dispatch

        def bind_product(instance: Any, slot_id: str, product: dict[str, Any]) -> bool:
            prepared, selected = self.prepare_product_for_binding(product)
            changed = original_bind(slot_id, prepared)
            if selected is not None and self.library is not None:
                self.library.record_use(selected["image_id"])
            slot = instance.page.slots.get(str(slot_id))
            if slot is not None:
                slot.metadata["image_db_lookup"] = deepcopy(selected or {
                    "status": "not-found",
                    "normalized_name": normalize_product_name(self._product_name(product)),
                })
            return bool(changed)

        session.bind_product = MethodType(bind_product, session)

        def dispatch(instance: Any, command: dict[str, Any]):
            name = str(command.get("name") or "").strip().lower()
            if name == "lookup_product_image":
                product = self._find_product(instance.session.document, str(command.get("product_id") or ""))
                if product is None:
                    return self._command_result(False, False, "Produto não encontrado.")
                rows = self.product_candidates(product)
                if not rows:
                    return self._command_result(True, False, "Imagem não encontrada.", {"candidates": []})
                return self._command_result(
                    True,
                    False,
                    f"{len(rows)} candidato(s) de imagem.",
                    {"candidates": rows},
                )
            if name == "apply_product_image":
                return self._apply_product_image_command(instance, command)
            return original_dispatch(command)

        router.dispatch = MethodType(dispatch, router)

    def prepare_product_for_binding(self, product: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
        prepared = deepcopy(product)
        if self._explicit_image(prepared):
            return prepared, None
        candidates = self.product_candidates(prepared)
        confident = next((row for row in candidates if row["automatic"]), None)
        if confident is None:
            for key in ("image_path", "image", "image_uri", "image_asset_id"):
                prepared.pop(key, None)
            return prepared, None
        prepared["image_path"] = confident["path"]
        prepared["image_db_image_id"] = confident["image_id"]
        prepared["image_db_confidence"] = confident["confidence"]
        prepared["image_db_match_type"] = confident["match_type"]
        prepared["image_db_source"] = confident["source"]
        return prepared, {
            **confident,
            "status": "auto-applied",
            "normalized_name": normalize_product_name(self._product_name(product)),
        }

    def _apply_product_image_command(self, router: Any, command: dict[str, Any]):
        if not self.available or self.library is None or self._original_bind_product is None:
            return self._command_result(False, False, self.error or "Banco de Imagens indisponível.")
        slot_id = str(command.get("slot_id") or "")
        product_id = str(command.get("product_id") or "")
        image_id = str(command.get("image_id") or "")
        if not slot_id or slot_id not in router.session.page.slots:
            return self._command_result(False, False, "Smart Slot não encontrado.")
        product = self._find_product(router.session.document, product_id)
        if product is None:
            slot = router.session.page.slots[slot_id]
            snapshot = slot.metadata.get("product_snapshot")
            product = deepcopy(snapshot) if isinstance(snapshot, dict) else None
        if product is None:
            return self._command_result(False, False, "Produto não encontrado.")
        asset = self._asset_by_id(image_id)
        if asset is None:
            return self._command_result(False, False, "image_id inexistente no Banco de Imagens.")
        if str(getattr(asset, "review_status", "")) == "rejected":
            return self._command_result(False, False, "Imagem rejeitada no Banco de Imagens.")
        self._validate_asset(asset, verify_hash=True)

        prepared = deepcopy(product)
        prepared["image_path"] = str(asset.path)
        prepared["image_db_image_id"] = str(asset.id)
        prepared["image_db_confidence"] = 1.0
        prepared["image_db_match_type"] = "manual-confirmation"
        prepared["image_db_source"] = str(getattr(asset, "source", "") or "image-db")
        changed = bool(self._original_bind_product(slot_id, prepared))
        self.record_manual_confirmation(product, asset)
        self.library.record_use(str(asset.id))
        slot = router.session.page.slots.get(slot_id)
        if slot is not None:
            slot.metadata["image_db_lookup"] = {
                "status": "manual-confirmed",
                "image_id": str(asset.id),
                "normalized_name": normalize_product_name(self._product_name(product)),
                "confidence": 1.0,
                "source": str(getattr(asset, "source", "") or "image-db"),
            }
        self._lookup_cache.clear()
        return self._command_result(
            True,
            changed,
            "Imagem aplicada e associação confirmada no Banco de Imagens.",
            {"image_id": str(asset.id), "slot_id": slot_id},
        )

    def record_manual_confirmation(self, product: dict[str, Any], asset: Any) -> None:
        if self.library is None:
            raise ImageDatabaseIntegrityError("Banco de Imagens indisponível")
        name = self._product_name(product)
        normalized = normalize_product_name(name)
        if not normalized:
            raise ValueError("Produto sem nome para associação de imagem.")
        current_metadata = dict(getattr(asset, "metadata", {}) or {})
        associations = list(current_metadata.get("manual_associations") or [])
        row = {
            "product_normalized_name": normalized,
            "selected_image_id": str(asset.id),
            "source": str(getattr(asset, "source", "") or "image-db"),
            "confidence": 1.0,
            "manual_confirmation": True,
            "confirmed_at": datetime.now(timezone.utc).isoformat(),
        }
        if not any(
            isinstance(item, dict)
            and item.get("product_normalized_name") == normalized
            and item.get("selected_image_id") == str(asset.id)
            for item in associations
        ):
            associations.append(row)
        aliases = tuple(sorted({
            *(str(value) for value in (getattr(asset, "aliases", ()) or ()) if str(value).strip()),
            name.strip(),
            normalized,
        }))
        self.library.update_metadata(
            str(asset.id),
            aliases=aliases,
            confidence=1.0,
            review_status="accepted",
            metadata={**current_metadata, "manual_associations": associations},
        )

    def _asset_by_id(self, image_id: str):
        if self.library is None:
            return None
        payload = self.library._load()
        raw = payload.get(str(image_id))
        return self.library._asset(raw) if isinstance(raw, dict) else None

    def _validate_asset(self, asset: Any, *, verify_hash: bool) -> None:
        if self.library is None:
            raise ImageDatabaseIntegrityError("Banco de Imagens indisponível")
        image_id = str(getattr(asset, "id", "") or "")
        if not image_id:
            raise ImageDatabaseIntegrityError("image_id ausente")
        payload = self.library._load()
        if image_id not in payload:
            raise ImageDatabaseIntegrityError(f"image_id inexistente: {image_id}")
        metadata = dict(getattr(asset, "metadata", {}) or {})
        canonical_sha = str(metadata.get("sha256_full") or "").strip().lower()
        if len(canonical_sha) != 64:
            raise ImageDatabaseIntegrityError(f"SHA-256 ausente: {image_id}")
        if not (metadata.get("source_provenance") or metadata.get("provenance")):
            raise ImageDatabaseIntegrityError(f"Provenance ausente: {image_id}")
        path = Path(str(getattr(asset, "path", "") or "")).expanduser().resolve()
        try:
            path.relative_to(self.library.assets_dir.resolve())
        except ValueError as exc:
            raise ImageDatabaseIntegrityError(f"Imagem fora do Banco SR: {image_id}") from exc
        if not path.is_file():
            raise ImageDatabaseIntegrityError(f"Arquivo de imagem ausente: {image_id}")
        if verify_hash:
            stat = path.stat()
            validation_stamp = (stat.st_mtime_ns, stat.st_size, canonical_sha)
            if self._validated_assets.get(image_id) != validation_stamp:
                if self._sha256_file(path) != canonical_sha:
                    raise ImageDatabaseIntegrityError(f"Hash da imagem diverge: {image_id}")
                self._validated_assets[image_id] = validation_stamp

    @staticmethod
    def _candidate_dict(candidate: ProductImageCandidate, *, automatic: bool) -> dict[str, Any]:
        asset = candidate.asset
        return {
            "image_id": str(getattr(asset, "id", "")),
            "path": str(getattr(asset, "path", "")),
            "product_name": str(getattr(asset, "product_name", "") or getattr(asset, "product_key", "")),
            "confidence": float(candidate.score),
            "identity_score": float(candidate.identity_score),
            "quality_score": float(candidate.quality_score),
            "reason": str(candidate.reason),
            "match_type": str(candidate.match_type),
            "source": str(getattr(asset, "source", "")),
            "review_status": str(getattr(asset, "review_status", "")),
            "automatic": bool(automatic),
            "provenance_count": len(candidate.provenance),
        }

    @staticmethod
    def _product_name(product: dict[str, Any]) -> str:
        return str(
            product.get("display_name")
            or product.get("name")
            or product.get("original_name")
            or ""
        ).strip()

    @staticmethod
    def _product_aliases(product: dict[str, Any]) -> tuple[str, ...]:
        values: list[str] = []
        raw = product.get("aliases")
        if isinstance(raw, (list, tuple)):
            values.extend(str(item) for item in raw if str(item).strip())
        metadata = product.get("metadata")
        if isinstance(metadata, dict):
            raw_meta = metadata.get("aliases")
            if isinstance(raw_meta, (list, tuple)):
                values.extend(str(item) for item in raw_meta if str(item).strip())
        return tuple(values)

    @staticmethod
    def _explicit_image(product: dict[str, Any]) -> str:
        return str(
            product.get("image_path")
            or product.get("image")
            or product.get("image_uri")
            or product.get("image_asset_id")
            or ""
        ).strip()

    @staticmethod
    def _find_product(document: Any, product_id: str) -> dict[str, Any] | None:
        products = document.metadata.get("products") if isinstance(document.metadata, dict) else None
        if not isinstance(products, list):
            return None
        for product in products:
            if not isinstance(product, dict):
                continue
            candidate = str(product.get("id") or product.get("product_id") or "")
            if candidate == product_id:
                return deepcopy(product)
        return None

    @staticmethod
    def _command_result(ok: bool, changed: bool, message: str, payload: dict[str, Any] | None = None):
        from .command_router import CommandResult
        return CommandResult(ok, changed, message, payload)

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest().lower()
