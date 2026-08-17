from __future__ import annotations

from xml.etree import ElementTree as ET

from srstudio.graphics2.model import GraphicsDocument, GraphicsNode, NodeKind, Transform
from srstudio.graphics2.pptx_fidelity import A_NS, P_NS, PptxFidelityReport, _enrich_page


def test_pptx_custom_geometry_on_image_becomes_clip_path_without_moving_node():
    document = GraphicsDocument(name="Canva image clip")
    page = document.active_page
    image = GraphicsNode(
        kind=NodeKind.IMAGE,
        name="Freeform Image 7",
        transform=Transform(x=120, y=180, width=420, height=310),
        metadata={"source_name": "Freeform Image 7"},
    )
    page.add_node(image)
    before = (
        image.transform.x,
        image.transform.y,
        image.transform.width,
        image.transform.height,
    )

    root = ET.fromstring(
        f"""
        <p:sld xmlns:p="{P_NS}" xmlns:a="{A_NS}">
          <p:cSld><p:spTree>
            <p:sp>
              <p:nvSpPr><p:cNvPr id="7" name="Freeform Image 7"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
              <p:spPr>
                <a:custGeom>
                  <a:avLst/><a:gdLst/><a:ahLst/><a:cxnLst/><a:rect l="l" t="t" r="r" b="b"/>
                  <a:pathLst><a:path w="1000" h="1000">
                    <a:moveTo><a:pt x="0" y="0"/></a:moveTo>
                    <a:lnTo><a:pt x="1000" y="0"/></a:lnTo>
                    <a:lnTo><a:pt x="850" y="1000"/></a:lnTo>
                    <a:lnTo><a:pt x="0" y="800"/></a:lnTo>
                    <a:close/>
                  </a:path></a:pathLst>
                </a:custGeom>
                <a:blipFill/>
              </p:spPr>
            </p:sp>
          </p:spTree></p:cSld>
        </p:sld>
        """
    )
    report = PptxFidelityReport()

    _enrich_page(page, root, 1000, 1000, report)

    assert report.image_clips_enriched == 1
    assert report.custom_paths_enriched == 0
    assert image.metadata["clip_path"]["paths"][0]["commands"][-1]["op"] == "Z"
    assert (
        image.transform.x,
        image.transform.y,
        image.transform.width,
        image.transform.height,
    ) == before
