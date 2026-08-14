from pathlib import Path
import json, shutil

R=Path('work/files')
S=Path('staging/beta14/source')

shutil.copy2(S/'EncartesPPTXFields.py',R/'EncartesPPTXFields.py')
shutil.copy2(S/'Encartes14VisualPatch.js',R/'Encartes8_beta14.js')

html=R/'Encartes3_index.html'
text=html.read_text(encoding='utf-8')
text=text.replace('4.0.12 — Encartes Studio','4.0.13 — Encartes Studio')
if 'Encartes8_beta14.js' not in text:
    tag='\n<script src="Encartes8_beta14.js"></script>\n'
    idx=text.lower().rfind('</body>')
    text=(text[:idx]+tag+text[idx:]) if idx>=0 else text+tag
html.write_text(text,encoding='utf-8')

engine=R/'Encartes3Engine.py'
text=engine.read_text(encoding='utf-8')
if "APP_DIR / 'Encartes8_beta14.js'" not in text:
    text=text.replace("APP_DIR / 'Encartes7_beta13.js',","APP_DIR / 'Encartes7_beta13.js',\n    APP_DIR / 'Encartes8_beta14.js',")
text=text.replace("'version':'4.0.12-beta13'","'version':'4.0.13-beta14'")
text=text.replace('BETA 13 • IMAGENS AUTOMÁTICAS DO CANVA','BETA 14 • AJUSTE VISUAL DO CANVA')
engine.write_text(text,encoding='utf-8')

vpath=R/'version.json';v=json.loads(vpath.read_text(encoding='utf-8'))
v.update(distribution_version='4.0.13-hybrid.beta14',product_version='4.0.13',release_label='Beta 14',updated_at='2026-08-14T08:18:00-03:00')
vpath.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(R/'VERSAO.txt').write_text('SR Studio 4.0.13 • Beta 14\nAjuste visual do PPTX Canva: camadas corretas, imagem recortada no slot e autoajuste de nome/preço/unidade.\n',encoding='utf-8')
print('Beta 14 montada')
