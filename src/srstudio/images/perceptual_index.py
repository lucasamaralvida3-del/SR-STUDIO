from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


@dataclass(frozen=True, slots=True)
class PerceptualIndexEntry:
    asset_id: str
    perceptual_hash: str


@dataclass(slots=True)
class _Node:
    value: int
    entries: list[PerceptualIndexEntry] = field(default_factory=list)
    children: dict[int, "_Node"] = field(default_factory=dict)


class HammingPerceptualIndex:
    """Metadata-only BK-tree for 64-bit perceptual hashes.

    dHash is only a candidate generator. Callers must still validate geometry and
    image content before treating a result as a near-duplicate.
    """

    def __init__(self, entries: Iterable[PerceptualIndexEntry] = ()) -> None:
        self.root: _Node | None = None
        self.size = 0
        for entry in entries:
            self.add(entry)

    @staticmethod
    def distance(left: int, right: int) -> int:
        return (left ^ right).bit_count()

    @staticmethod
    def parse(value: str) -> int | None:
        try:
            parsed = int(str(value), 16)
        except (TypeError, ValueError):
            return None
        if parsed < 0 or parsed.bit_length() > 64:
            return None
        return parsed

    def add(self, entry: PerceptualIndexEntry) -> bool:
        value = self.parse(entry.perceptual_hash)
        if value is None or not entry.asset_id:
            return False
        if self.root is None:
            self.root = _Node(value, [entry])
            self.size = 1
            return True

        node = self.root
        while True:
            distance = self.distance(value, node.value)
            if distance == 0:
                if all(existing.asset_id != entry.asset_id for existing in node.entries):
                    node.entries.append(entry)
                    self.size += 1
                return True
            child = node.children.get(distance)
            if child is None:
                node.children[distance] = _Node(value, [entry])
                self.size += 1
                return True
            node = child

    def search(self, perceptual_hash: str, max_distance: int) -> list[tuple[int, PerceptualIndexEntry]]:
        value = self.parse(perceptual_hash)
        if value is None or self.root is None:
            return []
        radius = max(0, int(max_distance))
        result: list[tuple[int, PerceptualIndexEntry]] = []
        stack = [self.root]
        while stack:
            node = stack.pop()
            distance = self.distance(value, node.value)
            if distance <= radius:
                result.extend((distance, entry) for entry in node.entries)
            lower = max(0, distance - radius)
            upper = distance + radius
            stack.extend(child for edge, child in node.children.items() if lower <= edge <= upper)
        result.sort(key=lambda item: (item[0], item[1].asset_id))
        return result
