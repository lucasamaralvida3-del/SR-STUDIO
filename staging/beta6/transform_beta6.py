from __future__ import annotations
import glob, json, os, pathlib, sys

root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else 'work').resolve()
staging = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else 'staging/beta6').resolve()
files = root / 'files'
if not files.is_dir(): raise SystemExit('Pasta files nao encontrada')

meta = json.loads((staging / 'READY_TRANSFORM.json').read_text(encoding='utf-8'))
version_path = files / 'version.json'
version = json.loads(version_path.read_text(encoding='utf-8'))
for key in ('distribution_version','product_version','release_label'):
    version[key] = meta[key]
version['updated_at'] = meta['created_at']
version_path.write_text(json.dumps(version, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')

(files/'VERSAO.txt').write_text(
    f"SR Studio {meta['product_version']} • {meta['release_label']}\n"
    "Novo núcleo do Studio de Encartes: canvas livre, blocos inteligentes, drag-and-drop, grid, validação, autosave e impressão/PDF.\n",
    encoding='utf-8'
)

parts=sorted(glob.glob(str(staging/'editor.*.js.part')))
if not parts: raise SystemExit('Partes do editor Beta 6 ausentes')
dst = files / 'Encartes4_beta6.js'
dst.write_text(''.join(pathlib.Path(p).read_text(encoding='utf-8') for p in parts), encoding='utf-8')
marker = '<!-- SR_STUDIO_BETA6_ENCARTES -->'
targets=[]
for html in files.rglob('*.html'):
    try: text=html.read_text(encoding='utf-8')
    except UnicodeDecodeError: continue
    low=text.lower()
    if marker in text: targets.append(html); continue
    if 'encartes3_app.js' in low or 'studio de encartes' in low or 'encartes3' in html.name.lower():
        rel=os.path.relpath(dst, html.parent).replace(os.sep,'/')
        tag=f'\n{marker}\n<script src="{rel}"></script>\n'
        idx=low.rfind('</body>')
        text=(text[:idx]+tag+text[idx:]) if idx>=0 else (text+tag)
        html.write_text(text, encoding='utf-8')
        targets.append(html)
if not targets: raise SystemExit('HTML do Studio de Encartes nao localizado; publicacao cancelada')

report={
 'distribution_version':meta['distribution_version'],
 'product_version':meta['product_version'],
 'release_label':meta['release_label'],
 'editor_script':'files/Encartes4_beta6.js',
 'html_targets':[str(p.relative_to(root)).replace(os.sep,'/') for p in targets],
 'features':['canvas livre A4','drag-and-drop','redimensionamento','grid/snap','importacao XLSX/CSV','blocos inteligentes','preco APP','limite CPF','validacao','autosave','undo/redo','organizar automaticamente','impressao/PDF']
}
(files/'beta6_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
