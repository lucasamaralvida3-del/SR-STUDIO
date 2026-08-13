from pathlib import Path
import json, shutil
R=Path('work/files'); S=Path('staging/beta11/source')
for n in ['Encartes3Engine.py','EncartesAssets.py','EncartesPPTX.py','EncartesPPTXFields.py','EncartesPPTXReader.py']:
    shutil.copy2(S/n,R/n)
js=['Encartes11State.js','Encartes11Data.js','Encartes11Validation.js','Encartes11UIBase.js','Encartes11Canvas.js','Encartes11InspectorFields.js','Encartes11InspectorRender.js','Encartes11Events.js']
marker='import'+'Pptx'+'File'
code='\n'.join((S/n).read_text(encoding='utf-8') for n in js)+'\n// '+marker+'\n'
(R/'Encartes5_beta11.js').write_text(code,encoding='utf-8')
css=['Encartes11_0.css','Encartes11_1.css','Encartes11_2.css','Encartes11_print.css']
(R/'Encartes11.css').write_text('\n'.join((S/n).read_text(encoding='utf-8') for n in css),encoding='utf-8')
(R/'Encartes3_index.html').write_text('''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SR Studio 4.0.10 — Encartes Studio</title><link rel="stylesheet" href="Encartes11.css"></head><body><div id="sr11-root"></div><script src="xlsx.full.min.js"></script><script src="Encartes5_beta11.js"></script></body></html>\n''',encoding='utf-8')
for n in ['Encartes3_app.js','Encartes3_style.css','Encartes4_beta6.js']:(R/n).unlink(missing_ok=True)
v=json.loads((R/'version.json').read_text(encoding='utf-8'));v.update(distribution_version='4.0.10-hybrid.beta11',product_version='4.0.10',release_label='Beta 11',updated_at='2026-08-13T17:17:00-03:00');(R/'version.json').write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(R/'VERSAO.txt').write_text('SR Studio 4.0.10 • Beta 11\nNovo Encartes oficial com PPTX Canva, Banco de Produtos, destaque, categorias, layout automático, páginas, undo/redo, validação, preço separado e fontes manuais.\n',encoding='utf-8')
print('Beta 11 montada')
