from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"expected exactly one match in {path}, got {count}: {old[:80]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


# 1) Wire the already implemented integrity repair and image replacement services
# into the real editor command path.
router = "src/srstudio/graphics2/command_router.py"
replace_once(
    router,
    "from .geometry import SnapEngine, SnapSettings\nfrom .import_bridge import CanvaBindingService\n",
    "from .geometry import SnapEngine, SnapSettings\nfrom .id_repair import repair_legacy_cross_page_ids\nfrom .image_replace import replace_image_source\nfrom .import_bridge import CanvaBindingService\n",
)
replace_once(
    router,
    "    def __init__(self, session: GraphicsSession) -> None:\n        self.session = session\n        self.snap = SnapSettings()\n",
    "    def __init__(self, session: GraphicsSession) -> None:\n        self.session = session\n        # Open-time migration is deliberately outside the undo stack.\n        self.integrity_repair = repair_legacy_cross_page_ids(self.session.document)\n        self.snap = SnapSettings()\n",
)
replace_once(
    router,
    '            "products": list(self.session.document.metadata.get("products") or []),\n        }\n',
    '            "products": list(self.session.document.metadata.get("products") or []),\n            "integrity_repair": self.integrity_repair.to_dict(),\n        }\n',
)
replace_once(
    router,
    '                return CommandResult(True, True, "Enquadramento e crop atualizados.", {"node_id": node_id})\n            if name in {"add_page", "duplicate_page"}:\n',
    '                return CommandResult(True, True, "Enquadramento e crop atualizados.", {"node_id": node_id})\n            if name == "replace_image":\n                node_id = str(command.get("node_id") or self.session.anchor_id or "")\n                if not node_id:\n                    return CommandResult(False, False, "Nenhuma imagem selecionada.")\n                replacement = replace_image_source(\n                    self.session,\n                    node_id,\n                    str(command.get("source") or ""),\n                )\n                return CommandResult(\n                    True,\n                    True,\n                    "Imagem substituída.",\n                    {\n                        "node_id": replacement.node_id,\n                        "asset_id": replacement.asset_id,\n                        "source": replacement.source,\n                        "reused_asset": replacement.reused_asset,\n                    },\n                )\n            if name in {"add_page", "duplicate_page"}:\n',
)

# 2) A native Windows drive path is not a URL scheme. Preserve UNC and file://
# behavior while still rejecting real remote URLs.
image_replace = "src/srstudio/graphics2/image_replace.py"
replace_once(
    image_replace,
    '    parsed = urlparse(raw)\n    if parsed.scheme and parsed.scheme.lower() != "file":\n        raise ValueError("A substituição de imagem aceita somente arquivos locais.")\n\n    if parsed.scheme.lower() == "file":\n        if parsed.netloc and parsed.netloc not in {"", "localhost"}:\n            # UNC: file://server/share/file.png\n            value = f"//{parsed.netloc}{unquote(parsed.path)}"\n        else:\n            value = unquote(parsed.path)\n        if os.name == "nt" and len(value) >= 3 and value[0] == "/" and value[2] == ":":\n            value = value[1:]\n    else:\n        value = raw\n',
    '    is_windows_drive = (\n        len(raw) >= 3\n        and raw[0].isalpha()\n        and raw[1] == ":"\n        and raw[2] in {"\\\\", "/"}\n    )\n    is_unc_path = raw.startswith("\\\\\\\\")\n\n    if is_windows_drive or is_unc_path:\n        value = raw\n    else:\n        parsed = urlparse(raw)\n        if parsed.scheme and parsed.scheme.lower() != "file":\n            raise ValueError("A substituição de imagem aceita somente arquivos locais.")\n\n        if parsed.scheme.lower() == "file":\n            if parsed.netloc and parsed.netloc not in {"", "localhost"}:\n                # UNC: file://server/share/file.png\n                value = f"//{parsed.netloc}{unquote(parsed.path)}"\n            else:\n                value = unquote(parsed.path)\n            if os.name == "nt" and len(value) >= 3 and value[0] == "/" and value[2] == ":":\n                value = value[1:]\n        else:\n            value = raw\n',
)

