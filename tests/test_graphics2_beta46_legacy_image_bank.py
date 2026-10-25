from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest
from PIL import Image

from srstudio.graphics2.item_slot_host import ItemSlotCommandRouter
from srstudio.graphics2.item_slots import create_item_slot
from srstudio.graphics2.legacy_image_bank_bridge import (
    approved_legacy_image, complete_product_image, hydrate_legacy_bank
)
from srstudio.graphics2.model import GraphicsDocument, GraphicsPage, BindingRole
from srstudio.graphics2.operations import GraphicsSession
from srstudio.images.library import ImageLibrary
from runpy import run_path

# The release recovery CLI lives under tools/ rather than the installed
# Python package. Resolve its exact file on both Windows and Ubuntu.
recover_standalone_images = run_path(
    str(Path(__file__).resolve().parents[1] / "tools" / "recover_historical_product_images_beta46.py")
)["recover_standalone_images"]
install_review_bank = run_path(
    str(Path(__file__).resolve().parents[1] / "tools" / "install_historical_review_bank_beta46.py")
)["install_review_bank"]


def picture(path: Path, color: str) -> Path:
    Image.new("RGB", (64, 84), color).save(path)
    return path


def approved(bank: ImageLibrary, path: Path, *, name: str, ean: str = "", code: str = "",
             accepted: bool = True, preferred: bool = False):
    return bank.import_image(
        path, product_key=name, product_name=name,
        kind="product", source_kind="manual-review",
        review_status="accepted" if accepted else "pending",
        preferred=preferred, metadata={"ean": ean, "code": code}
    )


def test_approved_match_by_ean_and_code_then_full_name(tmp_path, monkeypatch):
    root = tmp_path / "images"
    monkeypatch.setenv("SR_STUDIO_IMAGE_LIBRARY_ROOT", str(root))
    bank = ImageLibrary(root)
    img = picture(tmp_path / "rice.png", "blue")
    approved(bank, img, name="ARROZ VASCONCELOS 5KG", ean="07891234001235", code="123")
    # ImageLibrary stores the picture under its private content-addressed root.
    ean = approved_legacy_image({"ean":"07891234001235", "name": "OTHER"})
    assert ean and Path(ean["image_path"]).is_file()
    assert ean["image_linked_by"] == "approved_legacy_ean"
    code = approved_legacy_image({"id":"123", "name":"OTHER"})
    assert code and code["image_path"] == ean["image_path"]
    name = approved_legacy_image({"name":"ARROZ VASCONCELOS 5KG"})
    assert name and name["image_linked_by"] == "approved_legacy_exact_name"
    assert approved_legacy_image({"name":"ARROZ VASCONCELOS"}) is None
    assert approved_legacy_image({"ean":"99999999", "name":"OTHER"}) is None


def test_review_images_never_used_and_ambiguity_is_not_guessed(tmp_path, monkeypatch):
    root = tmp_path / "bank"
    monkeypatch.setenv("SR_STUDIO_IMAGE_LIBRARY_ROOT",str(root))
    bank = ImageLibrary(root)
    pending = approved(bank, picture(tmp_path / "pending.png", "red"),
                       name="FLOCAO 500G", accepted=False)
    assert approved_legacy_image({"name":"FLOCAO 500G"}) is None
    assert pending.review_status == "pending"
    one = approved(bank, picture(tmp_path / "a.png", "blue"),
                   name="ARROZ 5KG", code="220")
    two = approved(bank, picture(tmp_path / "b.png", "green"),
                   name="ARROZ 5KG", code="220")
    assert approved_legacy_image({"id":"220", "name":"ARROZ 5KG"}) is None
    bank.set_preferred(one.id, True)
    matching = approved_legacy_image({"id":"220", "name":"ARROZ 5KG"})
    assert matching and Path(matching["image_path"]).is_file()
    assert matching["image_bank_asset_id"] == one.id
    # Rejecting the preferred candidate makes the remaining reviewed image usable.
    bank.set_review_status(one.id, "rejected")
    assert approved_legacy_image({"id":"220"})["image_bank_asset_id"] == two.id


def test_manual_and_catalog_picture_take_precedence_over_legacy(tmp_path, monkeypatch):
    bank_dir = tmp_path / "official"
    monkeypatch.setenv("SR_STUDIO_IMAGE_LIBRARY_ROOT", str(bank_dir))
    bank = ImageLibrary(bank_dir)
    approved(bank, picture(tmp_path / "legacy.png", "blue"),
             name="CAFE 500G", code="840")
    manual = picture(tmp_path / "manual.png","red")
    original = complete_product_image({"id":"840","name":"CAFE 500G",
                                       "image_path":str(manual)})
    assert original["image_path"] == str(manual)
    resolved = complete_product_image({"id":"840","name":"CAFE 500G"},
                                      manual_links={"840":{"image_path":str(manual)}})
    assert resolved["image_linked_by"] == "product_id"
    assert resolved["image_path"] == str(manual)
    no_manual = complete_product_image({"id":"840","name":"CAFE 500G"},manual_links={})
    assert no_manual["image_linked_by"] == "approved_legacy_code"


