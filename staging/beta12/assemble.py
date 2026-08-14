from pathlib import Path
import json, shutil

R=Path('work/files')
S11=Path('staging/beta11/source')
S12=Path('staging/beta12/source')

for name in ['EncartesPPTXReader.py','EncartesPPTXVisual.py']:
    shutil.copy2(S12/name,R/name)

modules=[
    S11/'Encartes11State.js',
    S11/'Encartes11Data.js',
    S11/'Encartes11Validation.js',
    S11/'Encartes11UIBase.js',
    S12/'Encartes11Canvas.js',
    S11/'Encartes11InspectorFields.js',
    S11/'Encartes11InspectorRender.js',
    S12/'Encartes11Events.js',
]
code='\n'.join(p.read_text(encoding='utf-8') for p in modules)
code=code.replace("A.VERSION='4.0.10 • Beta 11'","A.VERSION='4.0.11 • Beta 12'")
(R/'Encartes6_beta12.js').write_text(code,encoding='utf-8')
(R/'Encartes5_beta11.js').unlink(missing_ok=True)

html=(R/'Encartes3_index.html').read_text(encoding='utf-8')
html=html.replace('4.0.10 — Encartes Studio','4.0.11 — Encartes Studio').replace('Encartes5_beta11.js','Encartes6_beta12.js')
(R/'Encartes3_index.html').write_text(html,encoding='utf-8')

engine=R/'Encartes3Engine.py'
text=engine.read_text(encoding='utf-8')
text=text.replace("APP_DIR / 'Encartes5_beta11.js'","APP_DIR / 'Encartes6_beta12.js'")
text=text.replace("'version':'4.0.10-beta11'","'version':'4.0.11-beta12'")
text=text.replace('BETA 11 • NOVO EDITOR OFICIAL','BETA 12 • DESIGN COMPLETO DO CANVA')
engine.write_text(text,encoding='utf-8')

vpath=R/'version.json';v=json.loads(vpath.read_text(encoding='utf-8'))
v.update(distribution_version='4.0.11-hybrid.beta12',product_version='4.0.11',release_label='Beta 12',updated_at='2026-08-13T23:18:00-03:00')
vpath.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(R/'VERSAO.txt').write_text('SR Studio 4.0.11 • Beta 12\nPPTX Canva com design completo renderizado pelo PowerPoint, mantendo os campos dinâmicos editáveis.\n',encoding='utf-8')
print('Beta 12 montada')