# 3) Harden invalid packages, preserve scalar numeric representation through
# save->load, and keep embedded provenance after extracting a packaged asset.
package = "src/srstudio/graphics2/package.py"
replace_once(
    package,
    'def load_package(path: str | Path, *, extract_assets_to: str | Path | None = None) -> GraphicsDocument:\n    source = Path(path)\n    with zipfile.ZipFile(source, "r") as archive:\n        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))\n        if manifest.get("format") != PACKAGE_FORMAT:\n            raise ValueError("Pacote não é SR Graphics Engine 2")\n        scene_raw = archive.read("scene.json")\n        if sha256(scene_raw).hexdigest() != manifest.get("scene_sha256"):\n            raise ValueError("Hash do scene.json inválido")\n        document = GraphicsDocument.from_dict(json.loads(scene_raw.decode("utf-8")))\n        if extract_assets_to:\n            destination = Path(extract_assets_to)\n            destination.mkdir(parents=True, exist_ok=True)\n            _extract_assets(document, manifest, archive, destination)\n            _extract_fonts(document, manifest, archive, destination / "fonts")\n    assert_document_integrity(document)\n    return document\n',
    'def load_package(path: str | Path, *, extract_assets_to: str | Path | None = None) -> GraphicsDocument:\n    source = Path(path)\n    try:\n        with zipfile.ZipFile(source, "r") as archive:\n            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))\n            if manifest.get("format") != PACKAGE_FORMAT:\n                raise ValueError("Pacote não é SR Graphics Engine 2")\n            scene_raw = archive.read("scene.json")\n            if sha256(scene_raw).hexdigest() != manifest.get("scene_sha256"):\n                raise ValueError("Hash do scene.json inválido")\n            scene_data = json.loads(scene_raw.decode("utf-8"))\n            document = GraphicsDocument.from_dict(scene_data)\n            # from_dict normalizes page dimensions/guides to float for runtime math.\n            # Restore the JSON scalar representation so repeated package round-trips\n            # remain byte-stable for documents originally authored with integers.\n            raw_pages = list(scene_data.get("pages") or [])\n            for page, raw_page in zip(document.pages, raw_pages):\n                if not isinstance(raw_page, dict):\n                    continue\n                width = raw_page.get("width")\n                height = raw_page.get("height")\n                if isinstance(width, (int, float)):\n                    page.width = width\n                if isinstance(height, (int, float)):\n                    page.height = height\n                page.guides_x = [\n                    value for value in raw_page.get("guides_x") or [] if isinstance(value, (int, float))\n                ]\n                page.guides_y = [\n                    value for value in raw_page.get("guides_y") or [] if isinstance(value, (int, float))\n                ]\n            if extract_assets_to:\n                destination = Path(extract_assets_to)\n                destination.mkdir(parents=True, exist_ok=True)\n                _extract_assets(document, manifest, archive, destination)\n                _extract_fonts(document, manifest, archive, destination / "fonts")\n    except zipfile.BadZipFile as exc:\n        raise ValueError("Pacote SR Scene inválido: arquivo ZIP corrompido.") from exc\n    assert_document_integrity(document)\n    return document\n',
)
replace_once(
    package,
    '            document.assets[asset_id].embedded = False\n            document.assets[asset_id].sha256 = sha256(raw).hexdigest()\n',
    '            # The local extraction is a runtime path; provenance remains that\n            # this asset is embedded in the portable SR Scene package.\n            document.assets[asset_id].embedded = True\n            document.assets[asset_id].sha256 = sha256(raw).hexdigest()\n',
)

# 4) Expose the direct replacement action in the real inspector while preserving
# all existing crop controls. Also add a selected-node fallback used by the
# standalone Qt Quick smoke test.
qml = "src/srstudio/graphics2/qml/ImageInspector.qml"
replace_once(
    qml,
    "import QtQuick.Controls\nimport QtQuick.Layouts\n",
    "import QtQuick.Controls\nimport QtQuick.Dialogs\nimport QtQuick.Layouts\n",
)
replace_once(
    qml,
    "    height: 610\n",
    "    height: 650\n",
)
replace_once(
    qml,
    '        if (!node && scene.editor.selection && scene.editor.selection.length)\n            node = page.nodes[String(scene.editor.selection[0])] || null\n        return node && (node.kind === "image" || node.kind === "background") ? node : null\n',
    '        if (!node && scene.editor.selection && scene.editor.selection.length)\n            node = page.nodes[String(scene.editor.selection[0])] || null\n        if (!node && page.nodes) {\n            for (var nodeId in page.nodes) {\n                if (page.nodes[nodeId] && page.nodes[nodeId].selected) {\n                    node = page.nodes[nodeId]\n                    break\n                }\n            }\n        }\n        return node && (node.kind === "image" || node.kind === "background") ? node : null\n',
)
replace_once(
    qml,
    "    Component.onCompleted: refresh()\n\n    Rectangle {\n",
    '    Component.onCompleted: Qt.callLater(refresh)\n\n    FileDialog {\n        id: replaceImageDialog\n        title: "Selecionar nova imagem"\n        fileMode: FileDialog.OpenFile\n        nameFilters: [\n            "Imagens (*.png *.jpg *.jpeg *.jfif *.webp *.bmp *.gif *.tif *.tiff)",\n            "Todos os arquivos (*)"\n        ]\n        onAccepted: {\n            if (!imageNode)\n                return\n            sceneBridge.dispatch(JSON.stringify({\n                "name": "replace_image",\n                "node_id": imageNode.id,\n                "source": selectedFile.toString()\n            }))\n        }\n    }\n\n    Rectangle {\n',
)
replace_once(
    qml,
    '            RowLayout {\n                Layout.fillWidth: true\n                Label { text: "Encaixe"; color: "#475569"; font.bold: true; Layout.preferredWidth: 56 }\n',
    '            Button {\n                Layout.fillWidth: true\n                text: "Substituir imagem…"\n                onClicked: if (imageNode) replaceImageDialog.open()\n            }\n\n            RowLayout {\n                Layout.fillWidth: true\n                Label { text: "Encaixe"; color: "#475569"; font.bold: true; Layout.preferredWidth: 56 }\n',
)
replace_once(
    qml,
    '                text: "Crop, foco, zoom e espelhamento são persistidos no SR Scene e usados pelo canvas e pela exportação."\n',
    '                text: "A substituição preserva posição, tamanho, crop, rotação e camadas. Crop, foco, zoom e espelhamento são persistidos no SR Scene e usados pelo canvas e pela exportação."\n',
)

print("Alpha 43 validation fixes applied.")
