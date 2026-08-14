from pathlib import Path
import json

R=Path('work/files')
S=Path('staging/beta16/source')
parts=['Encartes16Core.js','Encartes16Canvas.js','Encartes16UI.js']
code='\n'.join((S/p).read_text(encoding='utf-8') for p in parts)
(R/'Encartes10_beta16.js').write_text(code,encoding='utf-8')

html=R/'Encartes3_index.html'
text=html.read_text(encoding='utf-8')
text=text.replace('4.0.14 — Encartes Studio','4.0.15 — Encartes Studio')
if 'Encartes10_beta16.js' not in text:
    tag='\n<script src="Encartes10_beta16.js"></script>\n'
    idx=text.lower().rfind('</body>')
    text=(text[:idx]+tag+text[idx:]) if idx>=0 else text+tag
html.write_text(text,encoding='utf-8')

engine=R/'Encartes3Engine.py'
text=engine.read_text(encoding='utf-8')
if "APP_DIR / 'Encartes10_beta16.js'" not in text:
    text=text.replace("APP_DIR / 'Encartes9_beta15.js',","APP_DIR / 'Encartes9_beta15.js',\n    APP_DIR / 'Encartes10_beta16.js',")
text=text.replace("'version':'4.0.14-beta15'","'version':'4.0.15-beta16'")
text=text.replace('BETA 15 • EDITOR PRO + APRENDIZADO DE MODELO','BETA 16 • EDIÇÃO VISUAL ESTILO CANVA')
engine.write_text(text,encoding='utf-8')

vpath=R/'version.json';v=json.loads(vpath.read_text(encoding='utf-8'))
v.update(distribution_version='4.0.15-hybrid.beta16',product_version='4.0.15',release_label='Beta 16',updated_at='2026-08-14T10:45:00-03:00')
vpath.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(R/'VERSAO.txt').write_text('SR Studio 4.0.15 • Beta 16\nEditor visual inspirado no fluxo do Canva: seleção natural, multi-seleção, 8 alças, rotação, edição direta, recorte, barra flutuante, posição, alinhamento, grupos, camadas e atalhos.\n',encoding='utf-8')
print('Beta 16 montada')
