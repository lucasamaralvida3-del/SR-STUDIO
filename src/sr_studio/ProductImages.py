# -*- coding: utf-8 -*-
"""Banco de imagens do SR Studio.

SR Studio 4.0.4 Beta 5
- Banco de imagens mantido manualmente pelo usuário.
- Nenhuma pesquisa automática de imagens é executada.
- Nenhuma chamada OpenAI é feita para localizar/selecionar imagens.
- A imagem escolhida é copiada para o banco oficial do SR Studio.
"""
import os, re, json, shutil, sqlite3, threading, subprocess, sys, math, html as html_lib, webbrowser
from pathlib import Path
from datetime import datetime
from urllib.parse import quote_plus, urlparse, unquote, parse_qs
from urllib.request import Request, urlopen
import tkinter as tk
from tkinter import messagebox, filedialog

from SRStudio21 import LOCAL_DATA, PRODUCT_DB

try:
    from PIL import Image
except Exception:
    Image = None

IMAGE_ROOT = LOCAL_DATA / 'product_images'
OFFICIAL_DIR = IMAGE_ROOT / 'official'
CACHE_DIR = IMAGE_ROOT / 'cache'
META_FILE = IMAGE_ROOT / 'cache_meta.json'
PREF_FILE = IMAGE_ROOT / 'image_preferences.json'
GOOGLE_CFG_FILE = IMAGE_ROOT / 'google_images.json'
OCR_SCRIPT = Path(__file__).with_name('ProductImageOCR.ps1')
for _p in (IMAGE_ROOT, OFFICIAL_DIR, CACHE_DIR):
    _p.mkdir(parents=True, exist_ok=True)

# Palavras que descrevem o tipo do produto, mas normalmente não são a marca.
_PRODUCT_GENERIC = set("""
DE DA DO DAS DOS E EM COM SEM PARA POR A O AS OS AO AOS
PRODUTO EMBALAGEM PACOTE PCT PT UN UND CX CAIXA LATA GARRAFA PET SACHE SACHET PO
TIPO TP TRAD TRADICIONAL ORIGINAL ORIG INTEGRAL INTEGR SEMIDESN DESNATADO LIGHT ZERO
ARROZ FEIJAO FEIJÃO ACUCAR AÇUCAR CAFE CAFÉ LEITE FARINHA FLOCAO FLOCÃO MILHO
BISCOITO BOLACHA MACARRAO MACARRÃO MOLHO EXTRATO CREME CHOCOLATE ACHOCOLATADO
REFRIGERANTE CERVEJA ENERGETICO ENERGÉTICO SUCO AGUA ÁGUA BEBIDA IOGURTE MARGARINA
DETERGENTE AMACIANTE DESINFETANTE SABAO SABÃO LIMPADOR SANITARIA SANITÁRIA ESPONJA
CARNE BOVINO BOVINA SUINO SUÍNO SUINA SUÍNA FRANGO COXA SOBRECOXA COSTELA ACEM ACÉM
PICANHA LINGUICA LINGUIÇA PERNIL FILE FILÉ PEITO BANANA MACA MAÇÃ LARANJA LIMAO LIMÃO
BATATA CEBOLA CENOURA TOMATE MANGA MELANCIA MAMAO MAMÃO UVA PERA ABACAXI REPOLHO
PAO PÃO BOLO QUEIJO PRESUNTO MUSSARELA
""".split())
_BAD_RESULT_WORDS = set("""
RECEITA RECEITAS PRATO PRATOS PREPARO MODO COZIDO COZIDA REFEICAO REFEIÇÃO CARDAPIO CARDÁPIO
BANNER ENCARTES ENCARTE PANFLETO FLYER PROMOCAO PROMOÇÃO OFERTA OFERTAS INSTAGRAM FACEBOOK
PINTEREST YOUTUBE TIKTOK MOCKUP LOGOTIPO LOGO PAPEL PAREDE WALLPAPER
""".split())


def _conn():
    con = sqlite3.connect(PRODUCT_DB)
    con.row_factory = sqlite3.Row
    return con


def _now():
    return datetime.now().isoformat(timespec='seconds')


def _safe_stem(value):
    value = str(value or '').strip()
    value = re.sub(r'[^A-Za-z0-9._-]+', '_', value)
    value = re.sub(r'_+', '_', value).strip('._ ')
    return value or 'img'


def _norm_text(value):
    import unicodedata
    s = unicodedata.normalize('NFKD', str(value or ''))
    s = ''.join(ch for ch in s if not unicodedata.combining(ch)).upper()
    return re.sub(r'[^A-Z0-9]+', ' ', s).strip()


def _clean_query_name(value):
    s = str(value or '').strip()
    replacements = {
        r'\bS/\b': ' SEM ', r'\bC/\b': ' COM ', r'\bINTEGR\b': ' INTEGRAL ',
        r'\bTRAD\b': ' TRADICIONAL ', r'\bORIG\b': ' ORIGINAL ', r'\bUND\b': ' UN '
    }
    for pat, repl in replacements.items():
        s = re.sub(pat, repl, s, flags=re.I)
    return re.sub(r'\s+', ' ', s).strip(' -')


def _extract_measures(text):
    """Retorna medidas normalizadas. Massa em g, volume em ml, unidade como contagem."""
    n = _norm_text(text)
    out=[]
    for m in re.finditer(r'(?<!\d)(\d+(?:[.,]\d+)?)\s*(KG|G|GR|ML|L|LT)(?![A-Z])', n):
        try: value=float(m.group(1).replace(',','.'))
        except Exception: continue
        unit=m.group(2)
        if unit=='KG': out.append(('MASS', round(value*1000,2)))
        elif unit in ('G','GR'): out.append(('MASS', round(value,2)))
        elif unit in ('L','LT'): out.append(('VOL', round(value*1000,2)))
        elif unit=='ML': out.append(('VOL', round(value,2)))
    for m in re.finditer(r'(?<!\d)(\d+)\s*(UN|UND)(?![A-Z])', n):
        try: out.append(('COUNT', float(m.group(1))))
        except Exception: pass
    return out


def _product_measure(name):
    vals=_extract_measures(name)
    if not vals: return ''
    kind,val=vals[0]
    if kind=='MASS':
        return f'{val/1000:g}KG' if val>=1000 and val%1000==0 else f'{val:g}G'
    if kind=='VOL':
        return f'{val/1000:g}L' if val>=1000 and val%1000==0 else f'{val:g}ML'
    return f'{val:g}UN'


