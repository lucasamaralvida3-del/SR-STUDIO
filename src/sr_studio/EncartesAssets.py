from __future__ import annotations
import re, uuid
from pathlib import Path
from urllib.parse import quote
from SRStudio21 import PRODUCT_DB

LOCAL_DATA=PRODUCT_DB.parent
PPTX_ASSET_ROOT=LOCAL_DATA/'encartes_pptx_assets'
FONT_ROOT=LOCAL_DATA/'encartes_fonts'
PPTX_ASSET_ROOT.mkdir(parents=True,exist_ok=True)
FONT_ROOT.mkdir(parents=True,exist_ok=True)

def safe_name(name,default='arquivo'):
    name=Path(str(name or default)).name
    return (re.sub(r'[^A-Za-z0-9._ -]+','_',name).strip(' ._') or default)[:120]

def save_font(name,data):
    name=safe_name(name,'fonte.ttf'); ext=Path(name).suffix.lower()
    if ext not in {'.ttf','.otf','.woff','.woff2'}: raise ValueError('Formato de fonte não suportado. Use TTF, OTF, WOFF ou WOFF2.')
    if not data or len(data)>40*1024*1024: raise ValueError('Arquivo de fonte vazio ou muito grande.')
    target=FONT_ROOT/name
    if target.exists() and target.read_bytes()!=data: target=FONT_ROOT/f'{target.stem}_{uuid.uuid4().hex[:6]}{ext}'
    target.write_bytes(data); family=re.sub(r'[-_]+',' ',target.stem).strip()
    return {'name':target.name,'family':family,'url':'/api/encartes/font-file?name='+quote(target.name)}

def list_fonts():
    return [{'name':p.name,'family':re.sub(r'[-_]+',' ',p.stem).strip(),'url':'/api/encartes/font-file?name='+quote(p.name)} for p in sorted(FONT_ROOT.iterdir() if FONT_ROOT.exists() else []) if p.is_file() and p.suffix.lower() in {'.ttf','.otf','.woff','.woff2'}]

def font_path(name):
    p=(FONT_ROOT/Path(str(name or '')).name).resolve()
    return p if FONT_ROOT.resolve() in p.parents and p.is_file() else None

def session_dir(session):
    base=(PPTX_ASSET_ROOT/re.sub(r'[^a-f0-9]','',str(session or '').lower())[:32]).resolve(); base.mkdir(parents=True,exist_ok=True); return base

def asset_path(session,name):
    base=session_dir(session);p=(base/Path(str(name or '')).name).resolve()
    return p if base in p.parents and p.is_file() else None
