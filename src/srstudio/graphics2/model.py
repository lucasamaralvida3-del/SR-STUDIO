from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any, Iterable
import copy
import uuid


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


class CoordinateUnit(StrEnum):
    POINT = "pt"
    PIXEL = "px"
    MILLIMETER = "mm"


class NodeKind(StrEnum):
    GROUP = "group"
    TEXT = "text"
    IMAGE = "image"
    RECT = "rect"
    ELLIPSE = "ellipse"
    LINE = "line"
    PATH = "path"
    BACKGROUND = "background"
    PRODUCT_CARD = "product_card"


class BindingRole(StrEnum):
    NAME = "name"
    IMAGE = "image"
    CURRENCY = "currency"
    PRICE_REAIS = "price_reais"
    PRICE_CENTS = "price_cents"
    UNIT = "unit"
    LIMIT = "limit"
    APP_PRICE = "app_price"
    WHOLESALE_PRICE = "wholesale_price"
    RETAIL_PRICE = "retail_price"
    QUANTITY = "quantity"
    VALIDITY = "validity"


class FitMode(StrEnum):
    CONTAIN = "contain"
    COVER = "cover"
    FILL = "fill"


@dataclass(slots=True)
class Rect:
    x: float = 0.0
    y: float = 0.0
    width: float = 0.0
    height: float = 0.0

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    @property
    def center_x(self) -> float:
        return self.x + self.width / 2.0

    @property
    def center_y(self) -> float:
        return self.y + self.height / 2.0

    def translated(self, dx: float, dy: float) -> "Rect":
        return Rect(self.x + dx, self.y + dy, self.width, self.height)

    def normalized(self) -> "Rect":
        x, y, w, h = self.x, self.y, self.width, self.height
        if w < 0:
            x += w
            w = -w
        if h < 0:
            y += h
            h = -h
        return Rect(x, y, w, h)

    def union(self, other: "Rect") -> "Rect":
        a, b = self.normalized(), other.normalized()
        x = min(a.x, b.x)
        y = min(a.y, b.y)
        r = max(a.right, b.right)
        bt = max(a.bottom, b.bottom)
        return Rect(x, y, r - x, bt - y)


@dataclass(slots=True)
class Transform:
    x: float = 0.0
    y: float = 0.0
    width: float = 0.0
    height: float = 0.0
    rotation: float = 0.0
    scale_x: float = 1.0
    scale_y: float = 1.0
    pivot_x: float = 0.5
    pivot_y: float = 0.5

    @property
    def rect(self) -> Rect:
        return Rect(self.x, self.y, self.width, self.height)


@dataclass(slots=True)
class AssetRef:
    id: str = field(default_factory=lambda: _id("asset"))
    kind: str = "image"
    source: str = ""
    mime: str = ""
    sha256: str = ""
    width: int = 0
    height: int = 0
    embedded: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class GraphicsNode:
    id: str = field(default_factory=lambda: _id("node"))
    kind: NodeKind = NodeKind.RECT
    name: str = ""
    transform: Transform = field(default_factory=Transform)
    parent_id: str | None = None
    children: list[str] = field(default_factory=list)
    z_index: int = 0
    locked: bool = False
    visible: bool = True
    opacity: float = 1.0
    text: str = ""
    asset_id: str = ""
    binding_role: BindingRole | None = None
    style: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def rect(self) -> Rect:
        return self.transform.rect

    def clone(self, *, preserve_id: bool = False) -> "GraphicsNode":
        node = copy.deepcopy(self)
        if not preserve_id:
            node.id = _id("node")
            node.parent_id = None
            node.children = []
        return node


@dataclass(slots=True)
class SmartSlot:
    id: str = field(default_factory=lambda: _id("slot"))
    name: str = ""
    page_id: str = ""
    node_by_role: dict[str, str] = field(default_factory=dict)
    product_id: str = ""
    confidence: float = 1.0
    locked: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def node_id(self, role: BindingRole | str) -> str:
        key = role.value if isinstance(role, BindingRole) else str(role)
        return self.node_by_role.get(key, "")


