from pathlib import Path
import json, shutil

root=Path('work/files')
staging=Path('staging/beta8')
shutil.copy2(staging/'Encartes3Engine.py',root/'Encartes3Engine.py')

v=json.loads((root/'version.json').read_text(encoding='utf-8'))
v.update(distribution_version='4.0.7-hybrid.beta8',product_version='4.0.7',release_label='Beta 8',updated_at='2026-08-13T16:34:00-03:00')
(root/'version.json').write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(root/'VERSAO.txt').write_text('SR Studio 4.0.7 • Beta 8\nCorrige a aba vazia do Studio de Encartes e ativa o editor local-first.\n',encoding='utf-8')

h=root/'Encartes3_index.html'
text=h.read_text(encoding='utf-8')
text=text.replace('SR Studio 4.0.6 — Encartes Intelligence','SR Studio 4.0.7 — Encartes Studio')
text=text.replace('SR Studio 4.0.6 • Beta 7','SR Studio 4.0.7 • Beta 8')
text=text.replace('Encartes Intelligence 4.0.6 pronto','Encartes Studio 4.0.7 pronto')
h.write_text(text,encoding='utf-8')

j=root/'Encartes4_beta6.js'
js=j.read_text(encoding='utf-8')
js=js.replace('BETA 7 · NOVO ENCARTES','BETA 8 · NOVO ENCARTES')
js=js.replace('4.0.6 • BETA 7','4.0.7 • BETA 8')
j.write_text(js,encoding='utf-8')
print('Beta 8 aplicada ao pacote base')