def test_catalog_hydrate_then_bind_slot_keeps_user_design_and_png(tmp_path, monkeypatch):
    root = tmp_path / "legacy"
    monkeypatch.setenv("SR_STUDIO_IMAGE_LIBRARY_ROOT", str(root))
    bank = ImageLibrary(root)
    approved(bank, picture(tmp_path / "product.png", "green"),
             name="CAFE EXTRA FORTE 500G", code="900")
    document = GraphicsDocument(name="SR")
    document.add_page(GraphicsPage(width=1080,height=1350))
    document.metadata["products"] = [{"id":"900","name":"CAFE EXTRA FORTE 500G","price":"14,99"},
                                      {"id":"901","name":"CAFE EXTRA FORTE 400G","price":"9,99"}]
    assert hydrate_legacy_bank(document,root=root)==1
    assert hydrate_legacy_bank(document,root=root)==0
    assert "image_path" in document.metadata["products"][0]
    assert "image_path" not in document.metadata["products"][1]
    session = GraphicsSession(document)
    slot = create_item_slot(session,"individual-beta44")
    price_node = session.page.node(slot.node_by_role[BindingRole.PRICE_REAIS.value])
    response = ItemSlotCommandRouter(session).dispatch({
        "name":"bind_product", "slot_id":slot.id,"product_id":"900"})
    assert response.ok
    assert price_node.text == "14"
    pic = session.page.node(slot.node_by_role[BindingRole.IMAGE.value])
    assert pic.visible and Path(pic.metadata["bound_image_source"]).is_file()
    assert len(session.document.assets)==1


def test_zip_recovery_filters_art_and_keeps_candidates_pending(tmp_path):
    archive=tmp_path / "standalone-images.zip"
    rows=[]
    with zipfile.ZipFile(archive,"w") as z:
        for index,kind in enumerate(("candidate","candidate","decorative")):
            buffer=io.BytesIO()
            Image.new("RGB",(24,24),("blue","green","red")[index]).save(buffer,format="PNG")
            data=buffer.getvalue()
            name=f"photo-{index}.png"
            z.writestr(name,data)
            rows.append({
                "filename":name,"sha256":hashlib.sha256(data).hexdigest(),
                "classification":kind,"valid":True,
                "provenance":{"zip_member":name}
            })
    sha=hashlib.sha256(archive.read_bytes()).hexdigest()
    metadata={"release_tag":"image-db-corpus-v1",
              "asset":{"sha256":sha,"name":"standalone-images.zip"},
              "images":rows}
    manifest=tmp_path / "manifest.json"
    manifest.write_text(json.dumps(metadata),encoding="utf-8")
    dest=tmp_path / "recovered"
    report=recover_standalone_images(archive,manifest,dest)
    assert report["imported"]==2
    assert report["rejected_decorative_or_invalid"]==1
    assert report["accepted_automatically"]==0
    records=ImageLibrary(dest).all()
    assert len(records)==2
    assert all(record.review_status=="pending" and record.kind=="unknown" for record in records)
    # A ZIP with image files cannot change matches without explicit approval.
    assert approved_legacy_image({"name":"photo-0"},root=dest) is None
    twice=recover_standalone_images(archive,manifest,dest)
    assert twice["imported"]==0 and twice["duplicates"]==2
    assert len(ImageLibrary(dest).all())==2


def test_review_artifact_installs_portably_without_auto_approvals(tmp_path):
    from srstudio.graphics2.legacy_image_bank_bridge import approved_legacy_image
    archive=tmp_path/"single.zip"
    buffer=io.BytesIO()
    Image.new("RGB",(42,54),"blue").save(buffer,format="PNG")
    data=buffer.getvalue()
    with zipfile.ZipFile(archive,"w") as z:
        z.writestr("legacy.png",data)
    sha=hashlib.sha256(archive.read_bytes()).hexdigest()
    manifest=tmp_path/"manifest.json"
    manifest.write_text(json.dumps({
        "release_tag":"image-db-corpus-v1",
        "asset":{"name":"standalone-images.zip","sha256":sha},
        "images":[{"filename":"legacy.png",
                   "sha256":hashlib.sha256(data).hexdigest(),
                   "classification":"candidate","valid":True,
                   "provenance":{"zip_member":"legacy.png"}}]
    }),encoding="utf-8")
    stage=tmp_path/"github-runner"
    recover_standalone_images(archive,manifest,stage)
    target=tmp_path/"user-computer"
    first=install_review_bank(stage,target)
    assert first["installed_pending"] == 1
    assert first["auto_approved"] == 0
    second=install_review_bank(stage,target)
    assert second["already_present"] == 1 and second["installed_pending"] == 0
    saved=ImageLibrary(target).all()
    assert len(saved)==1
    assert Path(saved[0].path).is_file()
    assert str(target) in saved[0].path
    assert approved_legacy_image({"name":"legacy"},root=target) is None
    # Editing the source after recovery must abort the install.
    (stage/"assets"/Path(saved[0].path).name).write_bytes(b"BAD")
    with pytest.raises(ValueError,match="Integridade"):
        install_review_bank(stage,tmp_path/"another")


def test_recovery_rejects_zip_modification_before_writing(tmp_path):
    archive=tmp_path/"archive.zip"
    with zipfile.ZipFile(archive,"w") as z:
        z.writestr("photo.jpg",b"tampered")
    manifest=tmp_path/"manifest.json"
    manifest.write_text(json.dumps({"release_tag":"image-db-corpus-v1",
                                    "asset":{"sha256":"0"*64},
                                    "images":[]}),encoding="utf-8")
    destination=tmp_path/"never"
    with pytest.raises(ValueError,match="SHA-256"):
        recover_standalone_images(archive,manifest,destination)
    assert not destination.exists()
