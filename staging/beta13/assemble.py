from pathlib import Path
import json, shutil

R=Path('work/files')
S=Path('staging/beta13/source')

for name in ['EncartesPPTXFields.py','EncartesPPTXReader.py']:
    shutil.copy2(S/name,R/name)

old=R/'Encartes6_beta12.js'
new=R/'Encartes7_beta13.js'
code=old.read_text(encoding='utf-8')
code=code.replace("A.VERSION='4.0.11 • Beta 12'","A.VERSION='4.0.12 • Beta 13'")
code=code.replace("'PPTX: design completo preservado · '+(data.slotCount||0)+' bloco(s)'","'PPTX: design completo · '+(data.autoImageSlotCount||0)+' área(s) de imagem · '+(data.slotCount||0)+' bloco(s)'")
new.write_text(code,encoding='utf-8')
old.unlink(missing_ok=True)

html=R/'Encartes3_index.html'
text=html.read_text(encoding='utf-8').replace('4.0.11 — Encartes Studio','4.0.12 — Encartes Studio').replace('Encartes6_beta12.js','Encartes7_beta13.js')
html.write_text(text,encoding='utf-8')

engine=R/'Encartes3Engine.py'
text=engine.read_text(encoding='utf-8')
text=text.replace("APP_DIR / 'Encartes6_beta12.js'","APP_DIR / 'Encartes7_beta13.js'")
text=text.replace("'version':'4.0.11-beta12'","'version':'4.0.12-beta13'")
text=text.replace('BETA 12 • DESIGN COMPLETO DO CANVA','BETA 13 • IMAGENS AUTOMÁTICAS DO CANVA')
engine.write_text(text,encoding='utf-8')

vpath=R/'version.json';v=json.loads(vpath.read_text(encoding='utf-8'))
v.update(distribution_version='4.0.12-hybrid.beta13',product_version='4.0.12',release_label='Beta 13',updated_at='2026-08-14T07:35:00-03:00')
vpath.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(R/'VERSAO.txt').write_text('SR Studio 4.0.12 • Beta 13\nPPTX Canva: reconhecimento automático de caixas brancas/Freeforms agrupadas como áreas de imagem de produto.\n',encoding='utf-8')
print('Beta 13 montada')
