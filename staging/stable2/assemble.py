from pathlib import Path
import json, shutil

R=Path('work/files')
S=Path('staging/stable2/source')
shutil.copy2(S/'SRSpellCheck.py',R/'SRSpellCheck.py')

def replace(path,old,new,label):
    p=R/path
    text=p.read_text(encoding='utf-8')
    if old not in text:
        raise SystemExit(f'Patch não encontrado: {label} em {path}')
    text=text.replace(old,new,1)
    p.write_text(text,encoding='utf-8')

# SRStudio21: correções aprendidas têm prioridade; na ausência delas entra o corretor local.
p=R/'SRStudio21.py';text=p.read_text(encoding='utf-8')
anchor='from tkinter import ttk, messagebox\n'
if 'from SRSpellCheck import correct_product_name as _auto_correct_product_name' not in text:
    text=text.replace(anchor,anchor+'from SRSpellCheck import correct_product_name as _auto_correct_product_name\n',1)
old='''def apply_learned_correction(name):\n    raw=normalize_product_name(name)\n    rules=corrections()\n    return rules.get(norm(raw),raw)\n'''
new='''def apply_learned_correction(name):\n    raw=normalize_product_name(name)\n    rules=corrections()\n    learned=rules.get(norm(raw))\n    if learned:\n        return normalize_product_name(learned)\n    return _auto_correct_product_name(raw)\n'''
if old not in text: raise SystemExit('Função apply_learned_correction não localizada')
text=text.replace(old,new,1);p.write_text(text,encoding='utf-8')

# Geração por planilha/campanha: corrige também o título do cartaz.
p=R/'SR_Studio_Gerador.py';text=p.read_text(encoding='utf-8')
if 'from SRSpellCheck import correct_campaign_text' not in text:
    marker='from SRStudio21 import (\n'
    text=text.replace(marker,'from SRSpellCheck import correct_campaign_text\n'+marker,1)
old='''    if norm(s) == "BEBDAS":\n        s = "BEBIDAS"\n    return s.upper().rstrip("! ") + "!!"\n'''
new='''    if norm(s) == "BEBDAS":\n        s = "BEBIDAS"\n    s = correct_campaign_text(s)\n    return s.upper().rstrip("! ") + "!!"\n'''
if old not in text: raise SystemExit('clean_campaign_title não localizado')
text=text.replace(old,new,1);p.write_text(text,encoding='utf-8')

# Geração Manual: corrige antes da prévia/PDF/impressão.
p=R/'ManualModule.py';text=p.read_text(encoding='utf-8')
old='from SRStudio21 import dated_output_dir, smart_pdf_name, unique_path, record_reprint, record_product_jobs, PRODUCT_DB, norm\n'
new='from SRStudio21 import dated_output_dir, smart_pdf_name, unique_path, record_reprint, record_product_jobs, PRODUCT_DB, norm, apply_learned_correction\nfrom SRSpellCheck import correct_campaign_text\n'
if old not in text: raise SystemExit('Import ManualModule não localizado')
text=text.replace(old,new,1)
old='''    def promo_job(self):\n        k=self.kind.get(); product=self.product.get().strip()\n'''
new='''    def promo_job(self):\n        k=self.kind.get(); product=apply_learned_correction(self.product.get().strip())\n        if product and product != self.product.get().strip(): self.product.set(product)\n'''
if old not in text: raise SystemExit('promo_job não localizado')
text=text.replace(old,new,1)
old='headline=self.headline.get().strip().upper() if tipo in {1,2} else "CLUBE SR"\n'
new='headline=correct_campaign_text(self.headline.get()) if tipo in {1,2} else "CLUBE SR"\n'
if old not in text: raise SystemExit('headline manual não localizado')
text=text.replace(old,new,1)
old='p["nome"]=str(p.get("nome") or "").strip().upper()\n'
new='p["nome"]=apply_learned_correction(str(p.get("nome") or "").strip())\n'
if old not in text: raise SystemExit('nome atacado manual não localizado')
text=text.replace(old,new,1);p.write_text(text,encoding='utf-8')

# Atacado automático: aplica a mesma ortografia ao nome final do cartaz.
p=R/'AtacadoModule.py';text=p.read_text(encoding='utf-8')
old='from SRStudio21 import dated_output_dir, smart_pdf_name, unique_path, record_product_jobs, record_reprint, pdf_with_copies\n'
new='from SRStudio21 import dated_output_dir, smart_pdf_name, unique_path, record_product_jobs, record_reprint, pdf_with_copies, apply_learned_correction\n'
if old not in text: raise SystemExit('Import AtacadoModule não localizado')
text=text.replace(old,new,1)
old='            name=" ".join(name.split())\n'
new='            name=apply_learned_correction(" ".join(name.split()))\n'
if old not in text: raise SystemExit('nome agrupado Atacado não localizado')
text=text.replace(old,new,1)
old='                "cartaz_chave":"P:"+it["codigo"],"nome":it["descricao"],\n'
new='                "cartaz_chave":"P:"+it["codigo"],"nome":apply_learned_correction(it["descricao"]),\n'
if old not in text: raise SystemExit('nome individual Atacado não localizado')
text=text.replace(old,new,1);p.write_text(text,encoding='utf-8')

# Versão Stable 2.
vpath=R/'version.json';v=json.loads(vpath.read_text(encoding='utf-8'))
v.update(distribution_version='4.0.16-hybrid.stable2',product_version='4.0.16',channel='stable',release_label='Stable 2',updated_at='2026-08-14T10:37:00-03:00')
vpath.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(R/'VERSAO.txt').write_text('SR Studio 4.0.16 • Stable 2\nPromove todas as funções até a Beta 16 e adiciona corretor ortográfico local para nomes de produtos e enunciados antes da geração de cartazes.\n',encoding='utf-8')
print('Stable 2 montada com corretor ortográfico')
