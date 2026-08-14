from pathlib import Path
import json

R=Path('work/files')
js=(R/'Encartes9_beta15.js').read_text(encoding='utf-8')
html=(R/'Encartes3_index.html').read_text(encoding='utf-8')
engine=(R/'Encartes3Engine.py').read_text(encoding='utf-8')
version=json.loads((R/'version.json').read_text(encoding='utf-8'))

assert version['distribution_version']=='4.0.14-hybrid.beta15'
assert 'Encartes9_beta15.js' in html
assert "APP_DIR / 'Encartes9_beta15.js'" in engine
for token in [
    'partEdits','Editar partes','Aprender este modelo','copyPartToSimilar',
    'copyProductAdjustmentsToSimilar','fillCurrentPage','replaceSelectedProduct',
    'imageScale','focusX','focusY','part-handle','pro-guide',
    'exportProject','importProject','saveNamedVersion','restoreNamedVersion',
    'Original / preenchido','Resetar produto','Resetar página'
]:
    assert token in js, token
assert 'Encartes8_beta14.js' in html, 'Beta 14 visual deve continuar carregada antes da Beta 15'
print('Beta 15 validada: editor PRO + aprendizado + projetos')
