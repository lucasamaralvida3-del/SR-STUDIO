from __future__ import annotations

from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected exactly one match, got {count}: {old[:80]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_qt_host(root: Path) -> None:
    path = root / "src/srstudio/graphics2/qt_host.py"
    replace_once(path, "from .fonts import register_qt_document_fonts\n", "from .fonts import register_qt_document_fonts\nfrom .image_database_runtime import GraphicsImageDatabaseRuntime\n")
    replace_once(
        path,
        "    session = GraphicsSession(context.document)\n    router = GraphicsCommandRouter(session)\n    gate = context.gate or inspect_production_gate(session.document, require_visual_fidelity=False)\n",
        "    session = GraphicsSession(context.document)\n    router = GraphicsCommandRouter(session)\n    image_database = GraphicsImageDatabaseRuntime.from_environment()\n    image_database.attach(session, router)\n    gate = context.gate or inspect_production_gate(session.document, require_visual_fidelity=False)\n",
    )
    replace_once(
        path,
        "            payload = inject_preview_image_urls(router.payload(), session.document)\n            editor = payload.setdefault(\"editor\", {})\n",
        "            payload = inject_preview_image_urls(router.payload(), session.document)\n            image_database.augment_payload(payload)\n            editor = payload.setdefault(\"editor\", {})\n            editor[\"image_database\"] = {\n                \"available\": image_database.available,\n                \"status\": image_database.status,\n                \"root\": str(image_database.library_root),\n                \"error\": image_database.error,\n                \"seed_manifest\": dict(image_database.seed_manifest),\n            }\n",
    )
    replace_once(
        path,
        "    if bridge._recovery_point is not None:\n        details.append(\"recovery disponível\")\n",
        "    if bridge._recovery_point is not None:\n        details.append(\"recovery disponível\")\n    details.append(\"Image DB pronto\" if image_database.available else \"Image DB indisponível\")\n",
    )


def patch_runtime_cache(root: Path) -> None:
    path = root / "src/srstudio/graphics2/image_database_runtime.py"
    replace_once(
        path,
        "        self._lookup_cache: dict[tuple[str, tuple[str, ...]], ProductImageLookupResult] = {}\n        self._session = None\n",
        "        self._lookup_cache: dict[tuple[str, tuple[str, ...]], ProductImageLookupResult] = {}\n        self._validated_assets: dict[str, tuple[int, int, str]] = {}\n        self._session = None\n",
    )
    replace_once(
        path,
        "        if verify_hash and self._sha256_file(path) != canonical_sha:\n            raise ImageDatabaseIntegrityError(f\"Hash da imagem diverge: {image_id}\")\n",
        "        if verify_hash:\n            stat = path.stat()\n            validation_stamp = (stat.st_mtime_ns, stat.st_size, canonical_sha)\n            if self._validated_assets.get(image_id) != validation_stamp:\n                if self._sha256_file(path) != canonical_sha:\n                    raise ImageDatabaseIntegrityError(f\"Hash da imagem diverge: {image_id}\")\n                self._validated_assets[image_id] = validation_stamp\n",
    )


def patch_qml(root: Path) -> None:
    path = root / "src/srstudio/graphics2/qml/GraphicsEditor.qml"
    text = path.read_text(encoding="utf-8")
    marker = "                                    id: productCard\n"
    start = text.find(marker)
    if start < 0:
        raise RuntimeError("productCard delegate not found")
    end_marker = "                                    MouseArea {\n                                        id: productMouse\n"
    end = text.find(end_marker, start)
    if end < 0:
        raise RuntimeError("productMouse marker not found")
    head, block, tail = text[:start], text[start:end], text[end:]

    def local(old: str, new: str) -> None:
        nonlocal block
        count = block.count(old)
        if count != 1:
            raise RuntimeError(f"GraphicsEditor product block expected one match, got {count}: {old[:80]!r}")
        block = block.replace(old, new, 1)

    local("                                    height: 84\n", "                                    height: 116\n")
    local('                                                source: localSource(modelData.image_path || modelData.image || "")\n', '                                                source: localSource(modelData.image_db_preview || modelData.image_path || modelData.image || "")\n')
    local(
        "                                                asynchronous: true\n                                            }\n",
        "                                                asynchronous: true\n                                            }\n                                            Label {\n                                                anchors.centerIn: parent\n                                                visible: !modelData.image_db_preview && !modelData.image_path && !modelData.image\n                                                text: \"SEM\\nIMAGEM\"\n                                                horizontalAlignment: Text.AlignHCenter\n                                                color: \"#94A3B8\"\n                                                font.bold: true\n                                                font.pixelSize: 8\n                                            }\n",
    )
    local(
        '                                            Label { text: modelData.price ? ("R$ " + String(modelData.price).replace(".", ",")) : "Sem preço"; color: "#0F5BD8"; font.bold: true; font.pixelSize: 12 }\n',
        '                                            Label { text: modelData.price ? ("R$ " + String(modelData.price).replace(".", ",")) : "Sem preço"; color: "#0F5BD8"; font.bold: true; font.pixelSize: 12 }\n                                            Label {\n                                                Layout.fillWidth: true\n                                                text: modelData.image_db_message || "Imagem não consultada"\n                                                color: modelData.image_db_status === "match" ? "#15803D" : modelData.image_db_status === "candidates" ? "#B45309" : "#64748B"\n                                                font.pixelSize: 9\n                                                elide: Text.ElideRight\n                                            }\n',
    )
    local(
        '                                        ToolButton { text: "+"; enabled: selectedSlotId !== ""; onClicked: bindProduct(modelData) }\n',
        '                                        ColumnLayout {\n                                            spacing: 1\n                                            ToolButton { text: "+"; enabled: selectedSlotId !== ""; onClicked: bindProduct(modelData) }\n                                            ToolButton {\n                                                text: modelData.image_db_found ? "Escolher outra" : "Buscar imagem"\n                                                font.pixelSize: 8\n                                                onClicked: {\n                                                    var candidates = modelData.image_db_candidates || []\n                                                    if (candidates.length > 0) {\n                                                        imageChooser.open()\n                                                    } else {\n                                                        sceneBridge.dispatch(JSON.stringify({\n                                                            "name": "lookup_product_image",\n                                                            "product_id": String(modelData.id || modelData.product_id || "")\n                                                        }))\n                                                    }\n                                                }\n                                            }\n                                        }\n',
    )

    popup = """                                    Popup {
                                        id: imageChooser
                                        parent: Overlay.overlay
                                        width: Math.min(480, Overlay.overlay ? Overlay.overlay.width - 40 : 480)
                                        height: Math.min(430, 110 + Math.max(1, imageCandidateList.count) * 72)
                                        x: Overlay.overlay ? Math.max(20, (Overlay.overlay.width - width) / 2) : 20
                                        y: Overlay.overlay ? Math.max(20, (Overlay.overlay.height - height) / 2) : 20
                                        modal: true
                                        focus: true
                                        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
                                        background: Rectangle { color: \"#FFFFFF\"; border.color: \"#CBD5E1\"; radius: 8 }
                                        contentItem: ColumnLayout {
                                            spacing: 8
                                            Label { Layout.fillWidth: true; text: \"Imagens para \" + productLabel(productCard.productData); font.bold: true; color: \"#111827\"; elide: Text.ElideRight }
                                            Label { Layout.fillWidth: true; text: \"A aplicação só ocorre quando você escolher um candidato.\"; color: \"#64748B\"; font.pixelSize: 10; wrapMode: Text.WordWrap }
                                            ListView {
                                                id: imageCandidateList
                                                Layout.fillWidth: true
                                                Layout.fillHeight: true
                                                clip: true
                                                spacing: 4
                                                model: productCard.productData.image_db_candidates || []
                                                delegate: ItemDelegate {
                                                    required property var modelData
                                                    width: imageCandidateList.width
                                                    height: 64
                                                    enabled: selectedSlotId !== \"\"
                                                    contentItem: RowLayout {
                                                        spacing: 8
                                                        Rectangle {
                                                            Layout.preferredWidth: 52; Layout.preferredHeight: 52; color: \"#F8FAFC\"; border.color: \"#E2E8F0\"; radius: 4; clip: true
                                                            Image { anchors.fill: parent; anchors.margins: 2; source: localSource(modelData.path || \"\"); fillMode: Image.PreserveAspectFit; asynchronous: true }
                                                        }
                                                        ColumnLayout {
                                                            Layout.fillWidth: true; spacing: 1
                                                            Label { Layout.fillWidth: true; text: modelData.product_name || \"Imagem do banco\"; font.bold: true; color: \"#111827\"; elide: Text.ElideRight }
                                                            Label { Layout.fillWidth: true; text: (modelData.automatic ? \"Match confiável\" : \"Escolha manual\") + \" · \" + Math.round(Number(modelData.confidence || 0) * 100) + \"% · \" + (modelData.reason || \"\"); color: modelData.automatic ? \"#15803D\" : \"#B45309\"; font.pixelSize: 9; elide: Text.ElideRight }
                                                        }
                                                    }
                                                    onClicked: {
                                                        sceneBridge.dispatch(JSON.stringify({
                                                            \"name\": \"apply_product_image\",
                                                            \"slot_id\": selectedSlotId,
                                                            \"product_id\": String(productCard.productData.id || productCard.productData.product_id || \"\"),
                                                            \"image_id\": String(modelData.image_id || \"\")
                                                        }))
                                                        imageChooser.close()
                                                    }
                                                }
                                                Label { anchors.centerIn: parent; visible: imageCandidateList.count === 0; text: \"Imagem não encontrada\"; color: \"#94A3B8\" }
                                            }
                                            Button { Layout.alignment: Qt.AlignRight; text: \"Fechar\"; onClicked: imageChooser.close() }
                                        }
                                    }

"""
    path.write_text(head + block + popup + tail, encoding="utf-8")


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    patch_qt_host(root)
    patch_runtime_cache(root)
    patch_qml(root)
    (root / "scripts/ci/apply_g2_existing_image_db_integration.py").unlink()
    (root / ".github/workflows/g2-existing-image-db-patcher.yml").unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
