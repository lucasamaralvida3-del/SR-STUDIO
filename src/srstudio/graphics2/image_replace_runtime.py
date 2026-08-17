from __future__ import annotations

"""Substituição profissional de imagens no Graphics2.

O editor já persistia crop/foco/zoom, mas não havia um comando atômico para
substituir a imagem-fonte de um node existente. Este runtime adiciona o comando
``replace_image`` sem alterar geometria ou enquadramento do frame.
"""

from copy import deepcopy
from mimetypes import guess_type
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse
import os
import re

from .model import BindingRole, NodeKind
from .package import register_local_asset


def install_image_replace_command(command_module: Any) -> None:
    router_type = command_module.GraphicsCommandRouter
    if bool(getattr(router_type, "_sr_image_replace_installed", False)):
        return

    original_dispatch = router_type.dispatch

    def dispatch(self, command: dict[str, Any]):
        name = str(command.get("name") or "").strip().lower()
        if name != "replace_image":
            return original_dispatch(self, command)

        node_id = str(command.get("node_id") or self.session.anchor_id or "")
        node = self.session.page.node(node_id)
        if node is None or node.kind not in {NodeKind.IMAGE, NodeKind.BACKGROUND}:
            return command_module.CommandResult(False, False, "Selecione uma imagem editável.")
        if self.session.effective_locked(node_id):
            return command_module.CommandResult(False, False, "A imagem está bloqueada.")

        raw_source = str(command.get("source") or command.get("path") or "").strip()
        if not raw_source:
            return command_module.CommandResult(False, False, "Arquivo de imagem não informado.")

        try:
            source = _local_path(raw_source)
            if not source.is_file():
                raise FileNotFoundError(f"Arquivo não encontrado: {source}")
            mime = str(guess_type(source.name)[0] or "")
            if mime and not mime.startswith("image/"):
                raise ValueError("O arquivo selecionado não é uma imagem suportada.")

            old_asset_id = str(node.asset_id or "")
            with self.session.transaction("Substituir imagem"):
                asset = register_local_asset(self.session.document, source, kind="image", mime=mime)
                _fill_asset_dimensions(asset, source)
                node.asset_id = asset.id
                node.visible = True
                node.metadata.pop("graphics2_preview_original_source", None)
                node.metadata.pop("source_url", None)
                node.metadata["bound_image_source"] = str(source)
                node.metadata["image_replaced_by_user"] = True
                node.metadata["previous_asset_id"] = old_asset_id
                _sync_slot_image_snapshot(self.session.page, node_id, str(source), asset.id)
        except Exception as exc:
            return command_module.CommandResult(False, False, f"Não foi possível substituir a imagem: {exc}")

        return command_module.CommandResult(
            True,
            True,
            "Imagem substituída mantendo o enquadramento do card.",
            {"node_id": node_id, "asset_id": node.asset_id, "source": str(source)},
        )

    router_type.dispatch = dispatch
    router_type._sr_image_replace_installed = True


def _local_path(raw: str) -> Path:
    text = str(raw).strip()
    if text.lower().startswith("file:"):
        parsed = urlparse(text)
        path_text = unquote(parsed.path or "")
        if parsed.netloc and parsed.netloc not in {"", "localhost"}:
            path_text = f"//{parsed.netloc}{path_text}"
        if os.name == "nt" and re.match(r"^/[A-Za-z]:/", path_text):
            path_text = path_text[1:]
        text = path_text
    return Path(text).expanduser().resolve()


def _fill_asset_dimensions(asset: Any, source: Path) -> None:
    try:
        from PIL import Image

        with Image.open(source) as image:
            asset.width = int(image.width)
            asset.height = int(image.height)
            if not asset.mime:
                fmt = str(image.format or "").lower()
                if fmt:
                    asset.mime = f"image/{'jpeg' if fmt == 'jpg' else fmt}"
    except Exception:
        # Dimensões são metadado auxiliar; o asset já foi validado como arquivo
        # e o renderer ainda pode abri-lo pelos codecs do Qt.
        return


def _sync_slot_image_snapshot(page: Any, node_id: str, source: str, asset_id: str) -> None:
    for slot in page.slots.values():
        image_node_id = str(slot.node_by_role.get(BindingRole.IMAGE.value) or "")
        extra = slot.metadata.get("extra_bindings")
        extra_image_ids = []
        if isinstance(extra, dict):
            raw = extra.get(BindingRole.IMAGE.value)
            if isinstance(raw, (list, tuple)):
                extra_image_ids = [str(value) for value in raw]
        if node_id != image_node_id and node_id not in extra_image_ids:
            continue
        snapshot = slot.metadata.get("product_snapshot")
        if not isinstance(snapshot, dict):
            snapshot = {}
        else:
            snapshot = deepcopy(snapshot)
        snapshot["image_path"] = source
        snapshot["image_asset_id"] = asset_id
        slot.metadata["product_snapshot"] = snapshot
