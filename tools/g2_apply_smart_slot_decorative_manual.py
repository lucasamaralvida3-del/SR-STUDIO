from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected exactly one match, found {count}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_import_bridge() -> None:
    path = "src/srstudio/graphics2/import_bridge.py"
    replace_once(
        path,
        "from .semantic_recovery import recover_canva_semantic_cards\nfrom .smart_slot_import_reset import reset_new_pptx_import_product_content\n",
        "from .semantic_recovery import recover_canva_semantic_cards\nfrom .smart_slot_detection import consolidate_smart_slot_false_positives\nfrom .smart_slot_geometry import refresh_smart_slot_geometry\nfrom .smart_slot_import_reset import reset_new_pptx_import_product_content\n",
    )
    replace_once(
        path,
        "        recover_canva_semantic_cards(document)\n        if structure is not None:\n",
        "        recover_canva_semantic_cards(document)\n        if structure is not None:\n"
        "            # Final semantic arbitration: recovered PriceBlocks/backplates\n"
        "            # may be useful intermediate candidates, but artwork alone is\n"
        "            # never sufficient product identity. This pass removes/merges\n"
        "            # false Smart Slots without touching any visual node.\n"
        "            consolidate_smart_slot_false_positives(document)\n"
        "            refresh_smart_slot_geometry(document)\n",
    )


def patch_geometry() -> None:
    path = "src/srstudio/graphics2/smart_slot_geometry.py"
    old = '''        final = _bounds(page, included) or core
        if final is None and card is not None:
            raw = card.get("bounds")
            if isinstance(raw, dict):
                final = _rect(raw)
        if final is None:
            final = Rect()

        label = _slot_label(page, slot)
        source_group_id = str((card or {}).get("metadata", {}).get("source_group_id") or slot.metadata.get("source_group_id") or "")
        entry = SlotGeometryEntry(
            page_id=page.id,
            slot_id=slot.id,
            product_id=slot.product_id,
            label=label,
            source_group_id=source_group_id,
            bound_node_ids=list(ids),
            included_node_ids=list(dict.fromkeys(included)),
            excluded_shared_node_ids=excluded_shared,
            excluded_large_node_ids=excluded_large,
            bounds=_rect_dict(final),
        )
        entries[slot.id] = entry
        final_bounds[slot.id] = final

        slot.metadata["effective_bounds"] = _rect_dict(final)
        slot.metadata["effective_node_ids"] = list(entry.included_node_ids)
        slot.metadata["excluded_shared_node_ids"] = list(excluded_shared)
        slot.metadata["excluded_large_node_ids"] = list(excluded_large)
        slot.metadata["geometry_source"] = "bindings+exclusive-card-members"
        slot.metadata["geometry_version"] = 1
'''
    new = '''        auto_final = _bounds(page, included) or core
        if auto_final is None and card is not None:
            raw = card.get("bounds")
            if isinstance(raw, dict):
                auto_final = _rect(raw)
        if auto_final is None:
            auto_final = Rect()

        # The first automatic geometry is the restore point. A normal refresh
        # may update diagnostics, but it cannot override explicit user bounds.
        slot.metadata["auto_detected_bounds"] = _rect_dict(auto_final)
        original = _metadata_rect(slot.metadata.get("original_detected_bounds"))
        if original is None and _area(auto_final) > 0:
            original = auto_final
            slot.metadata["original_detected_bounds"] = _rect_dict(auto_final)

        manual = _metadata_rect(slot.metadata.get("user_adjusted_bounds"))
        adjustment_source = str(slot.metadata.get("adjustment_source") or "")
        if adjustment_source == "manual" and manual is not None:
            final = manual
            geometry_source = "manual"
        elif adjustment_source == "auto-restored" and original is not None:
            final = original
            geometry_source = "original-detected-bounds"
        else:
            final = auto_final
            geometry_source = "bindings+exclusive-card-members"

        label = _slot_label(page, slot)
        source_group_id = str((card or {}).get("metadata", {}).get("source_group_id") or slot.metadata.get("source_group_id") or "")
        entry = SlotGeometryEntry(
            page_id=page.id,
            slot_id=slot.id,
            product_id=slot.product_id,
            label=label,
            source_group_id=source_group_id,
            bound_node_ids=list(ids),
            included_node_ids=list(dict.fromkeys(included)),
            excluded_shared_node_ids=excluded_shared,
            excluded_large_node_ids=excluded_large,
            bounds=_rect_dict(final),
        )
        entries[slot.id] = entry
        final_bounds[slot.id] = final

        slot.metadata["effective_bounds"] = _rect_dict(final)
        slot.metadata["effective_node_ids"] = list(entry.included_node_ids)
        slot.metadata["excluded_shared_node_ids"] = list(excluded_shared)
        slot.metadata["excluded_large_node_ids"] = list(excluded_large)
        slot.metadata["geometry_source"] = geometry_source
        slot.metadata["geometry_version"] = 2
'''
    replace_once(path, old, new)
    replace_once(
        path,
        '''def _rect(raw: dict[str, Any]) -> Rect:
    return Rect(
        float(raw.get("x") or 0.0),
        float(raw.get("y") or 0.0),
        max(0.0, float(raw.get("width") or 0.0)),
        max(0.0, float(raw.get("height") or 0.0)),
    ).normalized()


def _rect_dict(rect: Rect) -> dict[str, float]:
''',
        '''def _rect(raw: dict[str, Any]) -> Rect:
    return Rect(
        float(raw.get("x") or 0.0),
        float(raw.get("y") or 0.0),
        max(0.0, float(raw.get("width") or 0.0)),
        max(0.0, float(raw.get("height") or 0.0)),
    ).normalized()


def _metadata_rect(raw: object) -> Rect | None:
    if not isinstance(raw, dict):
        return None
    rect = _rect(raw)
    return rect if _area(rect) > 0 else None


def _rect_dict(rect: Rect) -> dict[str, float]:
''',
    )


