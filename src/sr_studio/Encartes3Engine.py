from __future__ import annotations

import functools
import os
import subprocess
import threading
import urllib.request
import webbrowser
import json, mimetypes, re, sqlite3
from difflib import SequenceMatcher
from urllib.parse import parse_qs, urlparse, quote
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import tkinter as tk
from SRStudio21 import PRODUCT_DB, norm
from ProductImages import get_image_info
from EncartesPPTX import parse_pptx, save_font, list_fonts, font_path, asset_path
from services.project_store import load_project, save_project, snapshot_project, list_projects

APP_DIR = Path(__file__).resolve().parent
EDITOR_HTML = APP_DIR / 'Encartes3_index.html'
REQUIRED_EDITOR_FILES = (
    APP_DIR / 'Encartes3_index.html',
    APP_DIR / 'Encartes7_beta13.js',
    APP_DIR / 'Encartes8_beta14.js',
    APP_DIR / 'Encartes9_beta15.js',
    APP_DIR / 'Encartes10_beta16.js',
    APP_DIR / 'Encartes11_v5.js',
    APP_DIR / 'EncartesPPTX.py',
    APP_DIR / 'xlsx.full.min.js',
)
_SERVER = None
_SERVER_THREAD = None
_SERVER_LOCK = threading.Lock()


def _code_variants(value):
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
            'codigo_ciss':d.get('codigo_ciss') or '','canonical_name':d.get('commercial_name') or d.get('canonical_name') or name,
            'unidade':d.get('unidade') or '','categoria':d.get('categoria') or info.get('category') or '',
            'ean':d.get('ean') or '','image':image,'has_official_image':bool(image)}


def _resolve_products(items):
    if not PRODUCT_DB.is_file(): return [{'found':False,'error':'BANCO_INDISPONIVEL'} for _ in items]
    out=[]
    with sqlite3.connect(PRODUCT_DB) as con:
        con.row_factory=sqlite3.Row
        for item in items:
            try: out.append(_lookup_product(con,item if isinstance(item,dict) else {}))
            except Exception as exc: out.append({'found':False,'error':str(exc)})
    return out