@dataclass(slots=True)
class GraphicsPage:
    id: str = field(default_factory=lambda: _id("page"))
    name: str = "Página 1"
    width: float = 1080.0
    height: float = 1350.0
    unit: CoordinateUnit = CoordinateUnit.PIXEL
    background: str = "#FFFFFF"
    nodes: dict[str, GraphicsNode] = field(default_factory=dict)
    roots: list[str] = field(default_factory=list)
    slots: dict[str, SmartSlot] = field(default_factory=dict)
    guides_x: list[float] = field(default_factory=list)
    guides_y: list[float] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_node(self, node: GraphicsNode, parent_id: str | None = None) -> GraphicsNode:
        if node.id in self.nodes:
            raise ValueError(f"Node duplicado: {node.id}")
        node.parent_id = parent_id
        self.nodes[node.id] = node
        if parent_id:
            parent = self.nodes.get(parent_id)
            if parent is None:
                del self.nodes[node.id]
                raise KeyError(f"Pai inexistente: {parent_id}")
            if node.id not in parent.children:
                parent.children.append(node.id)
        else:
            self.roots.append(node.id)
        return node

    def node(self, node_id: str) -> GraphicsNode | None:
        return self.nodes.get(node_id)

    def ordered_nodes(self) -> list[GraphicsNode]:
        return sorted(self.nodes.values(), key=lambda item: (item.z_index, item.id))

    def descendants(self, node_id: str) -> list[str]:
        node = self.nodes.get(node_id)
        if node is None:
            return []
        out: list[str] = []
        stack = list(node.children)
        seen: set[str] = set()
        while stack:
            current = stack.pop()
            if current in seen or current not in self.nodes:
                continue
            seen.add(current)
            out.append(current)
            stack.extend(self.nodes[current].children)
        return out

    def remove_node(self, node_id: str, *, recursive: bool = True) -> list[GraphicsNode]:
        node = self.nodes.get(node_id)
        if node is None:
            return []
        targets = [node_id]
        if recursive:
            targets.extend(self.descendants(node_id))
        target_set = set(targets)
        removed = [self.nodes[nid] for nid in targets if nid in self.nodes]
        if node.parent_id and node.parent_id in self.nodes:
            parent = self.nodes[node.parent_id]
            parent.children = [nid for nid in parent.children if nid not in target_set]
        self.roots = [nid for nid in self.roots if nid not in target_set]
        for current in self.nodes.values():
            if current.id not in target_set:
                current.children = [nid for nid in current.children if nid not in target_set]
        for nid in target_set:
            self.nodes.pop(nid, None)
        self._prune_deleted_references(target_set)
        return removed

    def _prune_deleted_references(self, target_set: set[str]) -> None:
        removed_slot_ids: set[str] = set()
        for slot_id, slot in list(self.slots.items()):
            slot.node_by_role = {
                role: nid
                for role, nid in slot.node_by_role.items()
                if nid not in target_set and nid in self.nodes
            }
            extras = slot.metadata.get("extra_bindings")
            extra_node_ids: set[str] = set()
            if isinstance(extras, dict):
                cleaned_extras: dict[str, Any] = {}
                for role, raw_ids in extras.items():
                    if isinstance(raw_ids, (list, tuple, set)):
                        values = [str(nid) for nid in raw_ids if str(nid) not in target_set and str(nid) in self.nodes]
                        if values:
                            cleaned_extras[str(role)] = values
                            extra_node_ids.update(values)
                    elif raw_ids:
                        value = str(raw_ids)
                        if value not in target_set and value in self.nodes:
                            cleaned_extras[str(role)] = value
                            extra_node_ids.add(value)
                slot.metadata["extra_bindings"] = cleaned_extras
            if not slot.node_by_role and not extra_node_ids:
                removed_slot_ids.add(slot_id)
                self.slots.pop(slot_id, None)

        raw_blocks = self.metadata.get("semantic_blocks")
        if not isinstance(raw_blocks, dict):
            return

        removed_block_ids: set[str] = set()
        for block_id, block in list(raw_blocks.items()):
            if not isinstance(block, dict):
                continue
            slot_id = str(block.get("slot_id") or "")
            members = [str(nid) for nid in block.get("members") or [] if str(nid) not in target_set and str(nid) in self.nodes]
            roles: dict[str, list[str]] = {}
            for role, raw_ids in dict(block.get("roles") or {}).items():
                values = [str(nid) for nid in raw_ids if str(nid) not in target_set and str(nid) in self.nodes]
                if values:
                    roles[str(role)] = values
            metadata = block.get("metadata")
            if not isinstance(metadata, dict):
                metadata = {}
                block["metadata"] = metadata
            content_members = metadata.get("content_members")
            if isinstance(content_members, list):
                metadata["content_members"] = [
                    str(nid)
                    for nid in content_members
                    if str(nid) not in target_set and str(nid) in self.nodes
                ]
            for key in ("source_group_id", "name_node_id", "image_node_id"):
                value = str(metadata.get(key) or "")
                if value in target_set or (value and value not in self.nodes):
                    metadata[key] = ""
            geometry = block.get("template_geometry")
            if isinstance(geometry, dict):
                block["template_geometry"] = {
                    str(nid): value
                    for nid, value in geometry.items()
                    if str(nid) not in target_set and str(nid) in self.nodes
                }
            block["members"] = members
            block["roles"] = roles

            remaining_context = list(metadata.get("content_members") or [])
            has_references = bool(members or remaining_context or any(roles.values()))
            if slot_id in removed_slot_ids or not has_references:
                removed_block_ids.add(str(block_id))
                raw_blocks.pop(block_id, None)
                continue

            bounds_ids = members or remaining_context
            bounds = self.bounds(bounds_ids)
            if bounds is not None:
                block["bounds"] = {
                    "x": bounds.x,
                    "y": bounds.y,
                    "width": bounds.width,
                    "height": bounds.height,
                }

        if removed_block_ids:
            for block in raw_blocks.values():
                if not isinstance(block, dict):
                    continue
                metadata = block.get("metadata")
                if not isinstance(metadata, dict):
                    continue
                price_blocks = metadata.get("price_blocks")
                if isinstance(price_blocks, list):
                    metadata["price_blocks"] = [str(item) for item in price_blocks if str(item) not in removed_block_ids]

        for slot in self.slots.values():
            product_card_id = str(slot.metadata.get("semantic_product_card_id") or "")
            if product_card_id in removed_block_ids:
                slot.metadata.pop("semantic_product_card_id", None)
            price_ids = slot.metadata.get("semantic_price_block_ids")
            if isinstance(price_ids, list):
                slot.metadata["semantic_price_block_ids"] = [
                    str(item) for item in price_ids if str(item) not in removed_block_ids
                ]

    def bounds(self, node_ids: Iterable[str]) -> Rect | None:
        rects = [self.nodes[nid].rect for nid in node_ids if nid in self.nodes and self.nodes[nid].visible]
        if not rects:
            return None
        result = rects[0]
        for rect in rects[1:]:
            result = result.union(rect)
        return result


