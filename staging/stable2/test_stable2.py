from pathlib import Path
import importlib.util, json, sys

files=Path('work/files')
spec=importlib.util.spec_from_file_location('SRSpellCheck',files/'SRSpellCheck.py')
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)

cases={
    'ACUCAR DELTA 5KG':'AÇÚCAR DELTA 5KG',
    'CAFE VASCONCELOS 500G':'CAFÉ VASCONCELOS 500G',
    'LINGUICA CALABRESA 1KG':'LINGUIÇA CALABRESA 1KG',
    'FILE DE TILAPIA 500G':'FILÉ DE TILÁPIA 500G',
    'PAPEL HIGIENICO FOLHA DUPLA':'PAPEL HIGIÊNICO FOLHA DUPLA',
    'ACHOCOLATADO EM PO TODDY 370G':'ACHOCOLATADO EM PÓ TODDY 370G',
    'MUSCULO SUINO':'MÚSCULO SUÍNO',
    'ABOBRINNHA':'ABOBRINHA',
    'HAMBURGEUR SR 145G':'HAMBÚRGUER SR 145G',
    'TODDY 750G':'TODDY 750G',
}
for src,want in cases.items():
    got=mod.correct_product_name(src)
    assert got==want,(src,got,want)
assert mod.correct_campaign_text('TERCA VERDE')=='TERÇA VERDE'
assert mod.correct_campaign_text('QUARTA CAFE COM PAO')=='QUARTA CAFÉ COM PÃO'
assert mod.correct_campaign_text('QUINTA FILE')=='QUINTA FILÉ'

sr=(files/'SRStudio21.py').read_text(encoding='utf-8')
manual=(files/'ManualModule.py').read_text(encoding='utf-8')
main=(files/'SR_Studio_Gerador.py').read_text(encoding='utf-8')
atacado=(files/'AtacadoModule.py').read_text(encoding='utf-8')
assert '_auto_correct_product_name(raw)' in sr
assert 'learned=rules.get(norm(raw))' in sr
assert 'product=apply_learned_correction' in manual
assert 'correct_campaign_text(self.headline.get())' in manual
assert 's = correct_campaign_text(s)' in main
assert '"nome":apply_learned_correction(it["descricao"])' in atacado
assert (files/'Encartes10_beta16.js').is_file(), 'Editor Beta 16 ausente'
assert 'Encartes10_beta16.js' in (files/'Encartes3_index.html').read_text(encoding='utf-8')
v=json.loads((files/'version.json').read_text(encoding='utf-8'))
assert v['distribution_version']=='4.0.16-hybrid.stable2'
assert v['channel']=='stable'
print('Stable 2 validada: corretor + Beta 16 preservados')