def _v5_project_state(project):
    state=project.get('state') or {}
    enc=state.get('encartes_state')
    if isinstance(enc,dict): return enc
    return {
        'products':state.get('products') or [],'pages':state.get('pages') or [],'pageIndex':0,'selected':None,
        'grid':True,'snap':True,'zoom':.75,'categoryFilter':'TODAS','fonts':[],
        'projectName':project.get('name') or 'Projeto SR Studio','partEditMode':True,'proSelection':[],
        'cropKey':None,'proGroups':{}
    }


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args): return
    def _json(self,data,status=200):
        raw=json.dumps(data,ensure_ascii=False).encode('utf-8'); self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def _body(self,limit=120*1024*1024):
        size=int(self.headers.get('Content-Length') or 0)
        if size<0 or size>limit: raise ValueError('Arquivo/requisição muito grande.')
        return self.rfile.read(size) if size else b''
    def do_POST(self):
        parsed=urlparse(self.path); path=parsed.path; qs=parse_qs(parsed.query)
        try:
            if path=='/api/encartes/resolve-products':
                raw=self._body(5*1024*1024); data=json.loads(raw.decode('utf-8')) if raw else {};items=data.get('items',[]) if isinstance(data,dict) else [];items=items if isinstance(items,list) else []
                return self._json({'ok':True,'results':_resolve_products(items)})
            if path=='/api/encartes/import-pptx':
                raw=self._body(); name=(qs.get('name') or ['modelo.pptx'])[0]
                return self._json(parse_pptx(raw,name))
            if path=='/api/encartes/font-upload':
                raw=self._body(40*1024*1024); name=(qs.get('name') or ['fonte.ttf'])[0]
                return self._json({'ok':True,'font':save_font(name,raw)})
            if path=='/api/v5/project/save':
                project_id=(qs.get('id') or [''])[0].strip()
                if not project_id: return self._json({'ok':False,'error':'PROJECT_ID_AUSENTE'},400)
                raw=self._body(60*1024*1024); data=json.loads(raw.decode('utf-8')) if raw else {}
                state=data.get('state') if isinstance(data,dict) else None
                if not isinstance(state,dict): return self._json({'ok':False,'error':'STATE_INVALIDO'},400)
                autosave=str((qs.get('autosave') or ['0'])[0]).lower() in {'1','true','sim','yes'}
                project=load_project(project_id,prefer_autosave=False)
                project.setdefault('state',{})['encartes_state']=state
                project['state']['products']=state.get('products') or []
                project['state']['pages']=state.get('pages') or []
                project['name']=str(state.get('projectName') or project.get('name') or 'Projeto SR Studio')
                saved=save_project(project,autosave=autosave)
                if not autosave:
                    try: snapshot_project(project_id,'Salvamento manual',is_auto=False)
                    except Exception: pass
                return self._json({'ok':True,'project_id':project_id,'autosave':autosave,'revision':saved.get('revision',0),'saved_at':saved.get('autosave_at') or saved.get('updated_at')})
            if path=='/api/v5/project/snapshot':
                project_id=(qs.get('id') or [''])[0].strip(); raw=self._body(1024*1024); data=json.loads(raw.decode('utf-8')) if raw else {}
                if not project_id:return self._json({'ok':False,'error':'PROJECT_ID_AUSENTE'},400)
                item=snapshot_project(project_id,str(data.get('label') or 'Versão manual'),is_auto=False)
                return self._json({'ok':True,'snapshot':item})
            return self._json({'ok':False,'error':'ROTA_NAO_ENCONTRADA'},404)
        except Exception as exc:
            return self._json({'ok':False,'error':str(exc)},500)
    def _serve_file(self,p,cache='no-store'):
        if not p or not Path(p).is_file(): self.send_error(404,'Arquivo não encontrado'); return
        p=Path(p);raw=p.read_bytes();self.send_response(200);self.send_header('Content-Type',mimetypes.guess_type(str(p))[0] or 'application/octet-stream');self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control',cache);self.end_headers();self.wfile.write(raw)
    def do_GET(self):
        parsed=urlparse(self.path);qs=parse_qs(parsed.query)
        if parsed.path=='/api/encartes/health': return self._json({'ok':True,'product_db':PRODUCT_DB.is_file(),'version':'5.0.0-next'})
        if parsed.path=='/api/v5/projects':
            try:
                items=[{'id':x.get('id'),'name':x.get('name'),'campaign':x.get('campaign'),'updated_at':x.get('updated_at')} for x in list_projects()]
                return self._json({'ok':True,'projects':items})
            except Exception as exc:return self._json({'ok':False,'error':str(exc)},500)
        if parsed.path=='/api/v5/project':
            project_id=(qs.get('id') or [''])[0].strip()
            if not project_id:return self._json({'ok':False,'error':'PROJECT_ID_AUSENTE'},400)
            try:
                prefer=str((qs.get('autosave') or ['0'])[0]).lower() in {'1','true','sim','yes'}
                project=load_project(project_id,prefer_autosave=prefer)
                return self._json({'ok':True,'project_id':project_id,'project':project,'state':_v5_project_state(project)})
            except Exception as exc:return self._json({'ok':False,'error':str(exc)},404)
        if parsed.path=='/api/encartes/fonts': return self._json({'ok':True,'fonts':list_fonts()})
        if parsed.path=='/api/encartes/font-file': return self._serve_file(font_path((qs.get('name') or [''])[0]),'public, max-age=3600')
        if parsed.path=='/api/encartes/pptx-asset': return self._serve_file(asset_path((qs.get('session') or [''])[0],(qs.get('name') or [''])[0]))
        if parsed.path=='/api/encartes/product-image':
            identity=(qs.get('identity') or [''])[0]; info=get_image_info(identity) or {}; path=Path(str(info.get('official_path') or ''))
            return self._serve_file(path if path.is_file() else None)
        return super().do_GET()


