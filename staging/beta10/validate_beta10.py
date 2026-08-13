from pathlib import Path
import importlib.util, json, re, sqlite3, sys, tempfile, types, unicodedata

root=Path(sys.argv[1])/'files'
engine=root/'Encartes3Engine.py'
editor=root/'Encartes4_beta6.js'
text=engine.read_text(encoding='utf-8')
js=editor.read_text(encoding='utf-8')
assert '/api/encartes/resolve-products' in text
assert 'codigo_ciss' in text and 'canonical_norm' in text
assert "APP_DIR / 'xlsx.full.min.js'" in text
assert 'worksheetRows' in js and 'resolveFromProductBank' in js
assert "BANCO OK" in js and "NÃO LOCALIZADO" in js

sr=types.ModuleType('SRStudio21')
tmp=Path(tempfile.mkdtemp())/'product_history.db'
sr.PRODUCT_DB=tmp
def norm(v):
    s=unicodedata.normalize('NFD',str(v or ''))
    s=''.join(c for c in s if unicodedata.category(c)!='Mn')
    return re.sub(r'[^A-Z0-9]+',' ',s.upper()).strip()
sr.norm=norm
sys.modules['SRStudio21']=sr
pi=types.ModuleType('ProductImages'); pi.get_image_info=lambda identity:{}; sys.modules['ProductImages']=pi
try:
    import tkinter  # noqa
except Exception:
    tk=types.ModuleType('tkinter'); tk.Frame=object; tk.StringVar=object; sys.modules['tkinter']=tk

con=sqlite3.connect(tmp)
con.execute('''CREATE TABLE catalog_products(id INTEGER PRIMARY KEY,identity_key TEXT,codigo TEXT,canonical_name TEXT,canonical_norm TEXT,unidade TEXT,categoria TEXT,codigo_ciss TEXT,active INTEGER)''')
con.execute("INSERT INTO catalog_products VALUES(1,'K1','7891111111111','ARROZ TESTE 5KG','ARROZ TESTE 5KG','UN','MERCEARIA','1234',1)")
con.commit(); con.close()
spec=importlib.util.spec_from_file_location('enc_beta10',engine); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
rows=mod._resolve_products([{'code':'7891111111111'},{'code':'1234'},{'name':'ARROZ TESTE 5KG'},{'name':'ARROZ TESTE 5K'},{'code':'999'}])
assert [x['found'] for x in rows]==[True,True,True,True,False], rows
assert rows[0]['canonical_name']=='ARROZ TESTE 5KG'
print(json.dumps({'beta10':'ok','matches':[x.get('match_method') for x in rows]},ensure_ascii=False))
