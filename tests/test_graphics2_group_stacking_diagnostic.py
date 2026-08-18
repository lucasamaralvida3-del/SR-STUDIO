from __future__ import annotations

from srstudio.graphics2.model import GraphicsNode, GraphicsPage, NodeKind, Transform


def _paint_order(page: GraphicsPage) -> list[str]:
    """Espelha somente a seleção/ordenação global usada pelo renderer atual."""

    return [
        node.name
        for node in page.ordered_nodes()
        if node.visible and node.kind is not NodeKind.GROUP
    ]


def _overlap(a: GraphicsNode, b: GraphicsNode) -> bool:
    ar = a.rect.normalized()
    br = b.rect.normalized()
    return ar.x < br.right and ar.right > br.x and ar.y < br.bottom and ar.bottom > br.y


def test_global_paint_order_can_interleave_external_node_between_group_children() -> None:
    """Fixture diagnóstica: documenta a suscetibilidade, sem corrigir o renderer.

    A semântica composta esperada para esta árvore é G(A, B) seguido de C, isto
    é, A -> B -> C. Se os z_index forem não contíguos, a ordenação global atual
    pode pintar C entre os dois filhos: A -> C -> B.
    """

    page = GraphicsPage(width=300.0, height=300.0)
    group = GraphicsNode(
        id="group-g",
        kind=NodeKind.GROUP,
        name="G",
        transform=Transform(x=20.0, y=20.0, width=180.0, height=180.0),
        z_index=10,
    )
    child_a = GraphicsNode(
        id="child-a",
        kind=NodeKind.RECT,
        name="A",
        transform=Transform(x=30.0, y=30.0, width=140.0, height=140.0),
        z_index=10,
    )
    external_c = GraphicsNode(
        id="external-c",
        kind=NodeKind.RECT,
        name="C",
        transform=Transform(x=50.0, y=50.0, width=140.0, height=140.0),
        z_index=11,
    )
    child_b = GraphicsNode(
        id="child-b",
        kind=NodeKind.RECT,
        name="B",
        transform=Transform(x=70.0, y=70.0, width=140.0, height=140.0),
        z_index=12,
    )

    page.add_node(group)
    page.add_node(child_a, parent_id=group.id)
    page.add_node(external_c)
    page.add_node(child_b, parent_id=group.id)

    expected_group_traversal = ["A", "B", "C"]
    observed_global_paint_order = _paint_order(page)

    assert [page.node(node_id).name for node_id in group.children] == ["A", "B"]
    assert expected_group_traversal == ["A", "B", "C"]
    assert observed_global_paint_order == ["A", "C", "B"]
    assert _overlap(child_a, external_c)
    assert _overlap(external_c, child_b)
