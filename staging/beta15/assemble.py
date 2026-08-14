from pathlib import Path
import json

R=Path('work/files')
S=Path('staging/beta15/source')
parts=['Encartes15Core.js','Encartes15Render.js','Encartes15Tools.js','Encartes15Project.js']
code='\n'.join((S/p).read_text(encoding='utf-8') for p in parts)
(R/'Encartes9_beta15.js').write_text(code,encoding='utf-8')

html=R/'Encartes3_index.html'
text=html.read_text(encoding='utf-8')
text=text.replace('4.0.13 — Encartes Studio','4.0.14 — Encartes Studio')
if 'Encartes9_beta15.js' not in text:
    tag='\n<script src="Encartes9_beta15.js"></script>\n'
    idx=text.lower().rfind('</body>')
    text=(text[:idx]+tag+text[idx:]) if idx>=0 else text+tag
html.write_text(text,encoding='utf-8')

engine=R/'Encartes3Engine.py'
text=engine.read_text(encoding='utf-8')
if "APP_DIR / 'Encartes9_beta15.js'" not in text:
    text=text.replace("APP_DIR / 'Encartes8_beta14.js',","APP_DIR / 'Encartes8_beta14.js',\n    APP_DIR / 'Encartes9_beta15.js',")
text=text.replace("'version':'4.0.13-beta14'","'version':'4.0.14-beta15'")
text=text.replace('BETA 14 • AJUSTE VISUAL DO CANVA','BETA 15 • EDITOR PRO + APRENDIZADO DE MODELO')
engine.write_text(text,encoding='utf-8')

vpath=R/'version.json';v=json.loads(vpath.read_text(encoding='utf-8'))
v.update(distribution_version='4.0.14-hybrid.beta15',product_version='4.0.14',release_label='Beta 15',updated_at='2026-08-14T09:55:00-03:00')
vpath.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(R/'VERSAO.txt').write_text('SR Studio 4.0.14 • Beta 15\nEditor PRO: edição manual por partes, aprender modelo, copiar ajustes, guias inteligentes, camadas, foco/zoom de imagem, versões e backup de projeto.\n',encoding='utf-8')
print('Beta 15 montada')