def patch_router() -> None:
    path = "src/srstudio/graphics2/command_router.py"
    replace_once(
        path,
        "from .semantic_blocks import semantic_block, semantic_member_ids, semantic_owner\n",
        "from .semantic_blocks import semantic_block, semantic_member_ids, semantic_owner\n"
        "from .smart_slot_manual import (\n"
        "    mark_slot_non_product,\n"
        "    merge_slot_manually,\n"
        "    restore_auto_slot_bounds,\n"
        "    set_manual_slot_bounds,\n"
        "    snap_bounds_to_grid,\n"
        ")\n",
    )
    insert = '''            if name in {"adjust_smart_slot", "set_smart_slot_bounds"}:
                slot_id = str(command.get("slot_id") or "")
                if slot_id not in self.session.page.slots:
                    return CommandResult(False, False, "Smart Slot não encontrado.")
                required = ("x", "y", "width", "height")
                if any(key not in command for key in required):
                    return CommandResult(False, False, "Bounds x/y/width/height são obrigatórios.")
                raw_bounds = {key: float(command[key]) for key in required}
                use_snap = bool(command.get("snap", False)) and bool(self.snap.enabled)
                bounds = snap_bounds_to_grid(
                    raw_bounds,
                    spacing=float(self.snap.grid_spacing),
                    enabled=use_snap,
                    page=self.session.page,
                )
                applied = set_manual_slot_bounds(self.session, slot_id, **bounds)
                return CommandResult(True, True, "Área do Smart Slot ajustada.", {"slot_id": slot_id, "bounds": applied})
            if name == "restore_smart_slot_auto":
                slot_id = str(command.get("slot_id") or "")
                if slot_id not in self.session.page.slots:
                    return CommandResult(False, False, "Smart Slot não encontrado.")
                bounds = restore_auto_slot_bounds(self.session, slot_id)
                return CommandResult(True, True, "Detecção automática do Smart Slot restaurada.", {"slot_id": slot_id, "bounds": bounds})
            if name in {"mark_smart_slot_non_product", "delete_smart_slot"}:
                slot_id = str(command.get("slot_id") or "")
                if slot_id not in self.session.page.slots:
                    return CommandResult(False, False, "Smart Slot não encontrado.")
                reason = "manual-non-product" if name == "mark_smart_slot_non_product" else "manual-slot-delete"
                mark_slot_non_product(self.session, slot_id, reason=reason)
                return CommandResult(True, True, "Smart Slot removido semanticamente; conteúdo visual preservado.", {"slot_id": slot_id})
            if name == "merge_smart_slots":
                source_slot_id = str(command.get("source_slot_id") or command.get("slot_id") or "")
                target_slot_id = str(command.get("target_slot_id") or "")
                if source_slot_id not in self.session.page.slots or target_slot_id not in self.session.page.slots:
                    return CommandResult(False, False, "Smart Slot de origem/destino não encontrado.")
                merged = merge_slot_manually(self.session, source_slot_id, target_slot_id)
                return CommandResult(True, True, "Smart Slot decorativo associado ao produto.", {"source_slot_id": source_slot_id, "target_slot_id": target_slot_id, "merged_members": merged})
'''
    replace_once(
        path,
        '            if name == "undo":\n                changed = self.session.undo()\n',
        insert + '            if name == "undo":\n                changed = self.session.undo()\n',
    )


