from __future__ import annotations

"""Fingerprint determinístico da estrutura visual do SR Scene 2.

IDs de runtime e diretórios temporários não participam do hash. O objetivo é
provar que a mesma entrada produz a mesma estrutura visual/semântica em CI e em
máquinas diferentes, além de detectar drift estrutural que um diff de código
não revela.
"""

from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any
import json
import math

from .model import GraphicsDocument, GraphicsNode, GraphicsPage


@dataclass(slots=True, frozen=True)
class PageFingerprint:
    index: int
    name: str
    sha256: str
    nodes: int
    slots: int


@dataclass(slots=True, frozen=True)
class SceneFingerprint:
    schema: str
    sha256: str
    pages: tuple[PageFingerprint, ...]
    nodes: int
    slots: int
    assets: int

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["pages"] = [asdict(page) for page in self.pages]
        return payload


def fingerprint_document(document: GraphicsDocument, *, precision: int = 5) -> SceneFingerprint:
    page_records: list[dict[str, Any]] = []
    page_fingerprints: list[PageFingerprint] = []
    total_nodes = 0
    total_slots = 0
    for index, page in enumerate(document.pages):
        record = _canonical_page(document, page, precision=precision)
        page_hash = _digest(record)
        page_records.append(record)
        total_nodes += len(page.nodes)
        total_slots += len(page.slots)
        page_fingerprints.append(
            PageFingerprint(index=index, name=page.name, sha256=page_hash, nodes=len(page.nodes), slots=len(page.slots))
        )
    envelope = {
        "schema": document.schema,
        "name": str(document.name or ""),
        "pages": page_records,
        "assets": sorted(_asset_identity(asset) for asset in document.assets.values()),
    }
    return SceneFingerprint(
        schema=document.schema,
        sha256=_digest(envelope),
        pages=tuple(page_fingerprints),
        nodes=total_nodes,
        slots=total_slots,
        assets=len(document.assets),
    )


def store_scene_fingerprint(document: GraphicsDocument, *, precision: int = 5) -> SceneFingerprint:
    result = fingerprint_document(document, precision=precision)
    document.metadata["scene_fingerprint"] = result.to_dict()
    return result


def _canonical_page(document: GraphicsDocument, page: GraphicsPage, *, precision: int) -> dict[str, Any]:
    ordered = sorted(page.nodes.values(), key=lambda node: _node_sort_key(document, node, precision))
    canonical_index = {node.id: index for index, node in enumerate(ordered)}
    nodes = [_canonical_node(document, page, node, canonical_index, precision) for node in ordered]
    slots = []
    for slot in page.slots.values():
        roles = {
            str(role): canonical_index[node_id]
            for role, node_id in sorted(slot.node_by_role.items())
            if node_id in canonical_index
        }
        extra_bindings = {}
        raw_extra = slot.metadata.get("extra_bindings") if isinstance(slot.metadata, dict) else None
        if isinstance(raw_extra, dict):
            for role, node_ids in sorted(raw_extra.items()):
                if not isinstance(node_ids, (list, tuple)):
                    continue
                mapped = sorted(canonical_index[node_id] for node_id in node_ids if node_id in canonical_index)
                if mapped:
                    extra_bindings[str(role)] = mapped
        slots.append(
            {
                "name": str(slot.name or ""),
                "roles": roles,
                "extra_bindings": extra_bindings,
                "product_id": str(slot.product_id or ""),
                "confidence": _number(slot.confidence, precision),
                "locked": bool(slot.locked),
            }
        )
    slots.sort(key=lambda item: json.dumps(item, sort_keys=True, ensure_ascii=False, separators=(",", ":")))
    return {
        "name": str(page.name or ""),
        "width": _number(page.width, precision),
        "height": _number(page.height, precision),
        "unit": str(page.unit.value),
        "background": str(page.background or ""),
        "guides_x": sorted(_number(value, precision) for value in page.guides_x),
        "guides_y": sorted(_number(value, precision) for value in page.guides_y),
        "nodes": nodes,
        "slots": slots,
    }


