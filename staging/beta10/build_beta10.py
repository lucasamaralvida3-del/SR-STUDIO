from pathlib import Path
import json, subprocess, sys
root=Path(sys.argv[1]); p=root/'files'; here=Path(__file__).resolve().parent
subprocess.run([sys.executable,str(here/'patch_engine.py'),str(root)],check=True)
subprocess.run([sys.executable,str(here/'patch_editor.py'),str(root)],check=True)
v=json.loads((p/'version.json').read_text(encoding='utf-8'))
v.update(distribution_version='4.0.9-hybrid.beta10',product_version='4.0.9',release_label='Beta 10',updated_at='2026-08-13T17:05:00-03:00')
(p/'version.json').write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(p/'VERSAO.txt').write_text('SR Studio 4.0.9 • Beta 10\nImportação do Encartes integrada automaticamente ao Banco de Produtos.\n',encoding='utf-8')
h=p/'Encartes3_index.html'; s=h.read_text(encoding='utf-8').replace('SR Studio 4.0.8 • Beta 9','SR Studio 4.0.9 • Beta 10').replace('SR Studio 4.0.8 — Encartes Studio','SR Studio 4.0.9 — Encartes Studio'); h.write_text(s,encoding='utf-8')
e=p/'Encartes3Engine.py'; s=e.read_text(encoding='utf-8').replace('BETA 8 • LOCAL FIRST','BETA 10 • BANCO AUTOMÁTICO'); e.write_text(s,encoding='utf-8')
j=p/'Encartes4_beta6.js'; s=j.read_text(encoding='utf-8').replace('BETA 9 · NOVO ENCARTES','BETA 10 · BANCO AUTOMÁTICO').replace('4.0.8 • BETA 9','4.0.9 • BETA 10'); j.write_text(s,encoding='utf-8')
print('Beta 10 aplicada')
