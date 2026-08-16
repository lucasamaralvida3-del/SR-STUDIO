from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
from math import cos, radians, sin
from typing import Any, Iterator
import copy

from .history import TransactionHistory
from .model import BindingRole, GraphicsDocument, GraphicsNode, GraphicsPage, NodeKind, Rect, SmartSlot, Transform, _id
from .preflight import assert_document_integrity


def _price_parts(value: Any) -> tuple[str, str]:
    if value in (None, ""):
        return "", ""
    text = str(value).strip().replace("R$", "").replace(" ", "")
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        amount = Decimal(text).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return "", ""
    whole, cents = f"{amount:.2f}".split(".")
    return whole, f",{cents}"


def _role_value(role: BindingRole, product: dict[str, Any]) -> str:
    if role is BindingRole.NAME:
        return str(product.get("display_name") or product.get("name") or product.get("original_name") or "")
    if role is BindingRole.CURRENCY:
        return "R$"
    if role in {BindingRole.PRICE_REAIS, BindingRole.PRICE_CENTS}:
        whole, cents = _price_parts(product.get("price"))
        return whole if role is BindingRole.PRICE_REAIS else cents
    if role is BindingRole.UNIT:
        unit = str(product.get("unit") or "UN").upper().strip()
        return f"/{unit}" if unit and not unit.startswith("/") else unit
    if role is BindingRole.LIMIT:
        value = str(product.get("cpf_limit") or product.get("limit") or "").strip()
        return f"LIMITE DE {value} POR CPF" if value else ""
    if role is BindingRole.APP_PRICE:
        value = product.get("app_price")
        return "" if value in (None, "") else f"R$ {str(value).replace('.', ',')}"
    if role is BindingRole.WHOLESALE_PRICE:
        value = product.get("wholesale_price")
        return "" if value in (None, "") else f"R$ {str(value).replace('.', ',')}"
    if role is BindingRole.RETAIL_PRICE:
        value = product.get("retail_price")
        return "" if value in (None, "") else f"R$ {str(value).replace('.', ',')}"
    if role is BindingRole.QUANTITY:
        return str(product.get("quantity") or "")
    if role is BindingRole.VALIDITY:
        return str(product.get("validity") or "")
    return ""