def patch_qml() -> None:
    path = "src/srstudio/graphics2/qml/GraphicsEditor.qml"
    replace_once(
        path,
        "    property bool smartSlotInspectionMode: false\n",
        "    property bool smartSlotInspectionMode: false\n"
        "    property bool smartSlotEditMode: false\n"
        "    property bool smartSlotSnap: true\n",
    )
    replace_once(
        path,
        '            ToolButton { text: "Smart Slots"; checkable: true; checked: smartSlotInspectionMode; ToolTip.text: "Mostrar áreas inteligentes"; ToolTip.visible: hovered; onClicked: smartSlotInspectionMode = checked }\n',
        '''            ToolButton { text: "Smart Slots"; checkable: true; checked: smartSlotInspectionMode; ToolTip.text: "Mostrar áreas inteligentes"; ToolTip.visible: hovered; onClicked: smartSlotInspectionMode = checked }
            ToolButton {
                text: "Ajustar Smart Slot"
                checkable: true
                checked: smartSlotEditMode
                ToolTip.text: "Mover/redimensionar somente a área semântica do slot"
                ToolTip.visible: hovered
                onClicked: {
                    smartSlotEditMode = checked
                    if (checked) smartSlotInspectionMode = true
                }
            }
            ToolButton { text: "Snap Slot"; visible: smartSlotEditMode; checkable: true; checked: smartSlotSnap; onClicked: smartSlotSnap = checked }
            ToolButton {
                text: "Restaurar Auto"
                visible: smartSlotEditMode && selectedSlotId !== ""
                onClicked: sceneBridge.dispatch(JSON.stringify({"name":"restore_smart_slot_auto","slot_id":selectedSlotId}))
            }
            ToolButton {
                text: "Não-produto"
                visible: smartSlotEditMode && selectedSlotId !== ""
                onClicked: sceneBridge.dispatch(JSON.stringify({"name":"mark_smart_slot_non_product","slot_id":selectedSlotId}))
            }
            ToolButton {
                text: "Excluir Slot"
                visible: smartSlotEditMode && selectedSlotId !== ""
                onClicked: sceneBridge.dispatch(JSON.stringify({"name":"delete_smart_slot","slot_id":selectedSlotId}))
            }
''',
    )
    replace_once(
        path,
        "                                    property bool showSlotOverlay: smartSlotInspectionMode || productDragActive || isSelectedSlot || isHoveredSlot\n",
        "                                    property bool showSlotOverlay: smartSlotEditMode || smartSlotInspectionMode || productDragActive || isSelectedSlot || isHoveredSlot\n",
    )
    # Give each slot delegate a local id so resize-handle modelData cannot shadow
    # the actual slot modelData.
    replace_once(
        path,
        '''                                delegate: Item {
                                    required property var modelData
                                    property var bounds: slotBounds(modelData)
''',
        '''                                delegate: Item {
                                    id: slotOverlay
                                    required property var modelData
                                    property var bounds: slotBounds(modelData)
''',
    )
    old_mouse = '''                                    MouseArea {
                                        anchors.fill: parent
                                        acceptedButtons: Qt.LeftButton
                                        hoverEnabled: true
                                        onEntered: hoveredSlotId = modelData.id
                                        onExited: if (hoveredSlotId === modelData.id) hoveredSlotId = ""
                                        onClicked: selectedSlotId = modelData.id
                                    }
'''
    new_mouse = '''                                    MouseArea {
                                        anchors.fill: parent
                                        acceptedButtons: Qt.LeftButton
                                        hoverEnabled: true
                                        preventStealing: smartSlotEditMode
                                        drag.target: smartSlotEditMode ? slotOverlay : null
                                        onEntered: hoveredSlotId = slotOverlay.modelData.id
                                        onExited: if (hoveredSlotId === slotOverlay.modelData.id) hoveredSlotId = ""
                                        onPressed: selectedSlotId = slotOverlay.modelData.id
                                        onClicked: selectedSlotId = slotOverlay.modelData.id
                                        onReleased: {
                                            if (!smartSlotEditMode) return
                                            sceneBridge.dispatch(JSON.stringify({
                                                "name":"adjust_smart_slot",
                                                "slot_id":slotOverlay.modelData.id,
                                                "x":slotOverlay.x / zoom,
                                                "y":slotOverlay.y / zoom,
                                                "width":slotOverlay.width / zoom,
                                                "height":slotOverlay.height / zoom,
                                                "snap":smartSlotSnap
                                            }))
                                        }
                                    }
                                    Repeater {
                                        model: [
                                            {"dir":"nw","fx":0,"fy":0,"cursor":Qt.SizeFDiagCursor},
                                            {"dir":"n","fx":0.5,"fy":0,"cursor":Qt.SizeVerCursor},
                                            {"dir":"ne","fx":1,"fy":0,"cursor":Qt.SizeBDiagCursor},
                                            {"dir":"e","fx":1,"fy":0.5,"cursor":Qt.SizeHorCursor},
                                            {"dir":"se","fx":1,"fy":1,"cursor":Qt.SizeFDiagCursor},
                                            {"dir":"s","fx":0.5,"fy":1,"cursor":Qt.SizeVerCursor},
                                            {"dir":"sw","fx":0,"fy":1,"cursor":Qt.SizeBDiagCursor},
                                            {"dir":"w","fx":0,"fy":0.5,"cursor":Qt.SizeHorCursor}
                                        ]
                                        delegate: Rectangle {
                                            required property var modelData
                                            visible: smartSlotEditMode && slotOverlay.isSelectedSlot
                                            width: 11; height: 11; radius: 2
                                            x: modelData.fx * slotOverlay.width - width / 2
                                            y: modelData.fy * slotOverlay.height - height / 2
                                            color: "white"
                                            border.width: 2
                                            border.color: "#0F5BD8"
                                            z: 10
                                            MouseArea {
                                                anchors.fill: parent
                                                cursorShape: modelData.cursor
                                                preventStealing: true
                                                property real startGlobalX: 0
                                                property real startGlobalY: 0
                                                property real startX: 0
                                                property real startY: 0
                                                property real startW: 0
                                                property real startH: 0
                                                onPressed: {
                                                    var p = mapToItem(sheet, mouse.x, mouse.y)
                                                    startGlobalX = p.x / zoom
                                                    startGlobalY = p.y / zoom
                                                    startX = slotOverlay.bounds.x
                                                    startY = slotOverlay.bounds.y
                                                    startW = slotOverlay.bounds.width
                                                    startH = slotOverlay.bounds.height
                                                }
                                                onReleased: {
                                                    var p = mapToItem(sheet, mouse.x, mouse.y)
                                                    var dx = p.x / zoom - startGlobalX
                                                    var dy = p.y / zoom - startGlobalY
                                                    var nx = startX
                                                    var ny = startY
                                                    var nw = startW
                                                    var nh = startH
                                                    if (modelData.dir.indexOf("w") >= 0) { nx += dx; nw -= dx }
                                                    if (modelData.dir.indexOf("e") >= 0) nw += dx
                                                    if (modelData.dir.indexOf("n") >= 0) { ny += dy; nh -= dy }
                                                    if (modelData.dir.indexOf("s") >= 0) nh += dy
                                                    if (nw < 1) { if (modelData.dir.indexOf("w") >= 0) nx -= (1 - nw); nw = 1 }
                                                    if (nh < 1) { if (modelData.dir.indexOf("n") >= 0) ny -= (1 - nh); nh = 1 }
                                                    sceneBridge.dispatch(JSON.stringify({
                                                        "name":"adjust_smart_slot",
                                                        "slot_id":slotOverlay.modelData.id,
                                                        "x":nx,
                                                        "y":ny,
                                                        "width":nw,
                                                        "height":nh,
                                                        "snap":smartSlotSnap
                                                    }))
                                                }
                                            }
                                        }
                                    }
'''
    replace_once(path, old_mouse, new_mouse)


def main() -> None:
    patch_import_bridge()
    patch_geometry()
    patch_router()
    patch_qml()
    for temporary in (
        ".github/workflows/g2-smart-slot-decorative-manual-patcher.yml",
        "tools/g2_apply_smart_slot_decorative_manual.py",
    ):
        target = Path(temporary)
        if target.exists():
            target.unlink()


if __name__ == "__main__":
    main()
