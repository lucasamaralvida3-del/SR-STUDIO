from __future__ import annotations

"""Reconstrução da hierarquia de grupos DrawingML no SR Scene 2.

O leitor PPTX legado precisa achatar grupos para calcular coordenadas absolutas.
Isso é ótimo para fidelidade de posição, mas ruim para edição profissional.
Esta segunda passagem relê a árvore OOXML e recria somente a relação pai/filho,
sem alterar x/y/w/h/rotação dos elementos importados.
"""

from dataclasses import asdict, dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET
import zipfile

from srstudio.importers.pptx.package_order import ordered_slide_paths

from .model import GraphicsDocument, GraphicsNode, NodeKind, Rect, Transform
from .pptx_group_transform import recover_pptx_group_member_transforms
from .pptx_shape_visual import recover_pptx_shape_visuals

P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"


@dataclass(slots=True)
class PptxGroupReport:
    slides_scanned: int = 0
    groups_found: int = 0
    groups_rebuilt: int = 0
    nodes_reparented: int = 0
    unmatched_members: int = 0
    warnings: list[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return not self.warnings

    def to_dict(self) -> dict:
        return asdict(self)


def rebuild_pptx_groups(source: str | Path, document: GraphicsDocument) -> PptxGroupReport:
    path = Path(source)
    report = PptxGroupReport()
    if path.suffix.lower() != ".pptx" or not path.is_file():
        return report
    # Companions visuais precisam existir antes de montarmos o índice por nome;
    # assim owner TEXT + backplate visual entram juntos no grupo reconstruído.
    _recover_shape_visuals(path, document)
    _recover_member_transforms(path, document)
    try:
        with zipfile.ZipFile(path) as archive:
            slides = ordered_slide_paths(archive)
            for page_index, slide_path in enumerate(slides):
                if page_index >= len(document.pages):
                    break
                report.slides_scanned += 1
                try:
                    root = ET.fromstring(archive.read(slide_path))
                except (KeyError, ET.ParseError) as exc:
                    report.warnings.append(f"{slide_path}: XML inválido ao reconstruir grupos ({exc}).")
                    continue
                _rebuild_page_groups(document.pages[page_index], root, report)
    except (OSError, zipfile.BadZipFile) as exc:
        report.warnings.append(f"Não foi possível reconstruir grupos PPTX: {exc}")
    document.metadata["pptx_groups"] = report.to_dict()
    return report


def _recover_shape_visuals(path: Path, document: GraphicsDocument) -> None:
    try:
        recover_pptx_shape_visuals(path, document)
    except Exception as exc:
        document.metadata["pptx_shape_visual_recovery"] = {
            "text_shapes": 0,
            "text_colors_corrected": 0,
            "compound_text_colors_corrected": 0,
            "visual_shapes": 0,
            "visuals_recovered": 0,
            "existing_visuals": 0,
            "pure_shape_colors_corrected": 0,
            "deferred_geometry": 0,
            "visual_coverage": 0.0,
            "issues": [],
            "error": str(exc),
        }


def _recover_member_transforms(path: Path, document: GraphicsDocument) -> None:
    try:
        recover_pptx_group_member_transforms(path, document)
    except Exception as exc:
        document.metadata["pptx_group_member_transform_recovery"] = {
            "source_members": 0,
            "mapped_members": 0,
            "exact_members": 0,
            "corrected_members": 0,
            "deferred_shear_members": 0,
            "coverage": 0.0,
            "issues": [],
            "error": str(exc),
        }


def _rebuild_page_groups(page, root: ET.Element, report: PptxGroupReport) -> None:
    _clear_generated_groups(page)
    sp_tree = root.find(f".//{{{P_NS}}}spTree")
    if sp_tree is None:
        return

    by_name: dict[str, list[GraphicsNode]] = {}
    for node in page.nodes.values():
        source_name = str(node.metadata.get("source_name") or node.name or "").strip()
        if source_name:
            by_name.setdefault(source_name, []).append(node)
    for nodes in by_name.values():
        nodes.sort(key=lambda item: (item.z_index, item.transform.y, item.transform.x, item.id))
    used: set[str] = set()
    sequence = [0]

    for child in list(sp_tree):
        if _tag(child) != "grpSp":
            continue
        _build_group(page, child, by_name, used, report, sequence, depth=1)

    page.metadata["pptx_groups_rebuilt"] = report.groups_rebuilt


def _build_group(
    page,
    group_xml: ET.Element,
    by_name: dict[str, list[GraphicsNode]],
    used: set[str],
    report: PptxGroupReport,
    sequence: list[int],
    *,
    depth: int,
) -> str | None:
    report.groups_found += 1
    sequence[0] += 1
    child_ids: list[str] = []
    for child in list(group_xml):
        tag = _tag(child)
        if tag in {"nvGrpSpPr", "grpSpPr"}:
            continue
        if tag == "grpSp":
            nested = _build_group(page, child, by_name, used, report, sequence, depth=depth + 1)
            if nested:
                child_ids.append(nested)
            continue
        if tag not in {"sp", "pic", "graphicFrame"}:
            continue
        name = _shape_name(child)
        node = _take_node(by_name, name, used)
        if node is None:
            if name:
                report.unmatched_members += 1
            continue
        used.add(node.id)
        child_ids.append(node.id)
        for companion in _compound_companions(by_name, name, node.id, used):
            used.add(companion.id)
            child_ids.append(companion.id)

    if not child_ids:
        return None

    bounds = _bounds(page, child_ids)
    if bounds is None:
        return None
    z_values = [page.nodes[node_id].z_index for node_id in child_ids if node_id in page.nodes]
    source_name = _shape_name(group_xml) or f"Grupo PPTX {sequence[0]}"
    group = GraphicsNode(
        kind=NodeKind.GROUP,
        name=source_name,
        transform=Transform(x=bounds.x, y=bounds.y, width=bounds.width, height=bounds.height),
        z_index=min(z_values) if z_values else 0,
        locked=False,
        visible=True,
        opacity=1.0,
        metadata={
            "source": "pptx-group",
            "source_name": source_name,
            "pptx_group_generated": True,
            "pptx_group_depth": depth,
            "pptx_group_sequence": sequence[0],
        },
    )
    page.add_node(group)
    for node_id in child_ids:
        if _reparent(page, node_id, group.id):
            report.nodes_reparented += 1
    report.groups_rebuilt += 1
    return group.id


def _take_node(by_name: dict[str, list[GraphicsNode]], name: str, used: set[str]) -> GraphicsNode | None:
    if not name:
        return None
    candidates = by_name.get(name) or []
    primary = next(
        (
            node
            for node in candidates
            if node.id not in used
            and node.kind is not NodeKind.GROUP
            and not node.metadata.get("pptx_compound_owner_id")
        ),
        None,
    )
    if primary is not None:
        return primary
    return next((node for node in candidates if node.id not in used and node.kind is not NodeKind.GROUP), None)


def _compound_companions(
    by_name: dict[str, list[GraphicsNode]],
    name: str,
    owner_id: str,
    used: set[str],
) -> list[GraphicsNode]:
    if not name or not owner_id:
        return []
    return [
        node
        for node in by_name.get(name) or []
        if node.id not in used
        and str(node.metadata.get("pptx_compound_owner_id") or "") == owner_id
    ]


def _reparent(page, node_id: str, parent_id: str) -> bool:
    node = page.nodes.get(node_id)
    parent = page.nodes.get(parent_id)
    if node is None or parent is None or node_id == parent_id:
        return False
    old_parent_id = node.parent_id
    if old_parent_id == parent_id:
        return False
    if old_parent_id and old_parent_id in page.nodes:
        old_parent = page.nodes[old_parent_id]
        old_parent.children = [child for child in old_parent.children if child != node_id]
    page.roots = [root for root in page.roots if root != node_id]
    node.parent_id = parent_id
    if node_id not in parent.children:
        parent.children.append(node_id)
    return True


def _clear_generated_groups(page) -> None:
    generated = {
        node_id
        for node_id, node in page.nodes.items()
        if node.kind is NodeKind.GROUP and bool(node.metadata.get("pptx_group_generated"))
    }
    if not generated:
        return
    for node in page.nodes.values():
        if node.id in generated:
            continue
        if node.parent_id in generated:
            node.parent_id = None
        node.children = [child for child in node.children if child not in generated]
    for node_id in generated:
        page.nodes.pop(node_id, None)
    page.roots = [node.id for node in page.nodes.values() if not node.parent_id]


def _bounds(page, node_ids: list[str]) -> Rect | None:
    rects = [page.nodes[node_id].rect.normalized() for node_id in node_ids if node_id in page.nodes]
    if not rects:
        return None
    result = rects[0]
    for rect in rects[1:]:
        result = result.union(rect)
    return result


def _shape_name(node: ET.Element) -> str:
    candidates = (
        node.find(f"./{{{P_NS}}}nvSpPr/{{{P_NS}}}cNvPr"),
        node.find(f"./{{{P_NS}}}nvPicPr/{{{P_NS}}}cNvPr"),
        node.find(f"./{{{P_NS}}}nvGraphicFramePr/{{{P_NS}}}cNvPr"),
        node.find(f"./{{{P_NS}}}nvGrpSpPr/{{{P_NS}}}cNvPr"),
    )
    for candidate in candidates:
        if candidate is not None:
            return str(candidate.get("name") or "").strip()
    candidate = node.find(f".//{{{P_NS}}}cNvPr")
    return str(candidate.get("name") or "").strip() if candidate is not None else ""


def _tag(node: ET.Element) -> str:
    return node.tag.rsplit("}", 1)[-1]