def _missing_editor_files():
    return [p.name for p in REQUIRED_EDITOR_FILES if not p.is_file()]


def _ensure_local_server():
    global _SERVER, _SERVER_THREAD
    with _SERVER_LOCK:
        if _SERVER is not None and _SERVER_THREAD is not None and _SERVER_THREAD.is_alive(): return int(_SERVER.server_address[1])
        missing=_missing_editor_files()
        if missing: raise RuntimeError('Arquivos do editor ausentes: '+', '.join(missing))
        handler=functools.partial(_QuietHandler,directory=str(APP_DIR));server=ThreadingHTTPServer(('127.0.0.1',0),handler);server.daemon_threads=True
        thread=threading.Thread(target=server.serve_forever,name='SRStudioEncartesHTTP',daemon=True);thread.start();_SERVER=server;_SERVER_THREAD=thread;return int(server.server_address[1])


def local_editor_url(): return f'http://127.0.0.1:{_ensure_local_server()}/Encartes3_index.html'
def cloud_url(): return local_editor_url()
def preload_encarte3_data(force=False): return 0


def _open_app(url: str):
    candidates=[os.path.expandvars(r'%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe'),os.path.expandvars(r'%ProgramFiles%\Microsoft\Edge\Application\msedge.exe'),os.path.expandvars(r'%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe')]
    for exe in candidates:
        if exe and os.path.exists(exe):
            try: subprocess.Popen([exe,f'--app={url}','--start-maximized']);return True
            except Exception: pass
    return bool(webbrowser.open(url))

_AUTO_OPENED=False
class Encartes3Panel(tk.Frame):
    def __init__(self,parent,app=None,pal=None):
        self.app=app;self.pal=pal or {};bg=self.pal.get('APP_BG',self.pal.get('BG','#0E141D'));fg=self.pal.get('TEXT','#F3F6FA');muted=self.pal.get('MUTED','#9EABBC');blue=self.pal.get('BLUE2','#82B0FF')
        super().__init__(parent,bg=bg);self.status=tk.StringVar(value='Abrindo o Encartes Studio 5.0...');self.url=''
        body=tk.Frame(self,bg=bg);body.pack(fill='both',expand=True,padx=30,pady=30)
        tk.Label(body,text='ENCARTES STUDIO',bg=bg,fg=fg,font=('Segoe UI',20,'bold')).pack(pady=(80,8))
        tk.Label(body,text='SR STUDIO 5.0 • EDITOR VISUAL + PROJETOS + AUTOSAVE',bg=bg,fg=blue,font=('Segoe UI',10,'bold')).pack()
        tk.Label(body,textvariable=self.status,bg=bg,fg=muted,font=('Segoe UI',10)).pack(pady=18)
        tk.Button(body,text='ABRIR EDITOR',command=self.open_editor,bg=self.pal.get('BLUE','#1769aa'),fg='white',bd=0,padx=28,pady=12,font=('Segoe UI',10,'bold')).pack()
        self.after(180,self._auto_open)
    def check(self):
        missing=_missing_editor_files()
        if missing:self.status.set('● ERRO — arquivos ausentes: '+', '.join(missing));return False
        try:
            self.url=local_editor_url();urllib.request.urlopen(self.url,timeout=2).close();self.status.set('● PRONTO — editor local 5.0 disponível');return True
        except Exception as exc:self.status.set('● ERRO — '+str(exc));return False
    def _auto_open(self):
        global _AUTO_OPENED
        if not _AUTO_OPENED and self.check():_AUTO_OPENED=True;self.open_editor()
    def open_editor(self):
        if not self.check():return
        try:_open_app(self.url);self.status.set('● ABERTO — editor iniciado')
        except Exception as exc:self.status.set('● ERRO AO ABRIR — '+str(exc))
