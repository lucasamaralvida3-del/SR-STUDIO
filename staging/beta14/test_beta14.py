from __future__ import annotations
import sys, types, unicodedata
from pathlib import Path
import xml.etree.ElementTree as ET

stub=types.ModuleType('SRStudio21')
stub.norm=lambda s: ''.join(c for c in unicodedata.normalize('NFD',str(s or '')) if unicodedata.category(c)!='Mn').strip().upper()
sys.modules['SRStudio21']=stub

from EncartesPPTXFields import font_info,NS

xml=f'''<p:sp xmlns:p="{NS['p']}" xmlns:a="{NS['a']}">
<p:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="1000" cy="400"/></a:xfrm></p:spPr>
<p:txBody><a:bodyPr anchor="b"/><a:lstStyle/><a:p><a:pPr algn="ctr"/><a:r><a:rPr sz="4200" b="1"><a:latin typeface="Arial"/><a:solidFill><a:srgbClr val="FFFFFF"/></a:solidFill></a:rPr><a:t>TESTE</a:t></a:r></a:p></p:txBody>
</p:sp>'''
style=font_info(ET.fromstring(xml))
assert style['align']=='center',style
assert style['vAlign']=='bottom',style
assert style['font']=='Arial',style
assert style['bold'] is True,style

patch=Path('work/files/Encartes8_beta14.js').read_text(encoding='utf-8')
for token in ["zIndex='8'","zIndex='45'","overflow='hidden'",'fitText','imageSafeBox','objectFit']:
    assert token in patch,token
html=Path('work/files/Encartes3_index.html').read_text(encoding='utf-8')
assert 'Encartes7_beta13.js' in html
assert 'Encartes8_beta14.js' in html
print('Beta 14 visual checks OK')