class GraphicsSession:
    """API única de edição para UI, SR IA, importadores e automações.

    Coordenadas de todos os nós são absolutas no SR Scene. Grupos são uma
    relação semântica/hierárquica: operações no grupo são propagadas pela
    árvore de forma transacional para que o renderer permaneça simples e a
    geometria continue determinística.
    """

    def __init__(self, document: GraphicsDocument | None = None, *, history_limit: int = 250) -> None:
        self.document = document or GraphicsDocument()
        self.selection: set[str] = set()
        self.anchor_id: str | None = None
        self.history = TransactionHistory(history_limit)

    @property
    def page(self) -> GraphicsPage:
        return self.document.active_page

    def select(self, node_id: str, *, additive: bool = False, toggle: bool = False) -> None:
        if node_id not in self.page.nodes:
            return
        if toggle:
            if node_id in self.selection:
                self.selection.remove(node_id)
            else:
                self.selection.add(node_id)
        elif additive:
            self.selection.add(node_id)
        else:
            self.selection = {node_id}
        self.anchor_id = node_id if node_id in self.selection else next(iter(self.selection), None)

    def clear_selection(self) -> None:
        self.selection.clear()
        self.anchor_id = None

    @contextmanager
    def transaction(self, label: str) -> Iterator[None]:
        before = self.history.capture(self.document)
        try:
            yield
            assert_document_integrity(self.document)
        except Exception:
            self.document = GraphicsDocument.from_dict(before)
            self.clear_selection()
            raise
        self.history.push(label, before, self.history.capture(self.document))

    def undo(self) -> bool:
        if not self.history.can_undo:
            return False
        self.document = self.history.undo(self.document)
        self.clear_selection()
        return True

    def redo(self) -> bool:
        if not self.history.can_redo:
            return False
        self.document = self.history.redo(self.document)
        self.clear_selection()
        return True

    def add_node(self, node: GraphicsNode, parent_id: str | None = None, *, label: str = "Adicionar elemento") -> GraphicsNode:
        with self.transaction(label):
            self.page.add_node(node, parent_id=parent_id)
        self.select(node.id)
        return node

    def add_text(self, text: str, *, x: float, y: float, width: float, height: float, name: str = "Texto") -> GraphicsNode:
        return self.add_node(
            GraphicsNode(
                kind=NodeKind.TEXT,
                name=name,
                text=text,
                transform=Transform(x=x, y=y, width=width, height=height),
                style={"font_family": "Segoe UI", "font_size": 28.0, "font_size_unit": "pt", "font_weight": 700, "align": "center"},
            )
        )

    def delete_selected(self) -> int:
        targets = [nid for nid in self.selection if nid in self.page.nodes]
        if not targets:
            return 0
        roots = [nid for nid in targets if not self._ancestor_in(nid, set(targets))]
        count = sum(len(self._tree_ids(nid)) for nid in roots)
        with self.transaction("Excluir elementos"):
            for nid in roots:
                self.page.remove_node(nid, recursive=True)
        self.clear_selection()
        return count

    def move_selected(self, dx: float, dy: float, *, clamp: bool = False) -> None:
        roots = self._selection_roots(editable_only=True)
        if not roots:
            return
        with self.transaction("Mover elementos"):
            for node in roots:
                move_x, move_y = float(dx), float(dy)
                if clamp:
                    bounds = self._tree_bounds(node.id) or node.rect
                    move_x = min(max(move_x, -bounds.x), self.page.width - bounds.right)
                    move_y = min(max(move_y, -bounds.y), self.page.height - bounds.bottom)
                self._translate_tree(node.id, move_x, move_y)

    def resize_node(
        self,
        node_id: str,
        *,
        x: float | None = None,
        y: float | None = None,
        width: float | None = None,
        height: float | None = None,
        min_size: float = 1.0,
    ) -> None:
        node = self.page.node(node_id)
        if node is None or self.effective_locked(node_id):
            return
        old = Rect(node.transform.x, node.transform.y, max(node.transform.width, 1e-6), max(node.transform.height, 1e-6))
        new = Rect(
            float(x) if x is not None else old.x,
            float(y) if y is not None else old.y,
            max(float(min_size), float(width)) if width is not None else old.width,
            max(float(min_size), float(height)) if height is not None else old.height,
        )
        with self.transaction("Redimensionar elemento"):
            if node.kind is NodeKind.GROUP and node.children:
                self._scale_tree(node.id, old, new)
            else:
                t = node.transform
                t.x, t.y, t.width, t.height = new.x, new.y, new.width, new.height

    def rotate_selected(self, angle: float, *, relative: bool = False, snap: float | None = None) -> None:
        roots = self._selection_roots(editable_only=True)
        if not roots:
            return
        with self.transaction("Rotacionar elementos"):
            for node in roots:
                current = float(node.transform.rotation)
                target = current + float(angle) if relative else float(angle)
                if snap and snap > 0:
                    target = round(target / snap) * snap
                target %= 360.0
                delta = (target - current) % 360.0
                if delta > 180.0:
                    delta -= 360.0
                if node.kind is NodeKind.GROUP and node.children:
                    self._rotate_tree(node.id, delta)
                else:
                    node.transform.rotation = target

    def set_opacity(self, value: float) -> None:
        value = min(1.0, max(0.0, float(value)))
        nodes = self._selected_nodes()
        if not nodes:
            return
        with self.transaction("Alterar opacidade"):
            for node in nodes:
                node.opacity = value

    def lock_selected(self, value: bool = True) -> None:
        nodes = self._selected_nodes()
        if not nodes:
            return
        with self.transaction("Bloquear elementos" if value else "Desbloquear elementos"):
            for node in nodes:
                node.locked = bool(value)

    def hide_selected(self, value: bool = True) -> None:
        nodes = self._selected_nodes()
        if not nodes:
            return
        with self.transaction("Ocultar elementos" if value else "Exibir elementos"):
            for node in nodes:
                node.visible = not bool(value)

    def layer_selected(self, mode: str) -> None:
        roots = self._selection_roots(editable_only=False)
        if not roots:
            return
        with self.transaction("Alterar camada"):
            selected_ids = {tree_id for root in roots for tree_id in self._tree_ids(root.id)}
            outside = [node.z_index for node in self.page.nodes.values() if node.id not in selected_ids]
            for root in roots:
                tree = [self.page.nodes[nid] for nid in self._tree_ids(root.id) if nid in self.page.nodes]
                if not tree:
                    continue
                current_min = min(node.z_index for node in tree)
                current_max = max(node.z_index for node in tree)
                if mode == "front":
                    delta = (max(outside, default=current_max) + 1) - current_min
                elif mode == "back":
                    delta = (min(outside, default=current_min) - 1) - current_max
                elif mode == "forward":
                    delta = 1
                elif mode == "backward":
                    delta = -1
                else:
                    raise ValueError(f"Modo de camada inválido: {mode}")
                for node in tree:
                    node.z_index += delta

    def align_selected(self, mode: str) -> None:
        nodes = self._selection_roots(editable_only=True)
        if len(nodes) < 2:
            return
        bounds = self.page.bounds(node.id for node in nodes)
        if bounds is None:
            return
        with self.transaction("Alinhar elementos"):
            for node in nodes:
                t = node.transform
                nx, ny = t.x, t.y
                if mode == "left":
                    nx = bounds.x
                elif mode in {"center", "center_x"}:
                    nx = bounds.center_x - t.width / 2.0
                elif mode == "right":
                    nx = bounds.right - t.width
                elif mode == "top":
                    ny = bounds.y
                elif mode in {"middle", "center_y"}:
                    ny = bounds.center_y - t.height / 2.0
                elif mode == "bottom":
                    ny = bounds.bottom - t.height
                else:
                    raise ValueError(f"Alinhamento inválido: {mode}")
                self._translate_tree(node.id, nx - t.x, ny - t.y)

    def distribute_selected(self, axis: str) -> None:
        nodes = self._selection_roots(editable_only=True)
        if len(nodes) < 3:
            return
        horizontal = axis in {"x", "horizontal"}
        ordered = sorted(nodes, key=lambda n: n.transform.x if horizontal else n.transform.y)
        first, last = ordered[0].transform, ordered[-1].transform
        if horizontal:
            span = last.x + last.width - first.x
            content = sum(n.transform.width for n in ordered)
        else:
            span = last.y + last.height - first.y
            content = sum(n.transform.height for n in ordered)
        gap = (span - content) / (len(ordered) - 1)
        with self.transaction("Distribuir elementos"):
            cursor = first.x if horizontal else first.y
            for node in ordered:
                if horizontal:
                    delta = cursor - node.transform.x
                    self._translate_tree(node.id, delta, 0.0)
                    cursor += node.transform.width + gap
                else:
                    delta = cursor - node.transform.y
                    self._translate_tree(node.id, 0.0, delta)
                    cursor += node.transform.height + gap

    def group_selected(self, name: str = "Grupo") -> str:
        nodes = self._selection_roots(editable_only=True)
        if len(nodes) < 2:
            return ""
        bounds = self.page.bounds(node.id for node in nodes)
        if bounds is None:
            return ""
        parents = {node.parent_id for node in nodes}
        common_parent = next(iter(parents)) if len(parents) == 1 else None
        with self.transaction("Agrupar elementos"):
            group = GraphicsNode(
                kind=NodeKind.GROUP,
                name=name,
                transform=Transform(x=bounds.x, y=bounds.y, width=bounds.width, height=bounds.height),
                z_index=min(node.z_index for node in nodes),
            )
            self.page.add_node(group, parent_id=common_parent)
            selected_ids = {node.id for node in nodes}
            for node in nodes:
                if node.parent_id and node.parent_id in self.page.nodes:
                    parent = self.page.nodes[node.parent_id]
                    parent.children = [nid for nid in parent.children if nid != node.id]
                else:
                    self.page.roots = [nid for nid in self.page.roots if nid != node.id]
                node.parent_id = group.id
                if node.id not in group.children:
                    group.children.append(node.id)
            self.page.roots = [nid for nid in self.page.roots if nid not in selected_ids]
            if common_parent is None and group.id not in self.page.roots:
                self.page.roots.append(group.id)
            if common_parent and common_parent in self.page.nodes and group.id not in self.page.nodes[common_parent].children:
                self.page.nodes[common_parent].children.append(group.id)
        self.selection = {group.id}
        self.anchor_id = group.id
        return group.id

    def ungroup_selected(self) -> int:
        groups = [node for node in self._selection_roots(editable_only=False) if node.kind is NodeKind.GROUP]
        if not groups:
            return 0
        child_ids: set[str] = set()
        with self.transaction("Desagrupar elementos"):
            for group in groups:
                parent_id = group.parent_id
                if parent_id and parent_id in self.page.nodes:
                    parent = self.page.nodes[parent_id]
                    parent.children = [nid for nid in parent.children if nid != group.id]
                for child_id in list(group.children):
                    child = self.page.node(child_id)
                    if child is None:
                        continue
                    child.parent_id = parent_id
                    child_ids.add(child_id)
                    if parent_id and parent_id in self.page.nodes:
                        parent = self.page.nodes[parent_id]
                        if child_id not in parent.children:
                            parent.children.append(child_id)
                    elif child_id not in self.page.roots:
                        self.page.roots.append(child_id)
                group.children.clear()
                self.page.remove_node(group.id, recursive=False)
        self.selection = child_ids
        self.anchor_id = next(iter(child_ids), None)
        return len(groups)

    def duplicate_selected(self, dx: float = 20.0, dy: float = 20.0) -> list[str]:
        original = self._selection_roots(editable_only=False)
        created: list[str] = []
        if not original:
            return created
        with self.transaction("Duplicar elementos"):
            for node in original:
                mapping: dict[str, str] = {}
                self._duplicate_tree(node.id, node.parent_id, float(dx), float(dy), mapping)
                created.append(mapping[node.id])
        self.selection = set(created)
        self.anchor_id = created[-1] if created else None
        return created

    def set_text(self, node_id: str, text: str) -> None:
        node = self.page.node(node_id)
        if node is None or node.kind is not NodeKind.TEXT or self.effective_locked(node_id):
            return
        with self.transaction("Editar texto"):
            node.text = str(text)

    def set_image_crop(
        self,
        node_id: str,
        *,
        fit: str | None = None,
        focus_x: float | None = None,
        focus_y: float | None = None,
        zoom: float | None = None,
        flip_x: bool | None = None,
        flip_y: bool | None = None,
    ) -> None:
        node = self.page.node(node_id)
        if node is None or node.kind is not NodeKind.IMAGE or self.effective_locked(node_id):
            return
        with self.transaction("Ajustar imagem"):
            if fit is not None:
                node.style["fit"] = str(fit)
            if focus_x is not None:
                node.style["focus_x"] = min(1.0, max(0.0, float(focus_x)))
            if focus_y is not None:
                node.style["focus_y"] = min(1.0, max(0.0, float(focus_y)))
            if zoom is not None:
                node.style["zoom"] = min(20.0, max(0.05, float(zoom)))
            if flip_x is not None:
                node.style["flip_x"] = bool(flip_x)
            if flip_y is not None:
                node.style["flip_y"] = bool(flip_y)

    def add_page(self, *, name: str | None = None, duplicate_active: bool = False) -> str:
        with self.transaction("Duplicar página" if duplicate_active else "Adicionar página"):
            if duplicate_active:
                page = copy.deepcopy(self.page)
                page.id = _id("page")
                page.name = name or f"{self.page.name} - cópia"
                for slot in page.slots.values():
                    slot.page_id = page.id
                self.document.pages.append(page)
                self.document.active_page_id = page.id
            else:
                self.document.add_page(GraphicsPage(name=name or f"Página {len(self.document.pages) + 1}"))
        self.clear_selection()
        return self.document.active_page_id

    def create_slot(self, name: str, bindings: dict[BindingRole | str, str], *, confidence: float = 1.0) -> SmartSlot:
        normalized: dict[str, str] = {}
        for role, node_id in bindings.items():
            key = role.value if isinstance(role, BindingRole) else BindingRole(str(role)).value
            if node_id not in self.page.nodes:
                raise KeyError(f"Node do slot inexistente: {node_id}")
            normalized[key] = node_id
        with self.transaction("Criar Smart Slot"):
            for key, node_id in normalized.items():
                self.page.nodes[node_id].binding_role = BindingRole(key)
            slot = SmartSlot(name=name, page_id=self.page.id, node_by_role=normalized, confidence=float(confidence))
            self.page.slots[slot.id] = slot
        return slot

    def bind_product(self, slot_id: str, product: dict[str, Any]) -> None:
        slot = self.page.slots.get(slot_id)
        if slot is None or slot.locked:
            return
        with self.transaction("Preencher produto"):
            slot.product_id = str(product.get("id") or product.get("product_id") or "")
            slot.metadata["product_snapshot"] = copy.deepcopy(product)
            for role_text, node_id in slot.node_by_role.items():
                node = self.page.node(node_id)
                if node is None:
                    continue
                role = BindingRole(role_text)
                node.binding_role = role
                if role is BindingRole.IMAGE:
                    node.asset_id = str(product.get("image_asset_id") or node.asset_id)
                    source = str(product.get("image_path") or product.get("image") or "")
                    if source:
                        node.metadata["bound_image_source"] = source
                        node.visible = True
                elif node.kind is NodeKind.TEXT:
                    node.text = _role_value(role, product)
                    if role in {BindingRole.LIMIT, BindingRole.APP_PRICE}:
                        node.visible = bool(node.text)

    def effective_locked(self, node_id: str) -> bool:
        node = self.page.node(node_id)
        if node is None:
            return True
        current: GraphicsNode | None = node
        seen: set[str] = set()
        while current is not None and current.id not in seen:
            seen.add(current.id)
            if current.locked:
                return True
            current = self.page.node(current.parent_id) if current.parent_id else None
        return False

    def effective_visible(self, node_id: str) -> bool:
        node = self.page.node(node_id)
        if node is None:
            return False
        current: GraphicsNode | None = node
        seen: set[str] = set()
        while current is not None and current.id not in seen:
            seen.add(current.id)
            if not current.visible:
                return False
            current = self.page.node(current.parent_id) if current.parent_id else None
        return True

    def effective_opacity(self, node_id: str) -> float:
        node = self.page.node(node_id)
        if node is None:
            return 0.0
        value = 1.0
        current: GraphicsNode | None = node
        seen: set[str] = set()
        while current is not None and current.id not in seen:
            seen.add(current.id)
            value *= max(0.0, min(1.0, float(current.opacity)))
            current = self.page.node(current.parent_id) if current.parent_id else None
        return max(0.0, min(1.0, value))

    def _selected_nodes(self) -> list[GraphicsNode]:
        return [self.page.nodes[nid] for nid in self.selection if nid in self.page.nodes]

    def _editable_selection(self) -> list[GraphicsNode]:
        return [node for node in self._selected_nodes() if not self.effective_locked(node.id)]

    def _selection_roots(self, *, editable_only: bool) -> list[GraphicsNode]:
        selected = {nid for nid in self.selection if nid in self.page.nodes}
        nodes = []
        for nid in selected:
            if self._ancestor_in(nid, selected):
                continue
            if editable_only and self.effective_locked(nid):
                continue
            nodes.append(self.page.nodes[nid])
        return sorted(nodes, key=lambda node: (node.z_index, node.id))

    def _ancestor_in(self, node_id: str, ids: set[str]) -> bool:
        node = self.page.node(node_id)
        parent_id = node.parent_id if node else None
        seen: set[str] = set()
        while parent_id and parent_id not in seen:
            if parent_id in ids:
                return True
            seen.add(parent_id)
            parent = self.page.node(parent_id)
            parent_id = parent.parent_id if parent else None
        return False

    def _tree_ids(self, root_id: str) -> list[str]:
        if root_id not in self.page.nodes:
            return []
        return [root_id, *self.page.descendants(root_id)]

    def _tree_bounds(self, root_id: str) -> Rect | None:
        return self.page.bounds(self._tree_ids(root_id))

    def _translate_tree(self, root_id: str, dx: float, dy: float) -> None:
        for node_id in self._tree_ids(root_id):
            node = self.page.node(node_id)
            if node is None:
                continue
            node.transform.x += float(dx)
            node.transform.y += float(dy)

    def _scale_tree(self, root_id: str, old: Rect, new: Rect) -> None:
        sx = new.width / max(old.width, 1e-6)
        sy = new.height / max(old.height, 1e-6)
        for node_id in self._tree_ids(root_id):
            node = self.page.node(node_id)
            if node is None:
                continue
            t = node.transform
            rel_x = (t.x - old.x) / max(old.width, 1e-6)
            rel_y = (t.y - old.y) / max(old.height, 1e-6)
            t.x = new.x + rel_x * new.width
            t.y = new.y + rel_y * new.height
            t.width = max(0.1, t.width * sx)
            t.height = max(0.1, t.height * sy)
        root = self.page.node(root_id)
        if root is not None:
            root.transform.x = new.x
            root.transform.y = new.y
            root.transform.width = new.width
            root.transform.height = new.height

    def _rotate_tree(self, root_id: str, delta_degrees: float) -> None:
        root = self.page.node(root_id)
        if root is None:
            return
        pivot_x = root.transform.x + root.transform.width * root.transform.pivot_x
        pivot_y = root.transform.y + root.transform.height * root.transform.pivot_y
        angle = radians(float(delta_degrees))
        cosine, sine = cos(angle), sin(angle)
        for node_id in self._tree_ids(root_id):
            node = self.page.node(node_id)
            if node is None:
                continue
            t = node.transform
            center_x = t.x + t.width * t.pivot_x
            center_y = t.y + t.height * t.pivot_y
            dx, dy = center_x - pivot_x, center_y - pivot_y
            rotated_x = pivot_x + dx * cosine - dy * sine
            rotated_y = pivot_y + dx * sine + dy * cosine
            t.x += rotated_x - center_x
            t.y += rotated_y - center_y
            t.rotation = (t.rotation + float(delta_degrees)) % 360.0

    def _duplicate_tree(self, node_id: str, new_parent_id: str | None, dx: float, dy: float, mapping: dict[str, str]) -> None:
        source = self.page.nodes[node_id]
        clone = source.clone()
        clone.transform.x += dx
        clone.transform.y += dy
        clone.z_index += 1
        mapping[node_id] = clone.id
        self.page.add_node(clone, parent_id=new_parent_id)
        for child_id in source.children:
            if child_id in self.page.nodes:
                self._duplicate_tree(child_id, clone.id, dx, dy, mapping)
