from pathlib import Path
p=Path(__import__('sys').argv[1])/'files'/'Encartes3Engine.py'
s=p.read_text(encoding='utf-8')
s=s.replace('import webbrowser\n','import webbrowser\nimport json, mimetypes, re, sqlite3\nfrom difflib import SequenceMatcher\nfrom urllib.parse import parse_qs, urlparse, quote\n',1)
s=s.replace('import tkinter as tk\n','import tkinter as tk\nfrom SRStudio21 import PRODUCT_DB, norm\nfrom ProductImages import get_image_info\n',1)
s=s.replace("    APP_DIR / 'Encartes4_beta6.js',\n", "    APP_DIR / 'Encartes4_beta6.js',\n    APP_DIR / 'xlsx.full.min.js',\n",1)
old="""class _QuietHandler(SimpleHTTPRequestHandler):\n    def log_message(self, format, *args):\n        return\n"""
new=r'''def _code_variants(value):
    raw=str(value or '').strip(); out=[]
    for x in (raw, raw[:-2] if raw.endswith('.0') else '', re.sub(r'\D+','',raw)):
        if x and x not in out: out.append(x)
    return out


def _lookup_product(con,item):
    code=str(item.get('code') or '').strip(); name=str(item.get('name') or '').strip(); row=None; method=''
    for c in _code_variants(code):
        row=con.execute("SELECT * FROM catalog_products WHERE active=1 AND (codigo=? OR codigo_ciss=?) LIMIT 1",(c,c)).fetchone()
        if row: method='CODIGO'; break
    target=norm(name)
    if not row and target:
        row=con.execute("SELECT * FROM catalog_products WHERE active=1 AND canonical_norm=? LIMIT 1",(target,)).fetchone()
        if row: method='NOME_EXATO'
    if not row and target:
        toks=[t for t in target.split() if len(t)>=3][:2]; params=['%'+t+'%' for t in toks] or ['%'+target[:8]+'%']
        where=' OR '.join('canonical_norm LIKE ?' for _ in params)
        cand=con.execute(f"SELECT * FROM catalog_products WHERE active=1 AND ({where}) LIMIT 180",params).fetchall()
        best=None; score=0.0
        for r in cand:
            v=SequenceMatcher(None,target,str(r['canonical_norm'] or '')).ratio()
            if v>score: best,score=r,v
        if best is not None and score>=0.72: row=best; method='NOME_APROXIMADO'
    if not row: return {'found':False,'input_code':code,'input_name':name}
    d=dict(row); identity=str(d.get('identity_key') or ''); info=get_image_info(identity) or {}
    path=Path(str(info.get('official_path') or '')); image=''
    if path.is_file(): image='/api/encartes/product-image?identity='+quote(identity,safe='')
    elif info.get('official_url'): image=str(info.get('official_url'))
    return {'found':True,'match_method':method,'identity_key':identity,'codigo':d.get('codigo') or '',
            'codigo_ciss':d.get('codigo_ciss') or '','canonical_name':d.get('canonical_name') or name,
            'unidade':d.get('unidade') or '','categoria':d.get('categoria') or info.get('category') or '',
            'image':image,'has_official_image':bool(image)}


def _resolve_products(items):
    if not PRODUCT_DB.is_file(): return [{'found':False,'error':'BANCO_INDISPONIVEL'} for _ in items]
    out=[]
    with sqlite3.connect(PRODUCT_DB) as con:
        con.row_factory=sqlite3.Row
        for item in items:
            try: out.append(_lookup_product(con,item if isinstance(item,dict) else {}))
            except Exception as exc: out.append({'found':False,'error':str(exc)})
    return out


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args): return
    def _json(self,data,status=200):
        raw=json.dumps(data,ensure_ascii=False).encode('utf-8'); self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def do_POST(self):
        if urlparse(self.path).path!='/api/encartes/resolve-products': return self._json({'ok':False,'error':'ROTA_NAO_ENCONTRADA'},404)
        try:
            size=min(int(self.headers.get('Content-Length') or 0),5*1024*1024); data=json.loads(self.rfile.read(size).decode('utf-8')) if size else {}
            items=data.get('items',[]) if isinstance(data,dict) else []; items=items if isinstance(items,list) else []
            return self._json({'ok':True,'results':_resolve_products(items)})
        except Exception as exc: return self._json({'ok':False,'error':str(exc)},500)
    def do_GET(self):
        parsed=urlparse(self.path)
        if parsed.path=='/api/encartes/health': return self._json({'ok':True,'product_db':PRODUCT_DB.is_file()})
        if parsed.path=='/api/encartes/product-image':
            identity=(parse_qs(parsed.query).get('identity') or [''])[0]; info=get_image_info(identity) or {}; path=Path(str(info.get('official_path') or ''))
            if not path.is_file(): self.send_error(404,'Imagem oficial não encontrada'); return
            raw=path.read_bytes(); self.send_response(200); self.send_header('Content-Type',mimetypes.guess_type(str(path))[0] or 'application/octet-stream'); self.send_header('Content-Length',str(len(raw))); self.send_header('Cache-Control','no-store'); self.end_headers(); self.wfile.write(raw); return
        return super().do_GET()
'''
if old not in s: raise SystemExit('handler base não encontrado')
s=s.replace(old,new,1)
p.write_text(s,encoding='utf-8')