def _canonical_node(
    document: GraphicsDocument,
    page: GraphicsPage,
    node: GraphicsNode,
    canonical_index: dict[str, int],
    precision: int,
) -> dict[str, Any]:
    t = node.transform
    parent = canonical_index.get(node.parent_id) if node.parent_id else None
    children = sorted(canonical_index[child] for child in node.children if child in canonical_index)
    return {
        "kind": str(node.kind.value),
        "name": str(node.name or ""),
        "parent": parent,
        "children": children,
        "z": int(node.z_index),
        "locked": bool(node.locked),
        "visible": bool(node.visible),
        "opacity": _number(node.opacity, precision),
        "transform": {
            "x": _number(t.x, precision),
            "y": _number(t.y, precision),
            "width": _number(t.width, precision),
            "height": _number(t.height, precision),
            "rotation": _number(t.rotation, precision),
            "scale_x": _number(t.scale_x, precision),
            "scale_y": _number(t.scale_y, precision),
            "pivot_x": _number(t.pivot_x, precision),
            "pivot_y": _number(t.pivot_y, precision),
        },
        "text": str(node.text or ""),
        "binding_role": str(node.binding_role.value) if node.binding_role else "",
        "asset": _node_asset_identity(document, node),
        "style": _stable_value(node.style, precision=precision),
        "fidelity": _stable_fidelity_metadata(node.metadata, precision=precision),
    }


def _node_sort_key(document: GraphicsDocument, node: GraphicsNode, precision: int) -> tuple[Any, ...]:
    t = node.transform
    return (
        int(node.z_index),
        str(node.kind.value),
        str(node.name or ""),
        _number(t.y, precision),
        _number(t.x, precision),
        _number(t.width, precision),
        _number(t.height, precision),
        str(node.text or ""),
        _node_asset_identity(document, node),
    )


def _node_asset_identity(document: GraphicsDocument, node: GraphicsNode) -> str:
    if not node.asset_id:
        return ""
    asset = document.assets.get(node.asset_id)
    return _asset_identity(asset) if asset is not None else "missing:" + str(node.asset_id)


def _asset_identity(asset: Any) -> str:
    digest = str(getattr(asset, "sha256", "") or "").strip().lower()
    if digest:
        return "sha256:" + digest
    source = str(getattr(asset, "source", "") or "").strip()
    if not source:
        return ""

    # Assets importados ainda podem não ter SHA persistido antes do primeiro
    # save. Quando o arquivo local existe, use o conteúdo desde já para que o
    # fingerprint pré-save seja idêntico ao fingerprint do pacote reaberto.
    source_path = Path(source)
    try:
        if source_path.is_file():
            hasher = sha256()
            with source_path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    hasher.update(chunk)
            return "sha256:" + hasher.hexdigest()
    except OSError:
        pass

    normalized = source.replace("\\", "/")
    # Caminhos absolutos de cache variam entre máquinas. O nome de mídia PPTX
    # já é content-addressed no importador; para outros assets preservamos os
    # dois últimos componentes para reduzir colisões sem vazar diretório local.
    parts = [part for part in normalized.split("/") if part]
    tail = "/".join(parts[-2:]) if len(parts) >= 2 else (parts[-1] if parts else normalized)
    return "path:" + tail.casefold()


def _stable_fidelity_metadata(metadata: dict[str, Any], *, precision: int) -> dict[str, Any]:
    keys = (
        "slot_id",
        "slot_role",
        "shape_geometry",
        "custom_path",
        "clip_path",
        "template_hidden",
        "source_font_name",
    )
    return {
        key: _stable_value(metadata[key], precision=precision)
        for key in keys
        if key in metadata and metadata[key] not in (None, "", {}, [])
    }


def _stable_value(value: Any, *, precision: int) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _stable_value(item, precision=precision)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if str(key) not in {"embedded_font_path", "bound_image_source", "source_url"}
        }
    if isinstance(value, (list, tuple)):
        return [_stable_value(item, precision=precision) for item in value]
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return _number(value, precision)
    return str(value)


def _number(value: Any, precision: int) -> float | int:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0
    if not math.isfinite(number):
        return 0
    rounded = round(number, max(0, int(precision)))
    if rounded == int(rounded):
        return int(rounded)
    return rounded


def _digest(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(raw).hexdigest()
