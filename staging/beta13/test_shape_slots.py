from __future__ import annotations
import io, zipfile
from EncartesPPTXReader import parse_pptx

P='http://schemas.openxmlformats.org/presentationml/2006/main'
A='http://schemas.openxmlformats.org/drawingml/2006/main'
R='http://schemas.openxmlformats.org/officeDocument/2006/relationships'

presentation=f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation xmlns:p="{P}" xmlns:a="{A}" xmlns:r="{R}">
  <p:sldSz cx="10000000" cy="12500000"/>
</p:presentation>'''

slide=f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:p="{P}" xmlns:a="{A}" xmlns:r="{R}"><p:cSld><p:spTree>
  <p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/>
  <p:grpSp>
    <p:nvGrpSpPr><p:cNvPr id="2" name="Grupo Produto"/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
    <p:grpSpPr><a:xfrm><a:off x="1000000" y="3000000"/><a:ext cx="3000000" cy="3000000"/><a:chOff x="0" y="0"/><a:chExt cx="3000000" cy="3000000"/></a:xfrm></p:grpSpPr>
    <p:sp>
      <p:nvSpPr><p:cNvPr id="3" name="Freeform Foto"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
      <p:spPr><a:xfrm><a:off x="100000" y="200000"/><a:ext cx="2100000" cy="1800000"/></a:xfrm><a:solidFill><a:srgbClr val="FFFFFF"/></a:solidFill></p:spPr>
    </p:sp>
  </p:grpSp>
  <p:sp><p:nvSpPr><p:cNvPr id="10" name="Nome Produto"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:spPr><a:xfrm><a:off x="1100000" y="2800000"/><a:ext cx="2300000" cy="300000"/></a:xfrm></p:spPr><p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:rPr sz="2400"/><a:t>ACEM BOVINO</a:t></a:r></a:p></p:txBody></p:sp>
  <p:sp><p:nvSpPr><p:cNvPr id="11" name="Reais"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:spPr><a:xfrm><a:off x="3000000" y="4900000"/><a:ext cx="900000" cy="800000"/></a:xfrm></p:spPr><p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:rPr sz="5000"/><a:t>33</a:t></a:r></a:p></p:txBody></p:sp>
  <p:sp><p:nvSpPr><p:cNvPr id="12" name="Centavos"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:spPr><a:xfrm><a:off x="3850000" y="5000000"/><a:ext cx="400000" cy="300000"/></a:xfrm></p:spPr><p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:rPr sz="2600"/><a:t>,64</a:t></a:r></a:p></p:txBody></p:sp>
</p:spTree></p:cSld></p:sld>'''

buf=io.BytesIO()
with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED) as z:
    z.writestr('ppt/presentation.xml',presentation)
    z.writestr('ppt/slides/slide1.xml',slide)

result=parse_pptx(buf.getvalue(),'teste_caixa_branca.pptx')
assert result['pageCount']==1,result
assert result['slotCount']>=1,result
assert result['autoImageSlotCount']>=1,result
slot=result['pages'][0]['templateSlots'][0]
assert 'IMAGEM' in slot['fields'],slot
assert slot['fields']['IMAGEM'].get('autoDetected') is True,slot
print('Beta 13 shape slot OK:',result['autoImageSlotCount'])