@dataclass(slots=True)
class GraphicsDocument:
    schema: str = "srscene/2.0"
    id: str = field(default_factory=lambda: _id("doc"))
    name: str = "Novo Projeto SR"
    pages: list[GraphicsPage] = field(default_factory=lambda: [GraphicsPage()])
    assets: dict[str, AssetRef] = field(default_factory=dict)
    active_page_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.pages and not self.active_page_id:
            self.active_page_id = self.pages[0].id

    @property
    def active_page(self) -> GraphicsPage:
        page = self.page(self.active_page_id)
        if page is not None:
            return page
        if not self.pages:
            self.pages.append(GraphicsPage())
        self.active_page_id = self.pages[0].id
        return self.pages[0]

    def page(self, page_id: str) -> GraphicsPage | None:
        return next((item for item in self.pages if item.id == page_id), None)

    def add_page(self, page: GraphicsPage | None = None) -> GraphicsPage:
        page = page or GraphicsPage(name=f"Página {len(self.pages) + 1}")
        self.pages.append(page)
        self.active_page_id = page.id
        return page

    def add_asset(self, asset: AssetRef) -> AssetRef:
        self.assets[asset.id] = asset
        return asset

    def to_dict(self) -> dict[str, Any]:
        def encode_node(node: GraphicsNode) -> dict[str, Any]:
            data = asdict(node)
            data["kind"] = node.kind.value
            data["binding_role"] = node.binding_role.value if node.binding_role else None
            return data
        return {
            "schema": self.schema,
            "id": self.id,
            "name": self.name,
            "active_page_id": self.active_page_id,
            "metadata": copy.deepcopy(self.metadata),
            "assets": {key: asdict(value) for key, value in self.assets.items()},
            "pages": [
                {
                    "id": page.id, "name": page.name, "width": page.width, "height": page.height,
                    "unit": page.unit.value, "background": page.background,
                    "nodes": {key: encode_node(value) for key, value in page.nodes.items()},
                    "roots": list(page.roots),
                    "slots": {key: asdict(value) for key, value in page.slots.items()},
                    "guides_x": list(page.guides_x), "guides_y": list(page.guides_y),
                    "metadata": copy.deepcopy(page.metadata),
                }
                for page in self.pages
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GraphicsDocument":
        if str(data.get("schema") or "") not in {"srscene/2.0", "srscene/2"}:
            raise ValueError("Documento não é SR Scene 2.0")
        assets = {key: AssetRef(**value) for key, value in dict(data.get("assets") or {}).items()}
        pages: list[GraphicsPage] = []
        for raw_page in list(data.get("pages") or []):
            nodes: dict[str, GraphicsNode] = {}
            for key, raw_node in dict(raw_page.get("nodes") or {}).items():
                payload = dict(raw_node)
                payload["kind"] = NodeKind(payload.get("kind") or NodeKind.RECT.value)
                role = payload.get("binding_role")
                payload["binding_role"] = BindingRole(role) if role else None
                payload["transform"] = Transform(**dict(payload.get("transform") or {}))
                nodes[key] = GraphicsNode(**payload)
            slots = {key: SmartSlot(**value) for key, value in dict(raw_page.get("slots") or {}).items()}
            pages.append(GraphicsPage(
                id=str(raw_page.get("id") or _id("page")),
                name=str(raw_page.get("name") or "Página"),
                width=float(raw_page.get("width") or 1080.0),
                height=float(raw_page.get("height") or 1350.0),
                unit=CoordinateUnit(raw_page.get("unit") or CoordinateUnit.PIXEL.value),
                background=str(raw_page.get("background") or "#FFFFFF"),
                nodes=nodes, roots=list(raw_page.get("roots") or []), slots=slots,
                guides_x=[float(v) for v in raw_page.get("guides_x") or []],
                guides_y=[float(v) for v in raw_page.get("guides_y") or []],
                metadata=dict(raw_page.get("metadata") or {}),
            ))
        return cls(
            schema="srscene/2.0", id=str(data.get("id") or _id("doc")),
            name=str(data.get("name") or "Novo Projeto SR"), pages=pages or [GraphicsPage()],
            assets=assets, active_page_id=str(data.get("active_page_id") or ""),
            metadata=dict(data.get("metadata") or {}),
        )