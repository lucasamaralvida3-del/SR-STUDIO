from __future__ import annotations

"""Manual image replacement operations for the G2 flyer editor."""

from pathlib import Path
from typing import TYPE_CHECKING

from .model import AssetRef, NodeKind

if TYPE_CHECKING:
    from .operations import GraphicsSession


def _asset_for_source(session: "GraphicsSession", source: str) -> AssetRef:
    normalized = str(Path(source).expanduser()) if source else ""
    for asset in session.document.assets.values():
        if asset.source == normalized or asset.source == source:
            return asset
    asset = AssetRef(
        kind="image",
        source=normalized or source,
        embedded=False,
        metadata={"source": "graphics2-manual-replace"},
    )
    session.document.add_asset(asset)
    return asset


def replace_image(
    session: "GraphicsSession",
    node_id: str,
    source: str,
    *,
    reset_framing: bool = False,
) -> bool:
    """Replace an image/background source while preserving its visual box.

    Crop/focus/zoom/flip are preserved by default because they are properties of
    the template frame. ``reset_framing`` is explicit and undoable.
    """

    node = session.page.node(str(node_id))
    source = str(source or "").strip()
    if (
        node is None
        or node.kind not in {NodeKind.IMAGE, NodeKind.BACKGROUND}
        or session.effective_locked(node.id)
        or not source
    ):
        return False

    with session.transaction("Substituir imagem"):
        asset = _asset_for_source(session, source)
        node.asset_id = asset.id
        node.metadata["bound_image_source"] = asset.source
        node.metadata["manual_image_replacement"] = True
        node.visible = True
        if reset_framing:
            node.style["fit"] = "contain"
            node.style["zoom"] = 1.0
            node.style["focus_x"] = 0.5
            node.style["focus_y"] = 0.5
            node.style["flip_x"] = False
            node.style["flip_y"] = False
            node.style.pop("crop", None)
    return True