def _product_profile(name, code=''):
    clean=_clean_query_name(name)
    norm=_norm_text(clean)
    tokens=[t for t in norm.split() if len(t)>=2]
    lexical=[t for t in tokens if not re.fullmatch(r'\d+(?:\d+)?',t) and not re.fullmatch(r'\d+(KG|G|ML|L|LT|UN|UND)',t)]
    meaningful=[t for t in lexical if t not in _PRODUCT_GENERIC]
    if not meaningful:
        meaningful=[t for t in lexical if len(t)>=4 and t not in {'PRODUTO','EMBALAGEM'}]
    brand=meaningful[:3]
    cat=guess_category(clean)
    code_digits=re.sub(r'\D+','',str(code or ''))
    return {'original':str(name or ''),'clean':clean,'norm':norm,'tokens':tokens,'meaningful':meaningful,'brand':brand,'category':cat,'measures':_extract_measures(clean),'code':code_digits}


def _load_preferences():
    try: return json.loads(PREF_FILE.read_text(encoding='utf-8-sig'))
    except Exception: return {'approvals': 0, 'categories': {}}


def _save_preferences(data):
    try: PREF_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception: pass


def _image_metrics(path):
    out={'width':0,'height':0,'border_light':0.0,'border_neutral':0.0,'coverage':0.5,'sharpness_proxy':0.0}
    if Image is None: return out
    try:
        with Image.open(path) as im:
            im=im.convert('RGB'); out['width'],out['height']=im.size; im.thumbnail((180,180))
            w,h=im.size; pix=im.load(); border=[]; step=max(1,min(w,h)//40)
            for x in range(0,w,step): border.extend((pix[x,0],pix[x,h-1]))
            for y in range(0,h,step): border.extend((pix[0,y],pix[w-1,y]))
            if border:
                light=neutral=0
                for r,g,b in border:
                    avg=(r+g+b)/3
                    if min(r,g,b)>=205: light+=1
                    if avg>=175 and max(r,g,b)-min(r,g,b)<=28: neutral+=1
                out['border_light']=light/len(border); out['border_neutral']=neutral/len(border)
            total=fg=0; vals=[]; sy=max(1,h//80); sx=max(1,w//80)
            for y in range(0,h,sy):
                for x in range(0,w,sx):
                    r,g,b=pix[x,y]; total+=1; avg=(r+g+b)/3; vals.append(avg)
                    if not (min(r,g,b)>=225 or (avg>=205 and max(r,g,b)-min(r,g,b)<=20)): fg+=1
            out['coverage']=fg/max(1,total)
            if vals:
                mean=sum(vals)/len(vals); out['sharpness_proxy']=min(1.0,math.sqrt(sum((v-mean)**2 for v in vals)/len(vals))/80.0)
    except Exception: pass
    return out


def _visual_score(path, url='', product_name='', category=''):
    m=_image_metrics(path); w,h=m['width'],m['height']; score=50.0; reasons=[]
    if w and h:
        mn=min(w,h); mx=max(w,h); ratio=mx/max(1,mn)
        if mn>=900: score+=14; reasons.append('alta resolução')
        elif mn>=600: score+=11
        elif mn>=400: score+=7
        elif mn<220: score-=14; reasons.append('baixa resolução')
        if ratio<=1.8: score+=6
        elif ratio>2.8: score-=14; reasons.append('formato de banner')
    light=m.get('border_light',0); neutral=m.get('border_neutral',0)
    if category not in ('HORTIFRUTI','AÇOUGUE'):
        if light>=.68 or neutral>=.75: score+=18; reasons.append('fundo claro/neutro')
        elif light>=.35 or neutral>=.45: score+=9
        else: score-=8
    cov=m.get('coverage',.5)
    if .20<=cov<=.82: score+=9; reasons.append('produto bem enquadrado')
    elif cov<.08: score-=13; reasons.append('produto muito pequeno')
    elif cov>.95: score-=7
    lower=(url or '').lower()
    for t in ('produto','product','packshot','embalagem','package','pacote','pack','catalog','catalogo','supermerc','loja','shop','ecommerce'):
        if t in lower: score+=2
    for t in ('receita','recipe','prato','dish','bowl','cozido','meal','pinterest','youtube','facebook','instagram','banner','flyer'):
        if t in lower: score-=7
    try:
        pref=(_load_preferences().get('categories') or {}).get(category or 'GERAL') or {}
        if int(pref.get('approvals') or 0)>=3:
            target_b=float(pref.get('avg_border_light') or 0); target_c=float(pref.get('avg_coverage') or .5)
            score += max(-4, 5-abs(light-target_b)*12); score += max(-3, 4-abs(cov-target_c)*10)
    except Exception: pass
    return max(0,min(100,round(score,1))),m,reasons


def _same_measure(a,b,tolerance=.03):
    if a[0]!=b[0]: return False
    av,bv=float(a[1]),float(b[1]); return abs(av-bv)<=max(1.0,abs(av)*tolerance)


def _name_relevance(profile, title='', context='', url='', page_url='', ean_exact=False):
    """Compara o resultado do Google com o cadastro do produto antes de aceitar a imagem."""
    raw=' '.join(str(x or '') for x in (title,context,url,page_url)); norm=_norm_text(raw); toks=set(norm.split()); score=10.0; reasons=[]
    if not norm: return (95.0 if ean_exact else 20.0), ['EAN exato'] if ean_exact else []
    if ean_exact and profile.get('code'): score+=55; reasons.append('EAN exato')
    meaningful=profile.get('meaningful') or []; brands=profile.get('brand') or []
    all_prod=[t for t in profile.get('tokens') or [] if len(t)>=3 and t not in _PRODUCT_GENERIC]
    if meaningful:
        hits=sum(1 for t in meaningful if t in toks); ratio=hits/max(1,len(meaningful)); score+=ratio*35
        if hits: reasons.append(f'{hits}/{len(meaningful)} termo(s) principal(is)')
    if brands:
        bhits=sum(1 for t in brands if t in toks); score+=(bhits/max(1,len(brands)))*24
        if bhits: reasons.append('marca/nome compatível')
        elif len(brands)>=1: score-=18
    if all_prod: score+=(sum(1 for t in all_prod if t in toks)/max(1,len(all_prod)))*12
    cat_terms={t for t in profile.get('tokens') or [] if t in _PRODUCT_GENERIC and len(t)>=4}
    if cat_terms and any(t in toks for t in cat_terms): score+=10; reasons.append('tipo do produto compatível')
    target_measures=profile.get('measures') or []; cand_measures=_extract_measures(raw)
    if target_measures and cand_measures:
        ok=any(_same_measure(a,b) for a in target_measures for b in cand_measures)
        if ok: score+=20; reasons.append('peso/volume confere')
        elif any(a[0]==b[0] for a in target_measures for b in cand_measures): score-=38; reasons.append('peso/volume divergente')
    elif target_measures and not cand_measures: score-=3
    bad=sum(1 for t in _BAD_RESULT_WORDS if t in toks)
    if bad: score-=min(36,bad*12); reasons.append('contexto não comercial')
    low=raw.lower()
    if any(x in low for x in ('supermerc','atacad','mercado','ecommerce','produto','catalog','loja','shop')): score+=8
    if any(x in low for x in ('receita','prato pronto','cardapio','cardápio','pinterest','youtube')): score-=22
    return max(0,min(100,round(score,1))),reasons



def _ocr_visible_text(path, timeout=7):
    """OCR opcional da própria embalagem usando Windows.Media.Ocr.

    Falhas/idioma não instalado nunca bloqueiam a busca.
    """
    if os.name != 'nt' or not OCR_SCRIPT.exists():
        return ''
    try:
        proc=subprocess.run([
            'powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(OCR_SCRIPT),
            '-InputPath',str(Path(path).resolve())
        ],capture_output=True,text=True,encoding='utf-8',errors='ignore',timeout=timeout,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        return re.sub(r'\s+',' ',proc.stdout or '').strip()[:1800]
    except Exception:
        return ''


def _ocr_name_score(profile, ocr_text):
    """Compara palavras realmente visíveis na embalagem com o cadastro."""
    norm=_norm_text(ocr_text); toks=set(norm.split())
    if len(norm)<3 or not toks:
        return None, []
    score=35.0; reasons=[]
    brands=profile.get('brand') or []
    meaningful=profile.get('meaningful') or []
    if brands:
        hits=sum(1 for t in brands if t in toks)
        if hits:
            score += 35*(hits/max(1,len(brands))); reasons.append('marca lida na embalagem')
        elif len(toks)>=4:
            score -= 20; reasons.append('marca não confirmada pelo OCR')
    if meaningful:
        hits=sum(1 for t in meaningful if t in toks)
        score += 15*(hits/max(1,len(meaningful)))
    target=profile.get('measures') or []; seen=_extract_measures(ocr_text)
    if target and seen:
        if any(_same_measure(a,b) for a in target for b in seen):
            score += 20; reasons.append('peso/volume lido na embalagem')
        elif any(a[0]==b[0] for a in target for b in seen):
            score -= 30; reasons.append('peso/volume da embalagem diverge')
    cat_terms={t for t in profile.get('tokens') or [] if t in _PRODUCT_GENERIC and len(t)>=4}
    if cat_terms and any(t in toks for t in cat_terms):
        score += 10; reasons.append('tipo do produto lido na embalagem')
    return max(0,min(100,round(score,1))),reasons

def _dhash(path):
    if Image is None: return None
    try:
        with Image.open(path) as im:
            im=im.convert('L').resize((9,8)); px=list(im.getdata()); h=0
            for y in range(8):
                for x in range(8): h=(h<<1)|(1 if px[y*9+x]>px[y*9+x+1] else 0)
            return h
    except Exception: return None


def _hamming(a,b):
    if a is None or b is None: return 999
    try: return (a^b).bit_count()
    except Exception: return bin(a^b).count('1')


def _build_search_queries(name, code='', category=''):
    """Cria consultas que imitam uma busca manual no Google Imagens."""
    profile=_product_profile(name,code); clean=profile['clean']; code=profile['code']
    qs=[]
    if clean:
        # Principal: simples e direta, ex.: arroz vasconcelos 5kg
        qs.append((clean,'GOOGLE EXATO'))
        qs.append((f'"{clean}"','FRASE EXATA'))
        core=[]
        cat_tokens=[t for t in profile['tokens'] if t in _PRODUCT_GENERIC and len(t)>=4][:2]
        core.extend(cat_tokens); core.extend(profile['meaningful'][:4])
        measure=_product_measure(clean)
        if measure: core.append(measure)
        core_text=' '.join(dict.fromkeys(core)).strip()
        if core_text and _norm_text(core_text)!=_norm_text(clean):
            qs.append((core_text,'PRODUTO + MARCA + MEDIDA'))
    if code and len(code)>=8:
        qs.append((code,'EAN'))
    out=[]; seen=set()
    for q,t in qs:
        k=_norm_text(q)
        if k and k not in seen:
            seen.add(k); out.append((q,t))
    return out


def _measure_text(measures):
    if not measures: return ''
    kind,val=measures[0]
    if kind=='MASS':
        return f'{val/1000:g}KG' if val>=1000 and abs(val%1000)<.001 else f'{val:g}G'
    if kind=='VOL':
        return f'{val/1000:g}L' if val>=1000 and abs(val%1000)<.001 else f'{val:g}ML'
    return f'{val:g}UN'


def _strict_product_evidence(profile, title='', url='', page_url='', ocr_text=''):
    """Confirma produto/marca/medida sem usar o HTML global do Google."""
    meta_raw=' '.join(str(x or '') for x in (title,url,page_url))
    meta=_norm_text(meta_raw); meta_tokens=set(meta.split())
    ocr=_norm_text(ocr_text); ocr_tokens=set(ocr.split())
    evidence_tokens=meta_tokens | ocr_tokens
    brands=profile.get('brand') or []
    meaningful=profile.get('meaningful') or []
    product_tokens=[t for t in profile.get('tokens') or [] if t in _PRODUCT_GENERIC and len(t)>=4]
    target_measures=profile.get('measures') or []
    found_measures=_extract_measures(meta_raw+' '+ocr_text)

    brand_hits=sum(1 for t in brands if t in evidence_tokens)
    meaningful_hits=sum(1 for t in meaningful if t in evidence_tokens)
    type_hits=sum(1 for t in product_tokens if t in evidence_tokens)
    brand_ok=(not brands) or brand_hits>0
    type_ok=(not product_tokens) or type_hits>0

    measure_ok=True; measure_unknown=False; measure_conflict=False
    if target_measures:
        same=[1 for a in target_measures for b in found_measures if _same_measure(a,b)]
        comparable=[1 for a in target_measures for b in found_measures if a[0]==b[0]]
        if same:
            measure_ok=True
        elif comparable:
            measure_ok=False; measure_conflict=True
        else:
            measure_ok=False; measure_unknown=True

    branded_category=profile.get('category') not in ('HORTIFRUTI','AÇOUGUE')
    hard_ok=True; reasons=[]
    if branded_category and brands and not brand_ok:
        hard_ok=False; reasons.append('marca não confirmada')
    if product_tokens and not type_ok and meaningful_hits==0:
        hard_ok=False; reasons.append('tipo do produto não confirmado')
    if measure_conflict:
        hard_ok=False; reasons.append('peso/volume incompatível')

    strength=0.0
    if brands: strength += min(40,40*brand_hits/max(1,len(brands)))
    if meaningful: strength += min(25,25*meaningful_hits/max(1,len(meaningful)))
    if product_tokens: strength += min(15,15*type_hits/max(1,len(set(product_tokens))))
    if target_measures:
        if measure_ok: strength += 20
    else:
        strength += 10
    if ocr_text and ocr_tokens: strength += 5
    strength=max(0,min(100,round(strength,1)))
    return {'ok':hard_ok,'strength':strength,'brand_ok':brand_ok,'type_ok':type_ok,
            'measure_ok':measure_ok,'measure_unknown':measure_unknown,'measure_conflict':measure_conflict,
            'brand_hits':brand_hits,'type_hits':type_hits,'meaningful_hits':meaningful_hits,'reasons':reasons}


def _google_query_url(query):
    return 'https://www.google.com/search?tbm=isch&hl=pt-BR&gl=br&safe=active&q='+quote_plus(str(query or '').strip())

def ensure_schema():
    with _conn() as con:
        con.executescript("""CREATE TABLE IF NOT EXISTS catalog_images(identity_key TEXT PRIMARY KEY,codigo TEXT,canonical_name TEXT,category TEXT,official_path TEXT,official_url TEXT,source_name TEXT,confidence TEXT,updated_at TEXT NOT NULL);""")
        cols=[r[1] for r in con.execute('PRAGMA table_info(catalog_products)').fetchall()]
        if 'categoria' not in cols:
            try: con.execute('ALTER TABLE catalog_products ADD COLUMN categoria TEXT')
            except Exception: pass
ensure_schema()


def _load_meta():
    try: return json.loads(META_FILE.read_text(encoding='utf-8-sig'))
    except Exception: return {}


def _save_meta(data):
    try: META_FILE.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    except Exception: pass


def get_image_info(identity_key):
    with _conn() as con: row=con.execute('SELECT * FROM catalog_images WHERE identity_key=?',(str(identity_key),)).fetchone()
    return dict(row) if row else None


def get_category(identity_key):
    with _conn() as con: row=con.execute('SELECT categoria FROM catalog_products WHERE identity_key=?',(str(identity_key),)).fetchone()
    return row[0] if row and row[0] else ''


def set_category(identity_key,category):
    category=str(category or '').strip().upper()
    with _conn() as con:
        con.execute('UPDATE catalog_products SET categoria=? WHERE identity_key=?',(category,str(identity_key)))
        con.execute("INSERT INTO catalog_images(identity_key,category,updated_at) VALUES(?,?,?) ON CONFLICT(identity_key) DO UPDATE SET category=excluded.category,updated_at=excluded.updated_at",(str(identity_key),category,_now()))


def guess_category(name):
    n=str(name or '').upper()
    checks=[
        ('HORTIFRUTI',('BANANA','MAÇA','MACA','LARANJA','LIMAO','LIMÃO','BETERRABA','ALHO','BATATA','COCO','VAGEM','CHUCHU','BROCOLIS','BRÓCOLIS','PIMENTAO','PIMENTÃO','ABOBORA','ABÓBORA','ABACATE','PERA','REPOLHO','CENOURA','MELANCIA','TOMATE','MANGA','MAMÃO','MAMAO','UVA')),
        ('BEBIDAS',('REFRIGERANTE','ENERGETICO','ENERGÉTICO','SUCO','CERVEJA','AGUA','ÁGUA','BEBIDA','WHISKY','VINHO')),
        ('LIMPEZA',('DETERGENTE','AMACIANTE','AGUA SANITARIA','ÁGUA SANITÁRIA','DESINFETANTE','SABAO','SABÃO','LIMPADOR','ESPONJA')),
        ('AÇOUGUE',('ACEM','ACÉM','PICANHA','COSTELA','LINGUICA','LINGUIÇA','FRANGO','TILAPIA','CARNE','PERNIL','COXA','LOMBO','BACON')),
        ('MERCEARIA',('ARROZ','FEIJAO','FEIJÃO','AÇUCAR','ACUCAR','MACARRAO','MACARRÃO','BISCOITO','BOLACHA','CAFE','CAFÉ','LEITE','FARINHA','FLOCÃO','FLOCAO','ACHOCOLATADO')),
        ('PADARIA',('PAO','PÃO','BOLO','BROA','PUDIM','PÃO DE QUEIJO','PAO DE QUEIJO')),
    ]
    for cat,terms in checks:
        if any(t in n for t in terms): return cat
    return ''


def _request(url,timeout=10):
    req=Request(url,headers={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36','Accept-Language':'pt-BR,pt;q=0.9,en;q=0.7','Accept':'text/html,application/xhtml+xml,application/json,image/avif,image/webp,image/apng,image/*,*/*;q=0.8'})
    with urlopen(req,timeout=timeout) as r: return r.read()


def _download_to_cache(url,stem):
    stem=_safe_stem(stem); ext='.jpg'; low=url.lower()
    for e in ('.png','.jpg','.jpeg','.webp'):
        if e in low: ext='.jpg' if e=='.jpeg' else e; break
    target=CACHE_DIR/f'{stem}{ext}'; data=_request(url,timeout=14)
    if len(data)>8*1024*1024: raise RuntimeError('Imagem muito grande para o cache.')
    target.write_bytes(data)
    if Image is not None:
        try:
            with Image.open(target) as im: im.verify()
        except Exception:
            try: target.unlink()
            except Exception: pass
            raise RuntimeError('O endereço retornado não contém uma imagem válida.')
    return target


def _decode_js_url(value):
    s=html_lib.unescape(str(value or '')); s=s.replace('\\/','/').replace('\\u003d','=').replace('\\u0026','&').replace('\\u003f','?').replace('\\u0025','%')
    try:
        if '\\u' in s or '\\x' in s: s=bytes(s,'utf-8').decode('unicode_escape')
    except Exception: pass
    return s.strip()


def _clean_context(raw):
    s=_decode_js_url(raw); s=re.sub(r'<script.*?</script>',' ',s,flags=re.I|re.S); s=re.sub(r'<style.*?</style>',' ',s,flags=re.I|re.S); s=re.sub(r'<[^>]+>',' ',s)
    return re.sub(r'\s+',' ',html_lib.unescape(s.replace('\\n',' ').replace('\\"','"'))).strip()[:1800]


def _url_ok(url):
    if not url.startswith(('http://','https://')): return False
    low=url.lower()
    if any(x in low for x in ('google.com/images/branding','gstatic.com/images/branding','googleusercontent.com/proxy','favicon','logo_google','data:image','base64')): return False
    if any(x in low for x in ('.svg','.gif')): return False
    return True


def _google_direct_candidates(query,limit=60):
    """Busca URLs no Google Imagens sem contaminar o ranking com a própria consulta."""
    out=[]; seen=set()
    search_urls=[_google_query_url(query),
                 'https://www.google.com/search?udm=2&hl=pt-BR&gl=br&safe=active&q='+quote_plus(query)]

    def add(url,title='',page_url='',source='Google Imagens'):
        url=_decode_js_url(url); page_url=_decode_js_url(page_url); title=_clean_context(title)
        if not _url_ok(url) or url in seen: return
        seen.add(url)
        out.append({'url':url,'title':title[:500],'context':'','page_url':page_url,
                    'query':query,'source':source})

    for search_url in search_urls:
        try: doc=_request(search_url,timeout=12).decode('utf-8','ignore')
        except Exception: continue

        # Estrutura comum do Google Images: ou=original URL, pt=título, ru=página de origem.
        for m in re.finditer(r'"ou"\s*:\s*"([^"]+)"',doc,flags=re.I):
            chunk=doc[max(0,m.start()-1400):min(len(doc),m.end()+1800)]
            pt=re.search(r'"pt"\s*:\s*"([^"]*)"',chunk,flags=re.I)
            ru=re.search(r'"ru"\s*:\s*"([^"]*)"',chunk,flags=re.I)
            add(m.group(1),pt.group(1) if pt else '',ru.group(1) if ru else '')
            if len(out)>=limit: return out

        # Formato /imgres?imgurl=...&imgrefurl=...
        for m in re.finditer(r'(?:https?://www\.google\.[^"\'<>\s]+)?/imgres\?([^"\'<>\s]+)',doc,flags=re.I):
            try:
                qs=parse_qs(html_lib.unescape(m.group(1)).replace('&amp;','&'))
                iu=unquote((qs.get('imgurl') or [''])[0]); ru=unquote((qs.get('imgrefurl') or [''])[0])
                add(iu,'',ru)
            except Exception: pass
            if len(out)>=limit: return out

        # JSON alternativo.
        for m in re.finditer(r'"(?:imageUrl|originalImageUrl)"\s*:\s*"([^"]+)"',doc,flags=re.I):
            chunk=doc[max(0,m.start()-700):min(len(doc),m.end()+900)]
            title=''; page=''
            for key in ('title','name','pt'):
                mm=re.search(r'"'+key+r'"\s*:\s*"([^"]*)"',chunk,flags=re.I)
                if mm: title=mm.group(1); break
            for key in ('contextLink','pageUrl','ru'):
                mm=re.search(r'"'+key+r'"\s*:\s*"([^"]*)"',chunk,flags=re.I)
                if mm: page=mm.group(1); break
            add(m.group(1),title,page)
            if len(out)>=limit: return out

        # Fallback sem título: só passa depois se URL/OCR confirmarem o produto.
        pat=r"(https?:\\?/\\?/[^\"'<>\s]+?\.(?:jpg|jpeg|png|webp)(?:\?[^\"'<>\s]*)?)"
        for m in re.finditer(pat,doc,flags=re.I):
            add(m.group(1),'','')
            if len(out)>=limit: return out
    return out

def _google_api_candidates(query,limit=20):
    """Opcional: Google Programmable Search JSON API quando key/cx estiverem configurados."""
    cfg={}
    try: cfg=json.loads(GOOGLE_CFG_FILE.read_text(encoding='utf-8-sig'))
    except Exception: pass
    key=os.environ.get('SR_GOOGLE_API_KEY') or cfg.get('api_key') or ''; cx=os.environ.get('SR_GOOGLE_CX') or cfg.get('cx') or ''
    if not key or not cx: return []
    out=[]
    for start in ((1,11) if limit>10 else (1,)):
        try:
            url=('https://customsearch.googleapis.com/customsearch/v1?key='+quote_plus(key)+'&cx='+quote_plus(cx)+'&searchType=image&safe=active&imgSize=large&gl=br&hl=pt-BR&num=10&start='+str(start)+'&q='+quote_plus(query))
            data=json.loads(_request(url,timeout=12).decode('utf-8','ignore'))
            for it in data.get('items') or []:
                u=it.get('link') or ''; image=it.get('image') or {}
                if _url_ok(u): out.append({'url':u,'title':it.get('title') or '','context':it.get('snippet') or '','page_url':image.get('contextLink') or '','query':query,'source':'Google Imagens API'})
                if len(out)>=limit: return out
        except Exception: break
    return out


def search_online_product_images(code,name,identity_key='',max_results=8):
    raise RuntimeError('Pesquisa automática de imagens desativada. Use a importação manual do Banco de Produtos.')
    identity_key=str(identity_key or 'temp'); safe_identity=_safe_stem(identity_key)
    code=re.sub(r'\D+','',str(code or '')); name=str(name or '').strip()
    profile=_product_profile(name,code); category=profile['category']
    results=[]; seen_urls=set(); seen_hashes=[]; meta=_load_meta(); raw_candidates=[]
    search_queries=_build_search_queries(name,code,category)

    if code and len(code)>=8:
        try:
            raw=_request(f'https://world.openfoodfacts.org/api/v2/product/{code}.json',timeout=8)
            data=json.loads(raw.decode('utf-8','ignore')); prod=data.get('product') or {}; urls=[]
            for k in ('image_front_url','image_url'):
                if prod.get(k): urls.append(prod.get(k))
            front=(((prod.get('selected_images') or {}).get('front') or {}).get('display') or {})
            for lang in ('pt','pt_BR','en'):
                if front.get(lang): urls.append(front.get(lang))
            title=' '.join(str(prod.get(k) or '') for k in ('product_name','brands','quantity'))
            for u in urls:
                raw_candidates.append({'url':u,'title':title,'context':'','page_url':'https://world.openfoodfacts.org/',
                                       'query':code,'source':'EAN • Open Food Facts','ean_exact':True,'query_type':'EAN'})
        except Exception: pass

    for q,qtype in search_queries:
        got=_google_api_candidates(q,20); got.extend(_google_direct_candidates(q,80))
        for c in got: c['query_type']=qtype; raw_candidates.append(c)
        if len(raw_candidates)>220: break

    prepared=[]
    for c in raw_candidates:
        u=str(c.get('url') or '')
        if not _url_ok(u) or u in seen_urls: continue
        seen_urls.add(u)
        # NÃO usar c.context: em páginas públicas do Google ele pode repetir a própria busca.
        rel,rel_reasons=_name_relevance(profile,c.get('title'),' ',u,c.get('page_url'),bool(c.get('ean_exact')))
        c['name_match']=rel; c['match_reasons']=rel_reasons
        strict=_strict_product_evidence(profile,c.get('title'),u,c.get('page_url'),'')
        c['strict_pre']=strict
        if not c.get('ean_exact') and strict.get('measure_conflict'): continue
        if not c.get('ean_exact') and profile.get('brand') and c.get('title') and not strict.get('brand_ok') and rel<48: continue
        prepared.append(c)

    qprio={'GOOGLE EXATO':4,'FRASE EXATA':3,'PRODUTO + MARCA + MEDIDA':2,'EAN':5}
    prepared.sort(key=lambda c:(1 if c.get('ean_exact') else 0,qprio.get(c.get('query_type'),0),
                                float((c.get('strict_pre') or {}).get('strength') or 0),float(c.get('name_match') or 0)),reverse=True)

    for c in prepared[:max(45,max_results*7)]:
        if len(results)>=max_results*3: break
        try:
            cache_path=_download_to_cache(c['url'],f'{safe_identity}_{len(results)+1}_{abs(hash(c["url"]))%100000}')
            ph=_dhash(cache_path)
            if any(_hamming(ph,h)<=5 for h in seen_hashes):
                try: cache_path.unlink()
                except Exception: pass
                continue

            vis,metrics,vis_reasons=_visual_score(cache_path,c['url'],name,category)
            ocr_text=_ocr_visible_text(cache_path)
            ocr_score,ocr_reasons=_ocr_name_score(profile,ocr_text)
            strict=_strict_product_evidence(profile,c.get('title'),c.get('url'),c.get('page_url'),ocr_text)

            if not c.get('ean_exact') and not strict.get('ok'):
                try: cache_path.unlink()
                except Exception: pass
                continue
            if not c.get('ean_exact') and profile.get('brand') and not strict.get('brand_ok'):
                try: cache_path.unlink()
                except Exception: pass
                continue
            if not c.get('ean_exact') and strict.get('measure_conflict'):
                try: cache_path.unlink()
                except Exception: pass
                continue

            rel=float(c.get('name_match') or 0); evidence=float(strict.get('strength') or 0)
            if ocr_score is None:
                final=round(evidence*.47+rel*.33+vis*.20,1)
            else:
                final=round(evidence*.38+rel*.27+float(ocr_score)*.23+vis*.12,1)
            if c.get('query_type')=='GOOGLE EXATO': final+=3
            elif c.get('query_type')=='FRASE EXATA': final+=1.5
            if c.get('ean_exact'): final=max(final,92.0)

            if not c.get('ean_exact') and profile.get('measures') and strict.get('measure_unknown') and evidence<52:
                try: cache_path.unlink()
                except Exception: pass
                continue
            if not c.get('ean_exact') and final<63:
                try: cache_path.unlink()
                except Exception: pass
                continue

            seen_hashes.append(ph); final=max(0,min(100,round(final,1)))
            grade='EXATA' if final>=92 else 'MUITO PROVÁVEL' if final>=84 else 'PROVÁVEL' if final>=74 else 'REVISAR'
            reasons=list(dict.fromkeys((c.get('match_reasons') or [])+strict.get('reasons',[])+vis_reasons+ocr_reasons))
            if strict.get('brand_ok') and profile.get('brand'): reasons.append('marca confirmada')
            if strict.get('measure_ok') and profile.get('measures'): reasons.append('medida confirmada')
            item={'path':str(cache_path),'source_url':c['url'],'source_name':c.get('source') or 'Google Imagens',
                  'confidence':grade,'score':final,'name_match':round(rel,1),'evidence_score':round(evidence,1),
                  'visual_score':round(vis,1),'ocr_score':(round(float(ocr_score),1) if ocr_score is not None else None),
                  'ocr_text':ocr_text,'metrics':metrics,'reasons':list(dict.fromkeys(reasons)),
                  'label':f"{c.get('source') or 'Google Imagens'} • {c.get('query_type') or 'GOOGLE EXATO'}",
                  'google_title':str(c.get('title') or '')[:350],'page_url':c.get('page_url') or '',
                  'query':c.get('query') or (search_queries[0][0] if search_queries else name),'strict':strict}
            results.append(item)
            meta[str(cache_path)]={'url':c['url'],'source':item['source_name'],'confidence':grade,'score':final,
                                   'name_match':rel,'evidence_score':evidence,'visual_score':vis,'ocr_score':ocr_score,
                                   'metrics':metrics,'reasons':item['reasons'],'query':item['query'],'created_at':_now()}
        except Exception:
            continue

    results.sort(key=lambda x:(float(x.get('score') or 0),float(x.get('evidence_score') or 0),
                               float(x.get('name_match') or 0),float(x.get('visual_score') or 0)),reverse=True)
    results=results[:max_results]; _save_meta(meta); return results

def approve_candidate(identity_key,codigo,canonical_name,candidate):
    src=Path(candidate['path'])
    if not src.exists(): raise FileNotFoundError('A imagem candidata não foi encontrada.')
    ext=src.suffix.lower() or '.jpg'; dst=OFFICIAL_DIR/f'{_safe_stem(identity_key)}{ext}'; shutil.copy2(src,dst)
    with _conn() as con:
        con.execute("""INSERT INTO catalog_images(identity_key,codigo,canonical_name,official_path,official_url,source_name,confidence,updated_at) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(identity_key) DO UPDATE SET codigo=excluded.codigo,canonical_name=excluded.canonical_name,official_path=excluded.official_path,official_url=excluded.official_url,source_name=excluded.source_name,confidence=excluded.confidence,updated_at=excluded.updated_at""",(str(identity_key),str(codigo or ''),str(canonical_name or ''),str(dst),str(candidate.get('source_url') or ''),str(candidate.get('source_name') or ''),str(candidate.get('confidence') or ''),_now()))
    try:
        prefs=_load_preferences(); prefs['approvals']=int(prefs.get('approvals') or 0)+1; cat=guess_category(canonical_name) or 'GERAL'; c=prefs.setdefault('categories',{}).setdefault(cat,{'approvals':0,'avg_border_light':0.0,'avg_coverage':0.0}); old=int(c.get('approvals') or 0); m=candidate.get('metrics') or _image_metrics(src); c['approvals']=old+1; c['avg_border_light']=round((float(c.get('avg_border_light') or 0)*old+float(m.get('border_light') or 0))/(old+1),4); c['avg_coverage']=round((float(c.get('avg_coverage') or 0)*old+float(m.get('coverage') or 0))/(old+1),4); _save_preferences(prefs)
    except Exception: pass
    return str(dst)


def clear_official_image(identity_key):
    info=get_image_info(identity_key)
    if info and info.get('official_path'):
        try:
            p=Path(info['official_path'])
            if p.exists(): p.unlink()
        except Exception: pass
    with _conn() as con: con.execute('DELETE FROM catalog_images WHERE identity_key=?',(str(identity_key),))

class ProductImageManager(tk.Toplevel):
    def __init__(self, parent, product_row, palette):
        super().__init__(parent)
        self.parent = parent
        self.product = dict(product_row or {})
        self.p = palette
        self.title('Banco de Produtos • Imagens do Produto')
        self.configure(bg=palette['APP_BG'])
        self.transient(parent)
        self.grab_set()
        self.geometry('940x620')
        self.minsize(860, 560)
        try:
            self.update_idletasks()
            px = parent.winfo_rootx() + max(30, (parent.winfo_width() - 940)//2)
            py = parent.winfo_rooty() + max(30, (parent.winfo_height() - 620)//2)
            self.geometry(f'940x620+{px}+{py}')
        except Exception:
            pass
        self.status = tk.StringVar(value='Banco de imagens manual. Selecione uma imagem do computador para definir como oficial.')
        self.candidates = []
        self._build()
        self.refresh_info()

    def _build(self):
        p = self.p
        top = tk.Frame(self, bg=p['APP_BG']); top.pack(fill='x', padx=20, pady=(18,10))
        tk.Label(top, text='Imagens do Produto', bg=p['APP_BG'], fg=p['TEXT'], font=('Segoe UI', 18, 'bold')).pack(anchor='w')
        tk.Label(top, text='Importação manual: escolha a imagem correta no seu computador. O SR Studio não pesquisa imagens na internet e não usa créditos da SR IA para isso.', bg=p['APP_BG'], fg=p['MUTED'], font=('Segoe UI', 9)).pack(anchor='w', pady=(2,0))

        body = tk.Frame(self, bg=p['APP_BG']); body.pack(fill='both', expand=True, padx=20, pady=(0,10))
        body.grid_columnconfigure(0, weight=2); body.grid_columnconfigure(1, weight=3); body.grid_rowconfigure(0, weight=1)
        left = tk.Frame(body, bg=p['CARD'], highlightbackground=p['LINE'], highlightthickness=1); left.grid(row=0, column=0, sticky='nsew', padx=(0,8))
        right = tk.Frame(body, bg=p['CARD'], highlightbackground=p['LINE'], highlightthickness=1); right.grid(row=0, column=1, sticky='nsew', padx=(8,0))

        self.info_label = tk.Label(left, text='', bg=p['CARD'], fg=p['TEXT'], justify='left', anchor='nw', wraplength=300, padx=14, pady=14, font=('Segoe UI', 9))
        self.info_label.pack(fill='x')
        btns = tk.Frame(left, bg=p['CARD']); btns.pack(fill='x', padx=14, pady=(0,8))
        tk.Button(btns, text='IMPORTAR IMAGEM MANUALMENTE', command=self.import_manual_image, bg=p['BLUE'], fg='white', relief='flat', font=('Segoe UI',8,'bold'), padx=12, pady=8).pack(fill='x', pady=2)
        tk.Button(btns, text='ABRIR IMAGEM OFICIAL', command=self.open_official, bg=p['LIGHT_BLUE'], fg=p['LIGHT_BLUE_TXT'], relief='flat', font=('Segoe UI',8,'bold'), padx=12, pady=7).pack(fill='x', pady=2)
        tk.Button(btns, text='REMOVER IMAGEM OFICIAL', command=self.clear_official, bg=p['RED'], fg=p['RED_TXT'], relief='flat', font=('Segoe UI',8,'bold'), padx=12, pady=7).pack(fill='x', pady=2)

        ctop = tk.Frame(right, bg=p['CARD']); ctop.pack(fill='x', padx=16, pady=(16,8))
        tk.Label(ctop, text='Banco de imagens SR', bg=p['CARD'], fg=p['TEXT'], font=('Segoe UI', 12, 'bold')).pack(anchor='w')
        tk.Label(right, text='1. Localize a imagem correta do produto no seu computador.\n\n2. Clique em IMPORTAR IMAGEM MANUALMENTE.\n\n3. O SR Studio copia a imagem para o banco oficial e vincula ao produto.\n\n4. Nas próximas campanhas, a imagem oficial será reutilizada sem nova pesquisa e sem gasto de créditos.', bg=p['CARD'], fg=p['MUTED'], justify='left', anchor='nw', wraplength=430, font=('Segoe UI', 10), padx=16, pady=12).pack(fill='both', expand=True)
        self.listbox = tk.Listbox(right)
        self.listbox.pack_forget()

        foot = tk.Frame(self, bg=p['CARD'], highlightbackground=p['LINE'], highlightthickness=1); foot.pack(fill='x', padx=20, pady=(0,18))
        tk.Label(foot, textvariable=self.status, bg=p['CARD'], fg=p['MUTED'], font=('Segoe UI',8), anchor='w').pack(fill='x', padx=12, pady=10)

    def refresh_info(self):
        r = self.product
        info = get_image_info(r.get('identity_key')) or {}
        category = get_category(r.get('identity_key')) or info.get('category') or guess_category(r.get('canonical_name')) or '—'
        official = info.get('official_path') if info else ''
        official_txt = official if official else 'Nenhuma imagem oficial aprovada.'
        self.info_label.config(text=(f"Produto: {r.get('canonical_name') or '—'}\n"
                                     f"Código/EAN: {r.get('codigo') or '—'}\n"
                                     f"Categoria/Setor: {category}\n"
                                     f"Ocorrências: {r.get('occurrence_count') or 0}\n\n"
                                     f"Imagem oficial:\n{official_txt}\n\n"
                                     f"Origem: {info.get('source_name') or '—'}\n"
                                     f"Confiança: {info.get('confidence') or '—'}"))

    def _set_status(self, text):
        self.status.set(text)

    def import_manual_image(self):
        file_path = filedialog.askopenfilename(
            parent=self,
            title='Selecionar imagem do produto',
            filetypes=[
                ('Imagens', '*.png *.jpg *.jpeg *.webp *.bmp'),
                ('PNG', '*.png'), ('JPEG', '*.jpg *.jpeg'), ('WebP', '*.webp'),
                ('Todos os arquivos', '*.*'),
            ],
        )
        if not file_path:
            return
        src = Path(file_path)
        if not src.exists():
            messagebox.showerror('Imagens do Produto', 'A imagem selecionada não foi encontrada.', parent=self)
            return
        if src.suffix.lower() not in {'.png','.jpg','.jpeg','.webp','.bmp'}:
            messagebox.showerror('Imagens do Produto', 'Formato não suportado. Use PNG, JPG, JPEG, WEBP ou BMP.', parent=self)
            return
        try:
            r = self.product
            candidate = {
                'path': str(src),
                'source_url': '',
                'source_name': 'Importação manual',
                'confidence': 'MANUAL',
                'metrics': _image_metrics(src),
            }
            approve_candidate(r.get('identity_key'), r.get('codigo'), r.get('canonical_name'), candidate)
            self._set_status('Imagem importada e definida como oficial. Nenhuma pesquisa online/IA foi usada.')
            self.refresh_info()
            try:
                self.parent.refresh()
            except Exception:
                pass
        except Exception as e:
            messagebox.showerror('Imagens do Produto', f'Não foi possível importar a imagem.\n\n{e}', parent=self)

    def open_google_search(self):
        messagebox.showinfo('Imagens do Produto', 'A pesquisa automática/online foi desativada. Importe a imagem manualmente para montar o Banco de Imagens SR.', parent=self)

    def search_images(self):
        self.import_manual_image()

    def _finish_search(self, items):
        self.candidates = list(items or [])
        self.listbox.delete(0, 'end')
        if not self.candidates:
            self._set_status('Nenhuma imagem foi encontrada automaticamente. Você pode tentar novamente depois.')
            return
        for i, c in enumerate(self.candidates, 1):
            self.listbox.insert('end', f"{i}. {c.get('score',0):.0f}% • PRODUTO {c.get('evidence_score',0):.0f}% • NOME {c.get('name_match',0):.0f}% • OCR {(c.get('ocr_score') if c.get('ocr_score') is not None else '—')} • {c.get('confidence')} • {c.get('label') or c.get('source_name')}")
        self.listbox.selection_set(0)
        self._set_status(f"{len(self.candidates)} candidato(s) ranqueado(s). O primeiro tem a maior confirmação de produto/marca/medida. Imagens sem essa confirmação são filtradas; a aprovação permanece manual.")

    def _selected_candidate(self):
        sel = self.listbox.curselection()
        if not sel:
            return None
        idx = sel[0]
        if idx < 0 or idx >= len(self.candidates):
            return None
        return self.candidates[idx]

    def _open_path(self, path):
        path = str(path or '').strip()
        if not path:
            messagebox.showinfo('Imagens do Produto', 'Nenhum arquivo informado.', parent=self)
            return
        p = Path(path)
        if not p.exists():
            alt = p.with_name(_safe_stem(p.stem) + p.suffix)
            if alt.exists():
                p = alt
            else:
                messagebox.showinfo('Imagens do Produto', f'Arquivo não encontrado:\n{p}\n\nFaça uma nova busca da imagem.', parent=self)
                return
        try:
            if os.name == 'nt':
                os.startfile(os.path.normpath(str(p)))  # type: ignore[attr-defined]
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', str(p)])
            else:
                subprocess.Popen(['xdg-open', str(p)])
        except Exception as e:
            messagebox.showerror('Imagens do Produto', f'Não foi possível abrir a imagem.\n\n{e}\n\nArquivo: {p}', parent=self)

    def open_selected_candidate(self):
        c = self._selected_candidate()
        if not c:
            messagebox.showinfo('Imagens do Produto', 'Selecione um candidato.', parent=self); return
        self._open_path(c.get('path'))

    def approve_selected(self):
        c = self._selected_candidate()
        if not c:
            messagebox.showinfo('Imagens do Produto', 'Selecione um candidato.', parent=self); return
        try:
            r = self.product
            approve_candidate(r.get('identity_key'), r.get('codigo'), r.get('canonical_name'), c)
            self._set_status('Imagem oficial atualizada com sucesso.')
            self.refresh_info()
            try:
                self.parent.refresh()
            except Exception:
                pass
        except Exception as e:
            messagebox.showerror('Imagens do Produto', str(e), parent=self)

    def approve_first(self):
        if not self.candidates:
            self.import_manual_image(); return
        self.listbox.selection_clear(0, 'end')
        self.listbox.selection_set(0)
        self.approve_selected()

    def open_official(self):
        info = get_image_info(self.product.get('identity_key')) or {}
        p = info.get('official_path')
        if not p:
            messagebox.showinfo('Imagens do Produto', 'Este produto ainda não possui imagem oficial.', parent=self); return
        self._open_path(p)

    def clear_official(self):
        if not messagebox.askyesno('Imagens do Produto', 'Remover a imagem oficial deste produto?', parent=self):
            return
        clear_official_image(self.product.get('identity_key'))
        self.refresh_info()
        self._set_status('Imagem oficial removida.')
        try:
            self.parent.refresh()
        except Exception:
            pass
