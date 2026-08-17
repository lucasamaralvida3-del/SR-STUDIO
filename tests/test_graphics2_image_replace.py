from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from PIL import Image

from srstudio.graphics2 import BindingRole, GraphicsCommandRouter, GraphicsDocument, GraphicsNode, GraphicsSession, NodeKind, SmartSlot, Transform
from srstudio.graphics2.package import load_package, save_package


def test_replace_image_keeps_frame_updates_slot_and_survives_package_round_trip(tmp_path: Path):
    source = tmp_path / "produto-novo.png"
    Image.new("RGBA", (320, 180), (255, 255, 255, 255)).save(source)

    document = GraphicsDocument(name="Troca de imagem")
    page = document.active_page
    image = GraphicsNode(
        kind=NodeKind.IMAGE,
        name="Imagem do produto",
        transform=Transform(x=120, y=260, width=280, height=210),
        style={
            "fit": "cover",
            "zoom": 1.35,
            "focus_x": 0.42,
            "focus_y": 0.61,
            "crop": {"l": 0.03, "t": 0.02, "r": 0.04, "b": 0.01},
        },
        metadata={
            "graphics2_preview_original_source": "C:/old/preview.png",
            "source_url": "C:/old/source.png",
            "bound_image_source": "C:/old/product.png",
        },
    )
    page.add_node(image)
    slot = SmartSlot(
        name="Produto 1",
        page_id=page.id,
        node_by_role={BindingRole.IMAGE.value: image.id},
        product_id="produto-1",
        metadata={
            "product_snapshot": {
                "id": "produto-1",
                "display_name": "PRODUTO 1",
                "image_path": "C:/old/product.png",
            }
        },
    )
    page.slots[slot.id] = slot

    geometry_before = deepcopy(image.transform)
    style_before = deepcopy(image.style)
    router = GraphicsCommandRouter(GraphicsSession(document))

    result = router.dispatch(
        {
            "name": "replace_image",
            "node_id": image.id,
            "source": source.as_uri(),
        }
    )

    assert result.ok is True
    assert result.changed is True
    assert image.transform == geometry_before
    assert image.style == style_before
    assert image.asset_id in document.assets
    asset = document.assets[image.asset_id]
    assert Path(asset.source) == source.resolve()
    assert asset.width == 320
    assert asset.height == 180
    assert asset.mime == "image/png"
    assert image.metadata["bound_image_source"] == str(source.resolve())
    assert image.metadata["image_replaced_by_user"] is True
    assert "graphics2_preview_original_source" not in image.metadata
    assert "source_url" not in image.metadata
    assert slot.product_id == "produto-1"
    assert slot.metadata["product_snapshot"]["image_path"] == str(source.resolve())
    assert slot.metadata["product_snapshot"]["image_asset_id"] == image.asset_id

    package = save_package(document, tmp_path / "imagem-trocada.srscene", embed_local_assets=True)
    restored = load_package(package, extract_assets_to=tmp_path / "restored")
    restored_image = restored.active_page.nodes[image.id]
    restored_asset = restored.assets[restored_image.asset_id]

    assert Path(restored_asset.source).is_file()
    assert restored_image.metadata["bound_image_source"] == restored_asset.source
    assert restored_image.transform == geometry_before
    assert restored_image.style == style_before


def test_replace_image_rejects_missing_file_without_mutating_node(tmp_path: Path):
    document = GraphicsDocument(name="Troca inválida")
    page = document.active_page
    image = GraphicsNode(
        kind=NodeKind.IMAGE,
        transform=Transform(x=10, y=20, width=100, height=80),
        asset_id="asset-old",
        metadata={"bound_image_source": "old.png"},
    )
    page.add_node(image)
    before = deepcopy(image)
    router = GraphicsCommandRouter(GraphicsSession(document))

    result = router.dispatch({"name": "replace_image", "node_id": image.id, "source": str(tmp_path / "missing.png")})

    assert result.ok is False
    assert result.changed is False
    assert image.asset_id == before.asset_id
    assert image.metadata == before.metadata
    assert image.transform == before.transform
