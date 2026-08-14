# -*- coding: utf-8 -*-
import os
import re
import json
import math
import time
import queue
import hashlib
import shutil
import sqlite3
import tempfile
import threading
import subprocess
import unicodedata
from pathlib import Path
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from datetime import datetime

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from pypdf import PdfReader, PdfWriter
from ui_v2 import choose_palette, center_toplevel, add_tooltip, print_pdf, default_printer_name, cache_key, file_signature, ask_string
from SRStudio21 import dated_output_dir, smart_pdf_name, unique_path, record_product_jobs, record_reprint, pdf_with_copies

APP_DIR = Path(__file__).resolve().parent
MODELS = APP_DIR / "modelos"
MODEL = MODELS / "ATACADO.pptx"
ATACADO_UNIT_OPTIONS=["UN","KG","À LATA","À GARRAFA"]
ENGINE = APP_DIR / "AtacadoEngine.ps1"
PREVIEW_ENGINE = APP_DIR / "AtacadoPreview.ps1"

LOCAL_DATA = Path(os.environ.get("LOCALAPPDATA", str(APP_DIR))) / "SR_Studio_2.0"
LOCAL_DATA.mkdir(parents=True, exist_ok=True)

# A memória do Atacado é portátil: ao copiar a pasta do SR Studio para outro PC,
# o histórico acompanha o programa. Se a pasta estiver protegida contra escrita,
# cai automaticamente para o LocalAppData do Windows.
PORTABLE_DATA = APP_DIR / "dados"
try:
    PORTABLE_DATA.mkdir(parents=True, exist_ok=True)
    _probe=PORTABLE_DATA / ".write_test"
    _probe.write_text("ok",encoding="utf-8"); _probe.unlink()
    DATA_DIR=PORTABLE_DATA
except Exception:
    DATA_DIR=LOCAL_DATA / "dados_atacado"
    DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "atacado_historico.db"
BACKUP_DIR = DATA_DIR / "backups"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

_PAL=choose_palette("Automático")
APP_BG=_PAL["APP_BG"]; CARD=_PAL["CARD"]; TEXT=_PAL["TEXT"]; MUTED=_PAL["MUTED"]; LINE=_PAL["LINE"]
BLUE=_PAL["BLUE"]; BLUE2=_PAL["BLUE2"]; GREEN=_PAL["GREEN"]; GREEN_TXT=_PAL["GREEN_TXT"]
ORANGE=_PAL["ORANGE"]; ORANGE_TXT=_PAL["ORANGE_TXT"]; LIGHT_BLUE=_PAL["LIGHT_BLUE"]; LIGHT_BLUE_TXT=_PAL["LIGHT_BLUE_TXT"]
RED=_PAL["RED"]; RED_TXT=_PAL["RED_TXT"]; YELLOW=_PAL["YELLOW"]; YELLOW_TXT=_PAL["YELLOW_TXT"]
PURPLE=_PAL["PURPLE"]; PURPLE_TXT=_PAL["PURPLE_TXT"]; ROW_ALT=_PAL["ROW_ALT"]; SELECT_BG=_PAL["SELECT"]

def norm(v):
    s="" if v is None else str(v)
    s=unicodedata.normalize("NFD",s)
    s="".join(c for c in s if unicodedata.category(c)!="Mn")
    return re.sub(r"[^A-Z0-9]+"," ",s.upper()).strip()

def dec(v):
    if isinstance(v, Decimal): return v
    s=str(v or "").strip().replace("R$","").replace(" ","")
    if not s: return None
    if "," in s and "." in s: s=s.replace(".","").replace(",",".")
    elif "," in s: s=s.replace(",",".")
    try: return Decimal(s)
    except InvalidOperation: return None

def money(v):
    d=dec(v)
    if d is None: return str(v or "")
    return f"{d.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):.2f}".replace(".",",")

def qty_value(v, unit):
    s=str(v).strip()
    d=dec(s)
    return d if d is not None else Decimal("0")

def qty_display(v, unit):
    s=str(v).strip()
    if unit=="KG":
        # CISS normalmente usa três casas para peso.
        d=dec(s)
        if d is not None:
            return f"{d:.3f}".replace(".",",")
    d=dec(s)
    if d is not None and d == d.to_integral_value():
        return str(int(d))
    return s

def sha256_file(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()

def connect_db():
    con=sqlite3.connect(DB_PATH, timeout=15)
    con.row_factory=sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    return con

def init_db():
    with connect_db() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS relatorios(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hash_arquivo TEXT UNIQUE NOT NULL,
            arquivo TEXT NOT NULL,
            data_relatorio TEXT,
            empresa_codigo TEXT,
            empresa_nome TEXT,
            data_importacao TEXT NOT NULL,
            total_produtos INTEGER DEFAULT 0,
            novos INTEGER DEFAULT 0,
            alterados INTEGER DEFAULT 0,
            removidos INTEGER DEFAULT 0,
            agrupados INTEGER DEFAULT 0,
            alertas INTEGER DEFAULT 0,
            base_inicial INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS itens_relatorio(
            relatorio_id INTEGER NOT NULL,
            codigo TEXT NOT NULL,
            descricao TEXT NOT NULL,
            varejo TEXT,
            quantidade TEXT,
            unidade TEXT,
            desconto TEXT,
            atacado TEXT,
            total TEXT,
            PRIMARY KEY(relatorio_id,codigo),
            FOREIGN KEY(relatorio_id) REFERENCES relatorios(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS cartazes_relatorio(
            relatorio_id INTEGER NOT NULL,
            cartaz_chave TEXT NOT NULL,
            nome TEXT NOT NULL,
            varejo TEXT,
            quantidade TEXT,
            unidade TEXT,
            atacado TEXT,
            total TEXT,
            codigos_json TEXT,
            agrupado INTEGER DEFAULT 0,
            status TEXT,
            motivo TEXT,
            alerta TEXT,
            PRIMARY KEY(relatorio_id,cartaz_chave),
            FOREIGN KEY(relatorio_id) REFERENCES relatorios(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS produtos(
            codigo TEXT PRIMARY KEY,
            ultimo_nome TEXT,
            unidade_preferida TEXT,
            ignorado INTEGER DEFAULT 0,
            nunca_agrupar INTEGER DEFAULT 0,
            atualizado_em TEXT
        );
        CREATE TABLE IF NOT EXISTS regras_agrupamento(
            chave_base TEXT PRIMARY KEY,
            complemento TEXT NOT NULL,
            nome_cartaz TEXT,
            atualizado_em TEXT
        );
        CREATE TABLE IF NOT EXISTS membros_grupo(
            chave_base TEXT NOT NULL,
            codigo TEXT NOT NULL,
            PRIMARY KEY(chave_base,codigo)
        );
        """)
init_db()

def backup_db():
    if not DB_PATH.exists() or DB_PATH.stat().st_size < 100:
        return None
    stamp=datetime.now().strftime("%Y%m%d_%H%M%S")
    out=BACKUP_DIR/f"atacado_historico_{stamp}.db"
    # backup API é consistente mesmo com WAL.
    src=sqlite3.connect(DB_PATH)
    dst=sqlite3.connect(out)
    try: src.backup(dst)
    finally:
        dst.close(); src.close()
    files=sorted(BACKUP_DIR.glob("atacado_historico_*.db"), key=lambda p:p.stat().st_mtime, reverse=True)
    for old in files[20:]:
        try: old.unlink()
        except Exception: pass
    return out

def infer_atacado_unit(desc_, qty):
    """Detecta a unidade comercial usada no cartaz Atacado.

    Peso continua tendo prioridade. Para itens unitários, reconhece também
    lata e garrafa a partir da descrição do CISS.
    """
    qty_txt=str(qty or "").strip()
    if re.fullmatch(r"\d+,\d{3}",qty_txt):
        return "KG"
    n=norm(desc_)
    # Garrafa: somente marcadores explícitos para evitar confundir PET/volume.
    if re.search(r"\bGARRAFA(S)?\b|\bGFA\b|\bGF\b",n):
        return "À GARRAFA"
    # Lata: CISS frequentemente abrevia LATA como LT em bebidas.
    if re.search(r"\bLATA(S)?\b",n):
        return "À LATA"
    if re.search(r"\bLT\b",n) and any(k in n for k in ("CERVEJA","REFRIGERANTE","ENERGETICO","BEBIDA","AGUA TONICA","CHA")):
        return "À LATA"
    return "UN"

def parse_report(path, progress=None):
    path=Path(path)
    reader=PdfReader(str(path))
    total_pages=len(reader.pages)
    all_text=[]
    items=[]
    pending=None
    for pi,page in enumerate(reader.pages,1):
        text=page.extract_text() or ""
        all_text.append(text)
        lines=[x.strip() for x in text.splitlines() if x.strip()]
        pending=None
        for line in lines:
            # formato extraído pelo pypdf: DESCRIÇÃO 19,64Preço Varejo:
            m=re.match(r"^(\d+)\s*-\s*(.*?)\s+(\d*,\d{2})Preço Varejo:\s*$",line,re.I)
            if not m:
                # fallback para relatórios onde o rótulo vem antes do valor
                m2=re.match(r"^(\d+)\s*-\s*(.*?)\s+Preço Varejo:\s*(\d*,\d{2})\s*$",line,re.I)
                if m2: m=m2
            if m:
                pending=(m.group(1),m.group(2).strip(),m.group(3))
                continue
            q=re.match(r"^A partir de\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)\s*$",line,re.I)
            if q and pending:
                code,desc_,retail=pending
                qty,discount,wholesale=q.groups()
                # Quantidade decimal com 3 casas representa peso; itens unitários
                # também podem ser vendidos À LATA ou À GARRAFA.
                unit=infer_atacado_unit(desc_,qty)
                qd=dec(qty) or Decimal("0")
                wd=dec(wholesale) or Decimal("0")
                total=(qd*wd).quantize(Decimal("0.01"),rounding=ROUND_HALF_UP)
                items.append({
                    "codigo":code, "descricao":desc_, "varejo":money(retail),
                    "quantidade":qty_display(qty,unit), "unidade":unit,
                    "desconto":money(discount), "atacado":money(wholesale),
                    "total":money(total),
                })
                pending=None
        if progress:
            progress(pi,total_pages,f"Lendo página {pi} de {total_pages} • {len(items)} produtos encontrados")
    full="\n".join(all_text)
    if "782-Listagem de Produtos Atacarejo" not in full:
        raise RuntimeError("O PDF não é o relatório 782 - Listagem de Produtos Atacarejo.")
    em=re.search(r"Empresa:\s*(\d+)\s*-\s*([^\r\n]+)",full,re.I)
    dm=re.search(r"\b(\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2})\b",full)
    if not em:
        raise RuntimeError("Não foi possível identificar a empresa/loja no relatório.")
    if not items:
        raise RuntimeError("Nenhum produto Atacarejo foi identificado no relatório.")
    return {
        "items":items,
        "empresa_codigo":em.group(1).strip(),
        "empresa_nome":em.group(2).strip(),
        "data_relatorio":dm.group(1) if dm else "",
        "pages":total_pages,
    }

MEASURE_RE=re.compile(r"\b(\d+(?:[.,]\d+)?)\s*(KG|ML|G|L)\b",re.I)
def measure_of(desc_):
    m=MEASURE_RE.search(desc_)
    return ((m.group(1)+m.group(2)).upper() if m else "")

def tokens(desc_):
    return norm(desc_).split()

def family_prefix(ts):
    if len(ts)<2: return ts
    a=ts[0:2]
    if len(ts)>=3 and ((ts[0]=="SUCO" and ts[1]=="DEL") or
                       (ts[0]=="LAVA" and ts[1]=="LOUCAS") or
                       (ts[0]=="MACARRAO" and ts[1] in {"INST","INSTANTANEO"}) or
                       (ts[0]=="AGUA" and ts[1]=="DE")):
        a=ts[:3]
    if len(ts)>=4 and ts[0]=="REFRESCO" and ts[1]=="EM" and ts[2]=="PO":
        a=ts[:4]
    return a

def common_prefix_token_lists(lists):
    if not lists: return []
    out=[]
    for vals in zip(*lists):
        if len(set(vals))==1: out.append(vals[0])
        else: break
    return out

def qualifier_for(descs):
    s=" ".join(norm(x) for x in descs)
    if any(k in s for k in ["FRALDA ","TAMANHO "]): return "TAMANHOS"
    if any(k in s for k in ["SABONETE ","AMACIANTE ","DETERGENTE ","DESINFETANTE ","LIMPADOR ","SHAMPOO ","CONDICIONADOR ","PERFUME "]):
        return "FRAGRÂNCIAS"
    if any(k in s for k in ["ENERGETICO ","SUCO ","REFRESCO ","REFRIGERANTE ","ISOTONICO ","BISCOITO ","BOLACHA ","CHICLETE ","DROPS ","MACARRAO INST ","ICE "]):
        return "SABORES"
    if "CERVEJA " in s: return "TIPOS"
    return "VARIEDADES"

def product_flags():
    with connect_db() as con:
        rows=con.execute("SELECT codigo,ignorado,nunca_agrupar,unidade_preferida FROM produtos").fetchall()
    return {r["codigo"]:dict(r) for r in rows}

def group_rules():
    with connect_db() as con:
        rows=con.execute("SELECT * FROM regras_agrupamento").fetchall()
    return {r["chave_base"]:dict(r) for r in rows}

def build_posters(items):
    flags=product_flags()
    rules=group_rules()
    active=[]
    ignored_count=0
    for it in items:
        f=flags.get(it["codigo"],{})
        if f.get("ignorado"):
            ignored_count+=1; continue
        x=dict(it)
        if f.get("unidade_preferida") in set(ATACADO_UNIT_OPTIONS):
            x["unidade"]=f["unidade_preferida"]
            x["quantidade"]=qty_display(x["quantidade"],x["unidade"])
        x["_never_group"]=bool(f.get("nunca_agrupar"))
        active.append(x)

    buckets={}
    singles=[]
    for it in active:
        if it["_never_group"]:
            singles.append([it]); continue
        ts=tokens(it["descricao"])
        fp=family_prefix(ts)
        if len(fp)<2:
            singles.append([it]); continue
        measure=measure_of(it["descricao"])
        key="|".join(fp)+"|"+measure
        commercial=(it["varejo"],it["quantidade"],it["unidade"],it["atacado"])
        buckets.setdefault((key,commercial),[]).append(it)

    families=[]
    for (base_key,commercial),members in buckets.items():
        if len(members)<2:
            singles.append(members); continue
        desc_tokens=[tokens(x["descricao"]) for x in members]
        cp=common_prefix_token_lists(desc_tokens)
        # Só agrupa quando há uma base textual suficientemente forte.
        if len(cp)<2:
            singles.append(members); continue
        # Precisa existir parte variável em pelo menos dois membros.
        if len({norm(x["descricao"]) for x in members})<2:
            singles.append(members); continue
        families.append((base_key,members,cp))

    posters=[]
    learned=[]
    for base_key,members,cp in families:
        rule=rules.get(base_key)
        q=rule["complemento"] if rule else qualifier_for([x["descricao"] for x in members])
        if rule and rule.get("nome_cartaz"):
            name=rule["nome_cartaz"]
        else:
            # Mantém o nome-base próximo ao relatório e insere um complemento comercial.
            core=" ".join(cp)
            measure=measure_of(members[0]["descricao"])
            if q=="FRAGRÂNCIAS" and core.startswith("SABONETE ") and measure:
                core2=re.sub(r"\s+\d+(?:[.,]\d+)?\s*(?:KG|ML|G|L)\b","",core,flags=re.I).strip()
                name=f"{core2} {q} {measure}"
            else:
                # Se o tamanho está em uma posição variável da descrição, não o perde no agrupamento.
                if measure and norm(measure) not in norm(core):
                    core=f"{core} {measure}"
                name=f"{core} {q}"
            name=" ".join(name.split())
        first=members[0]
        p={
            "cartaz_chave":"G:"+base_key,
            "nome":name,
            "varejo":first["varejo"],"quantidade":first["quantidade"],"unidade":first["unidade"],
            "atacado":first["atacado"],"total":first["total"],"desconto":first.get("desconto",""),
            "codigos":[x["codigo"] for x in members],
            "agrupado":True,"complemento":q,"base_key":base_key,
            "selected":True,"copies":1,
        }
        posters.append(p)
        learned.append((base_key,q,name,p["codigos"]))

    for member_list in singles:
        for it in member_list:
            posters.append({
                "cartaz_chave":"P:"+it["codigo"],"nome":it["descricao"],
                "varejo":it["varejo"],"quantidade":it["quantidade"],"unidade":it["unidade"],
                "atacado":it["atacado"],"total":it["total"],"desconto":it.get("desconto",""),
                "codigos":[it["codigo"]],"agrupado":False,"complemento":"",
                "base_key":"","selected":True,"copies":1,
            })

    # aprende os grupos detectados para manter nomenclatura estável.
    now=datetime.now().isoformat(timespec="seconds")
    with connect_db() as con:
        for base_key,q,name,codes in learned:
            con.execute("""INSERT INTO regras_agrupamento(chave_base,complemento,nome_cartaz,atualizado_em)
                           VALUES(?,?,?,?)
                           ON CONFLICT(chave_base) DO UPDATE SET complemento=excluded.complemento,
                           nome_cartaz=COALESCE(regras_agrupamento.nome_cartaz,excluded.nome_cartaz),
                           atualizado_em=excluded.atualizado_em""",(base_key,q,name,now))
            for c in codes:
                con.execute("INSERT OR IGNORE INTO membros_grupo(chave_base,codigo) VALUES(?,?)",(base_key,c))
    return posters,ignored_count

def poster_alert(p):
    alerts=[]
    r=dec(p["varejo"]); w=dec(p["atacado"]); q=dec(p["quantidade"])
    if r is None or r<=0: alerts.append("Varejo inválido")
    if w is None or w<=0: alerts.append("Atacado inválido")
    if q is None or q<=0: alerts.append("Quantidade inválida")
    if r is not None and w is not None:
        if w>=r: alerts.append("Atacado ≥ varejo")
        d=dec(p.get("desconto"))
        if r>0 and d is not None:
            calc=((r-w)/r*Decimal("100"))
            if abs(calc-d) > Decimal("0.75"):
                alerts.append("Desconto divergente")
    return " • ".join(alerts)

def poster_tuple(p):
    return (
        norm(p["nome"]), money(p["varejo"]), str(p["quantidade"]).strip(),
        p["unidade"], money(p["atacado"])
    )

def load_report_posters(report_id):
    if not report_id: return {}
    with connect_db() as con:
        rows=con.execute("SELECT * FROM cartazes_relatorio WHERE relatorio_id=?",(report_id,)).fetchall()
    out={}
    for r in rows:
        out[r["cartaz_chave"]]=dict(r)
    return out

def latest_report_id(exclude_hash=None):
    with connect_db() as con:
        if exclude_hash:
            r=con.execute("SELECT id FROM relatorios WHERE hash_arquivo<>? ORDER BY id DESC LIMIT 1",(exclude_hash,)).fetchone()
        else:
            r=con.execute("SELECT id FROM relatorios ORDER BY id DESC LIMIT 1").fetchone()
    return r["id"] if r else None

_ATACADO_POSTERS_CACHE=[]
_ATACADO_CACHE_REPORT_ID=None
_ATACADO_CACHE_LOCK=threading.RLock()

def invalidate_atacado_cache():
    global _ATACADO_POSTERS_CACHE,_ATACADO_CACHE_REPORT_ID
    with _ATACADO_CACHE_LOCK:
        _ATACADO_POSTERS_CACHE=[];_ATACADO_CACHE_REPORT_ID=None

def preload_atacado_catalog(force=False):
    global _ATACADO_POSTERS_CACHE,_ATACADO_CACHE_REPORT_ID
    with _ATACADO_CACHE_LOCK:
        rid=latest_report_id()
        if not rid:
            _ATACADO_POSTERS_CACHE=[];_ATACADO_CACHE_REPORT_ID=None;return 0
        if _ATACADO_CACHE_REPORT_ID==rid and _ATACADO_POSTERS_CACHE and not force:
            return len(_ATACADO_POSTERS_CACHE)
        with connect_db() as con:
            rows=con.execute("SELECT * FROM cartazes_relatorio WHERE relatorio_id=? ORDER BY nome COLLATE NOCASE",(rid,)).fetchall()
        out=[]
        for r in rows:
            d=dict(r);d["report_id"]=rid;d["selected"]=True;d["copies"]=1
            try:d["codigos"]=json.loads(d.get("codigos_json") or "[]")
            except Exception:d["codigos"]=[]
            d["_search_norm"]=norm((d.get("nome") or "")+" "+" ".join(str(x) for x in d["codigos"]))
            out.append(d)
        _ATACADO_POSTERS_CACHE=out;_ATACADO_CACHE_REPORT_ID=rid
        return len(out)

def latest_atacado_posters(search="", limit=1000):
    """Retorna os cartazes do relatório Atacado mais recente para seleção na Geração Manual."""
    preload_atacado_catalog();q=norm(search);out=[]
    for r in (_ATACADO_POSTERS_CACHE or []):
        if q and q not in r.get("_search_norm",""):continue
        out.append(dict(r))
        if len(out)>=int(limit):break
    return out


def compare_posters(posters,previous):
    for p in posters:
        p.setdefault("copies",1)
        p["alerta"]=poster_alert(p)
        prev=previous.get(p["cartaz_chave"])
        if not prev:
            p["status"]="NOVO"; p["motivo"]="Produto/cartaz novo"
        else:
            p["_previous"]={"nome":prev["nome"],"varejo":prev["varejo"],"quantidade":prev["quantidade"],"unidade":prev["unidade"],"atacado":prev["atacado"],"total":prev["total"]}
            current=poster_tuple(p)
            old=(norm(prev["nome"]),money(prev["varejo"]),str(prev["quantidade"]).strip(),prev["unidade"],money(prev["atacado"]))
            if current==old:
                p["status"]="SEM ALTERAÇÃO"; p["motivo"]=""
            else:
                reasons=[]
                labels=["Nome","Varejo","Quantidade","Unidade","Atacado"]
                for a,b,label in zip(current,old,labels):
                    if a!=b: reasons.append(label)
                p["status"]="ALTERADO"; p["motivo"]=", ".join(reasons)
                try:
                    old_w=dec(prev["atacado"]); new_w=dec(p["atacado"])
                    old_r=dec(prev["varejo"]); new_r=dec(p["varejo"])
                    extra=[]
                    if old_w and old_w>0 and new_w is not None and abs(new_w-old_w)/old_w > Decimal("0.30"):
                        extra.append("Variação alta no atacado")
                    if old_r and old_r>0 and new_r is not None and abs(new_r-old_r)/old_r > Decimal("0.30"):
                        extra.append("Variação alta no varejo")
                    if extra:
                        p["alerta"]=" • ".join([x for x in [p.get("alerta","")] + extra if x])
                except Exception:
                    pass
        p["selected"]=p["status"] in {"NOVO","ALTERADO"}
    removed=[k for k in previous.keys() if k not in {p["cartaz_chave"] for p in posters}]
    return removed

def save_report(path,parsed,posters,removed,ignored_count):
    h=sha256_file(path)
    with connect_db() as con:
        existing=con.execute("SELECT id FROM relatorios WHERE hash_arquivo=?",(h,)).fetchone()
    if existing:
        rid=existing["id"]
        stored=load_report_posters(rid)
        result=[]
        for p in posters:
            s=stored.get(p["cartaz_chave"])
            if s:
                p["status"]=s["status"]; p["motivo"]=s["motivo"] or ""; p["alerta"]=s["alerta"] or ""
                p["selected"]=p["status"] in {"NOVO","ALTERADO"}
            p.setdefault("copies",1)
            result.append(p)
        return rid,True

    backup_db()
    new_count=sum(p["status"]=="NOVO" for p in posters)
    altered=sum(p["status"]=="ALTERADO" for p in posters)
    grouped=sum(bool(p["agrupado"]) for p in posters)
    alerts=sum(bool(p.get("alerta")) for p in posters)
    with connect_db() as con:
        cur=con.execute("""INSERT INTO relatorios(hash_arquivo,arquivo,data_relatorio,empresa_codigo,empresa_nome,
                    data_importacao,total_produtos,novos,alterados,removidos,agrupados,alertas)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (h,Path(path).name,parsed["data_relatorio"],parsed["empresa_codigo"],parsed["empresa_nome"],
                     datetime.now().isoformat(timespec="seconds"),len(parsed["items"]),new_count,altered,len(removed),grouped,alerts))
        rid=cur.lastrowid
        now=datetime.now().isoformat(timespec="seconds")
        for it in parsed["items"]:
            con.execute("""INSERT INTO itens_relatorio VALUES(?,?,?,?,?,?,?,?,?)""",
                        (rid,it["codigo"],it["descricao"],it["varejo"],it["quantidade"],it["unidade"],
                         it["desconto"],it["atacado"],it["total"]))
            con.execute("""INSERT INTO produtos(codigo,ultimo_nome,atualizado_em) VALUES(?,?,?)
                           ON CONFLICT(codigo) DO UPDATE SET ultimo_nome=excluded.ultimo_nome,atualizado_em=excluded.atualizado_em""",
                        (it["codigo"],it["descricao"],now))
        for p in posters:
            con.execute("""INSERT INTO cartazes_relatorio VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (rid,p["cartaz_chave"],p["nome"],p["varejo"],p["quantidade"],p["unidade"],p["atacado"],p["total"],
                         json.dumps(p["codigos"],ensure_ascii=False),1 if p["agrupado"] else 0,
                         p["status"],p["motivo"],p.get("alerta","")))
    invalidate_atacado_cache()
    preload_atacado_catalog(force=True)
    return rid,False

def analyze_and_store(path,progress=None):
    parsed=parse_report(path,progress)
    h=sha256_file(path)
    prev_id=latest_report_id(exclude_hash=h)
    prev=load_report_posters(prev_id)
    if progress: progress(1,4,"Aplicando memória e agrupamentos inteligentes...")
    posters,ignored=build_posters(parsed["items"])
    if progress: progress(2,4,"Comparando com o último relatório...")
    removed=compare_posters(posters,prev)
    if progress: progress(3,4,"Salvando histórico e backup...")
    rid,duplicate=save_report(path,parsed,posters,removed,ignored)
    if progress: progress(4,4,"Análise concluída")
    first=(prev_id is None and not duplicate)
    return {
        "path":str(path),"report_id":rid,"duplicate":duplicate,"first_report":first,
        "parsed":parsed,"posters":posters,"removed_keys":removed,"ignored":ignored,
        "counts":{
            "raw":len(parsed["items"]),"posters":len(posters),
            "new":sum(p["status"]=="NOVO" for p in posters),
            "changed":sum(p["status"]=="ALTERADO" for p in posters),
            "same":sum(p["status"]=="SEM ALTERAÇÃO" for p in posters),
            "removed":len(removed),"grouped":sum(p["agrupado"] for p in posters),
            "alerts":sum(bool(p.get("alerta")) for p in posters),
        }
    }

def set_baseline(report_id):
    with connect_db() as con:
        con.execute("UPDATE relatorios SET base_inicial=1,novos=0,alterados=0 WHERE id=?",(report_id,))
        con.execute("UPDATE cartazes_relatorio SET status='SEM ALTERAÇÃO',motivo='' WHERE relatorio_id=?",(report_id,))

def set_ignored(codes,value=True):
    now=datetime.now().isoformat(timespec="seconds")
    with connect_db() as con:
        for code in codes:
            con.execute("""INSERT INTO produtos(codigo,ignorado,atualizado_em) VALUES(?,?,?)
                           ON CONFLICT(codigo) DO UPDATE SET ignorado=excluded.ignorado,atualizado_em=excluded.atualizado_em""",
                        (code,1 if value else 0,now))

def set_never_group(codes,value=True):
    now=datetime.now().isoformat(timespec="seconds")
    with connect_db() as con:
        for code in codes:
            con.execute("""INSERT INTO produtos(codigo,nunca_agrupar,atualizado_em) VALUES(?,?,?)
                           ON CONFLICT(codigo) DO UPDATE SET nunca_agrupar=excluded.nunca_agrupar,atualizado_em=excluded.atualizado_em""",
                        (code,1 if value else 0,now))

def update_group_name(base_key,name,qualifier):
    with connect_db() as con:
        con.execute("""INSERT INTO regras_agrupamento(chave_base,complemento,nome_cartaz,atualizado_em)
                       VALUES(?,?,?,?) ON CONFLICT(chave_base) DO UPDATE SET complemento=excluded.complemento,
                       nome_cartaz=excluded.nome_cartaz,atualizado_em=excluded.atualizado_em""",
                    (base_key,qualifier,name,datetime.now().isoformat(timespec="seconds")))

def update_report_poster_name(report_id,key,name):
    with connect_db() as con:
        con.execute("UPDATE cartazes_relatorio SET nome=? WHERE relatorio_id=? AND cartaz_chave=?",(name,report_id,key))

def remove_current_poster(report_id,key):
    with connect_db() as con:
        con.execute("DELETE FROM cartazes_relatorio WHERE relatorio_id=? AND cartaz_chave=?",(report_id,key))

def upsert_current_poster(report_id,p):
    with connect_db() as con:
        con.execute("""INSERT OR REPLACE INTO cartazes_relatorio
                       (relatorio_id,cartaz_chave,nome,varejo,quantidade,unidade,atacado,total,
                        codigos_json,agrupado,status,motivo,alerta)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (report_id,p["cartaz_chave"],p["nome"],p["varejo"],p["quantidade"],p["unidade"],
                     p["atacado"],p["total"],json.dumps(p["codigos"],ensure_ascii=False),
                     1 if p.get("agrupado") else 0,p["status"],p.get("motivo",""),p.get("alerta","")))

def mark_posters_generated(report_id, poster_keys):
    """Marca somente os cartazes concluídos e recalcula as pendências do relatório."""
    keys=[str(x) for x in (poster_keys or []) if str(x).strip()]
    if not report_id or not keys:
        return
    now=datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    with connect_db() as con:
        for key in keys:
            con.execute(
                """UPDATE cartazes_relatorio
                   SET status='GERADO', motivo=?
                   WHERE relatorio_id=? AND cartaz_chave=?""",
                (f"Gerado em {now}", report_id, key)
            )
        row=con.execute(
            """SELECT
                   SUM(CASE WHEN status='NOVO' THEN 1 ELSE 0 END) AS novos,
                   SUM(CASE WHEN status='ALTERADO' THEN 1 ELSE 0 END) AS alterados
               FROM cartazes_relatorio WHERE relatorio_id=?""",
            (report_id,)
        ).fetchone()
        con.execute(
            "UPDATE relatorios SET novos=?, alterados=? WHERE id=?",
            (int(row["novos"] or 0), int(row["alterados"] or 0), report_id)
        )

def history_for_code(code):
    with connect_db() as con:
        return con.execute("""SELECT r.data_relatorio,r.data_importacao,i.descricao,i.varejo,i.quantidade,i.unidade,i.atacado
                              FROM itens_relatorio i JOIN relatorios r ON r.id=i.relatorio_id
                              WHERE i.codigo=? ORDER BY r.id DESC LIMIT 100""",(code,)).fetchall()

def ignored_products():
    with connect_db() as con:
        return con.execute("SELECT codigo,ultimo_nome FROM produtos WHERE ignorado=1 ORDER BY ultimo_nome").fetchall()

def reports_history():
    with connect_db() as con:
        return con.execute("SELECT * FROM relatorios ORDER BY id DESC LIMIT 100").fetchall()

def find_powershell():
    for c in [shutil.which("powershell"),r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"]:
        if c and Path(c).exists(): return c
    raise RuntimeError("Windows PowerShell não foi encontrado.")

def merge_pdfs(files,output):
    writer=PdfWriter()
    for f in files:
        r=PdfReader(str(f))
        for p in r.pages: writer.add_page(p)
    with open(output,"wb") as h: writer.write(h)

def job_payload(p):
    unit=p["unidade"]
    q=p["quantidade"]
    if unit=="KG":
        q1=f"{q} KG SAI A:"
        q2=f"NA COMPRA A PARTIR DE {q} KG O KG SAI POR APENAS:"
    elif unit=="À LATA":
        q1=f"{q} LATAS SAEM A:"
        q2=f"NA COMPRA A PARTIR DE {q} LATAS, O PREÇO À LATA SAI POR APENAS:"
    elif unit=="À GARRAFA":
        q1=f"{q} GARRAFAS SAEM A:"
        q2=f"NA COMPRA A PARTIR DE {q} GARRAFAS, O PREÇO À GARRAFA SAI POR APENAS:"
    else:
        q1=f"{q} UN SAI A:"
        q2=f"NA COMPRA A PARTIR DE {q} A UNIDADE SAI POR APENAS:"
    return {
        "nome":p["nome"],"varejo":p["varejo"],"atacado":p["atacado"],"total":p["total"],
        "quantidade_texto":q1,"quantidade_2_texto":q2,"chave":p["cartaz_chave"]
    }


def _terminate_engine_process(proc, ppt_pid=None):
    """Encerra apenas o PowerShell e a instância de PowerPoint criada por esta geração."""
    try:
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=1.5)
            except Exception:
                try: proc.kill()
                except Exception: pass
    except Exception:
        pass
    if ppt_pid and os.name == "nt":
        try:
            subprocess.run(
                ["taskkill","/PID",str(int(ppt_pid)),"/T","/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0),
                timeout=4,
            )
        except Exception:
            pass

def run_engine(posters,output,progress=None,cancel_event=None,watchdog_seconds=180):
    if not MODEL.exists(): raise RuntimeError("Modelo ATACADO.pptx não encontrado.")
    if not ENGINE.exists(): raise RuntimeError("AtacadoEngine.ps1 não encontrado.")
    with tempfile.TemporaryDirectory(prefix="sr_atacado_") as td:
        td=Path(td); jobs=td/"jobs.json"; pdfdir=td/"pdfs"; pdfdir.mkdir()
        jobs.write_text(json.dumps([job_payload(x) for x in posters],ensure_ascii=False),encoding="utf-8")
        cmd=[find_powershell(),"-NoProfile","-ExecutionPolicy","Bypass","-File",str(ENGINE),
             "-JobsJson",str(jobs),"-OutputDir",str(pdfdir),"-Model",str(MODEL)]
        proc=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,
                              encoding="utf-8",errors="replace",
                              creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        q=queue.Queue()
        def reader():
            try:
                for line in proc.stdout: q.put(line.rstrip())
            finally: q.put(None)
        threading.Thread(target=reader,daemon=True).start()
        log=[]; done=0; failed=[]; success_keys=[]; ok_pdfs=[]; all_done_at=None; batch_done_at=None; ppt_pid=None; forced_after_success=False; last_activity=time.time(); stream_closed=False
        while True:
            if cancel_event and cancel_event.is_set():
                _terminate_engine_process(proc,ppt_pid)
                raise RuntimeError("Geração cancelada pelo usuário.")
            try:
                line=q.get(timeout=0.25)
                if line is None:
                    stream_closed=True
                else:
                    last_activity=time.time(); log.append(line)
                    if line.startswith("PPTPID|"):
                        try: ppt_pid=int(line.split("|",1)[1].strip())
                        except Exception: ppt_pid=None
                    elif line.startswith("BATCH_DONE|"):
                        batch_done_at=time.time()
                        if progress:
                            progress(len(posters),len(posters),"PDF criado • finalizando PowerPoint...")
                    elif line.startswith("ENGINE_DONE"):
                        pass
                    elif line.startswith("OK|"):
                        done+=1
                        parts=line.split("|",2)
                        try:
                            ok_idx=int(parts[1])-1 if len(parts)>=2 else -1
                        except Exception:
                            ok_idx=-1
                        if 0 <= ok_idx < len(posters):
                            key=str(posters[ok_idx].get("cartaz_chave","")).strip()
                            if key and key not in success_keys:
                                success_keys.append(key)
                        if len(parts)>=3:
                            try:
                                _p=Path(parts[2].strip())
                                if _p.exists(): ok_pdfs.append(_p)
                            except Exception: pass
                        if done>=len(posters) and all_done_at is None: all_done_at=time.time()
                        if progress:
                            idx=min(done-1,len(posters)-1)
                            progress(done,len(posters),f"Gerando {done} de {len(posters)} • {posters[idx]['nome']}")
                    elif line.startswith("ERR|"):
                        parts=line.split("|",2)
                        try: idx=int(parts[1])-1
                        except Exception: idx=-1
                        msg=parts[2] if len(parts)>2 else "Erro não identificado."
                        failed.append({
                            "nome": posters[idx]["nome"] if 0 <= idx < len(posters) else "",
                            "message": msg
                        })
            except queue.Empty:
                pass
            if proc.poll() is not None and stream_closed: break
            # O manifesto já foi escrito: o trabalho acabou. Se o Office prender no Quit,
            # encerra somente a instância criada pelo SR Studio.
            if batch_done_at is not None and proc.poll() is None and time.time()-batch_done_at>1.5:
                forced_after_success=True
                _terminate_engine_process(proc,ppt_pid)
                break
            # Fallback: todos os PDFs foram confirmados mas o script nem chegou ao manifesto.
            if all_done_at is not None and proc.poll() is None and time.time()-all_done_at>4:
                forced_after_success=True
                _terminate_engine_process(proc,ppt_pid)
                break
            if time.time()-last_activity>watchdog_seconds:
                _terminate_engine_process(proc,ppt_pid)
                raise RuntimeError("O PowerPoint demorou mais que o esperado e foi encerrado com segurança.")
        try: code=proc.wait(timeout=3)
        except Exception: code=proc.poll() if proc.poll() is not None else 1
        manifest=pdfdir/"manifest.txt"
        pdfs=[]
        if manifest.exists():
            pdfs=[Path(x.strip()) for x in manifest.read_text(encoding="utf-8-sig").splitlines() if x.strip() and Path(x.strip()).exists()]
        if len(pdfs)<max(1,done):
            seen=set(); pdfs=[]
            for _p in ok_pdfs:
                key=str(_p).lower()
                if _p.exists() and key not in seen:
                    seen.add(key);pdfs.append(_p)
        if forced_after_success and done>=len(posters) and len(pdfs)>=done: code=0
        if code!=0 and not pdfs:
            raise RuntimeError("O motor do Atacado encontrou um erro:\n\n"+"\n".join(log[-30:]))
        # O motor continua após falhas individuais. Se ao menos um PDF saiu, preserva o trabalho.
        if not pdfs:
            details="\n".join(f"• {x['nome']}: {x['message']}" for x in failed[:12])
            raise RuntimeError("Nenhum cartaz do Atacado foi gerado." + ("\n\n"+details if details else ""))
        merge_pdfs(pdfs,output)
        return {"success":len(pdfs),"failed":failed,"success_keys":success_keys}

def generate_preview(poster):
    if not PREVIEW_ENGINE.exists(): raise RuntimeError("AtacadoPreview.ps1 não encontrado.")
    with tempfile.TemporaryDirectory(prefix="sr_atacado_preview_") as td:
        td=Path(td); j=td/"job.json"; out=td/"preview.png"
        j.write_text(json.dumps(job_payload(poster),ensure_ascii=False),encoding="utf-8")
        cmd=[find_powershell(),"-NoProfile","-ExecutionPolicy","Bypass","-File",str(PREVIEW_ENGINE),
             "-JobJson",str(j),"-OutputPng",str(out),"-Model",str(MODEL)]
        p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,
                         encoding="utf-8",errors="replace",
                         creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        if p.returncode!=0 or not out.exists():
            raise RuntimeError((p.stdout or "Falha ao gerar prévia.")[-2500:])
        stable=LOCAL_DATA/"preview_atacado.png"
        shutil.copy2(out,stable)
        return stable

class AtacadoReviewWindow(tk.Toplevel):
    def __init__(self,master,panel,analysis):
        super().__init__(master);self.panel=panel;self.analysis=analysis;self.posters=analysis["posters"];self.app=panel.app
        self.title("SR Studio - Revisão Atacado");self.configure(bg=APP_BG);self.minsize(920,600);center_toplevel(self,self.app,1280,760)
        self.search=tk.StringVar();self.filter=tk.StringVar(value="TODOS");self.density=tk.StringVar(value="Confortável");self.view=tk.StringVar(value="Tabela")
        self.counter=tk.StringVar();self.undo_stack=[];self.redo_stack=[];self.thumb_dir=LOCAL_DATA/"thumb_cache_atacado";self.thumb_dir.mkdir(parents=True,exist_ok=True);self._images=[];self._token=0;self._thumb_queue=queue.Queue();self._thumb_worker_running=False
        self.build();self.refresh();self.bind("<Control-z>",lambda e:self.undo());self.bind("<Control-y>",lambda e:self.redo());self.bind("<Control-f>",lambda e:self.search_entry.focus_set())
    def build(self):
        top=tk.Frame(self,bg=CARD,height=66,highlightbackground=LINE,highlightthickness=1);top.pack(fill="x");top.pack_propagate(False)
        tk.Label(top,text="Revisão do Atacado",bg=CARD,fg=TEXT,font=("Segoe UI",17,"bold")).pack(side="left",padx=20)
        tk.Label(top,textvariable=self.counter,bg=CARD,fg=BLUE2,font=("Segoe UI",9,"bold")).pack(side="right",padx=20)
        ctl=tk.Frame(self,bg=APP_BG);ctl.pack(fill="x",padx=18,pady=(10,7))
        tk.Label(ctl,text="Pesquisar",bg=APP_BG,fg=TEXT,font=("Segoe UI",8,"bold")).pack(side="left")
        self.search_entry=tk.Entry(ctl,textvariable=self.search,width=26,bg=CARD,fg=TEXT,insertbackground=TEXT,relief="flat");self.search_entry.pack(side="left",padx=(5,9),ipady=5);self.search_entry.bind("<KeyRelease>",lambda e:self.refresh_current())
        f=ttk.Combobox(ctl,textvariable=self.filter,state="readonly",width=19,values=["TODOS","NOVOS","ALTERADOS","NOVOS + ALTERADOS","GERADOS","SEM ALTERAÇÃO","AGRUPADOS","COM ALERTA","EDITADOS"]);f.pack(side="left");f.bind("<<ComboboxSelected>>",lambda e:self.refresh_current())
        tk.Label(ctl,text="Densidade",bg=APP_BG,fg=MUTED,font=("Segoe UI",8)).pack(side="right",padx=(8,4))
        d=ttk.Combobox(ctl,textvariable=self.density,state="readonly",values=["Confortável","Compacto"],width=12);d.pack(side="right");d.bind("<<ComboboxSelected>>",lambda e:self.apply_density())
        self.view_btn=tk.Button(ctl,text="GALERIA",command=self.toggle_view,bg=LIGHT_BLUE,fg=LIGHT_BLUE_TXT,relief="flat",font=("Segoe UI",8,"bold"),padx=10,pady=6);self.view_btn.pack(side="right",padx=6)
        quick=tk.Frame(self,bg=APP_BG);quick.pack(fill="x",padx=18,pady=(0,7))
        tk.Button(quick,text="↶ DESFAZER",command=self.undo,bg=CARD,fg=TEXT,relief="flat",font=("Segoe UI",8,"bold"),padx=10,pady=5).pack(side="left")
        tk.Button(quick,text="↷ REFAZER",command=self.redo,bg=CARD,fg=TEXT,relief="flat",font=("Segoe UI",8,"bold"),padx=10,pady=5).pack(side="left",padx=5)
        tk.Label(quick,text="Duplo clique para editar • botão direito para ações",bg=APP_BG,fg=MUTED,font=("Segoe UI",8)).pack(side="left",padx=10)
        tk.Button(quick,text="SELECIONAR VISÍVEIS",command=lambda:self.set_visible(True),bg=LIGHT_BLUE,fg=LIGHT_BLUE_TXT,relief="flat",font=("Segoe UI",8,"bold"),padx=9,pady=5).pack(side="right")
        tk.Button(quick,text="DESMARCAR VISÍVEIS",command=lambda:self.set_visible(False),bg=RED,fg=RED_TXT,relief="flat",font=("Segoe UI",8,"bold"),padx=9,pady=5).pack(side="right",padx=5)
        self.paned=tk.PanedWindow(self,orient="horizontal",bg=APP_BG,sashwidth=6);self.paned.pack(fill="both",expand=True,padx=18,pady=(0,9))
        self.left=tk.Frame(self.paned,bg=CARD,highlightbackground=LINE,highlightthickness=1);self.right=tk.Frame(self.paned,bg=CARD,highlightbackground=LINE,highlightthickness=1,width=315)
        self.paned.add(self.left,stretch="always",minsize=590);self.paned.add(self.right,stretch="never",minsize=285)
        self.build_table();self.build_details()
        bottom=tk.Frame(self,bg=CARD,height=58,highlightbackground=LINE,highlightthickness=1);bottom.pack(fill="x");bottom.pack_propagate(False)
        tk.Button(bottom,text="FECHAR REVISÃO",command=self.close,bg=BLUE,fg="white",relief="flat",font=("Segoe UI",9,"bold"),padx=18,pady=8).pack(side="right",padx=18,pady=9)
    def build_table(self):
        self.table_holder=tk.Frame(self.left,bg=CARD);self.table_holder.pack(fill="both",expand=True)
        cols=("sel","status","produto","varejo","qtd","unit","atacado","total","copies","atencao")
        self.tree=ttk.Treeview(self.table_holder,columns=cols,show="headings",selectmode="extended")
        heads={"sel":"✓","status":"Status","produto":"Produto/Grupo","varejo":"Varejo","qtd":"Qtd.","unit":"Unid.","atacado":"Atacado","total":"Total","copies":"Cópias","atencao":"Atenção"};widths={"sel":34,"status":105,"produto":300,"varejo":72,"qtd":65,"unit":55,"atacado":75,"total":78,"copies":55,"atencao":105}
        for c in cols:self.tree.heading(c,text=heads[c]);self.tree.column(c,width=widths[c],anchor="w" if c=="produto" else "center")
        ys=ttk.Scrollbar(self.table_holder,orient="vertical",command=self.tree.yview);xs=ttk.Scrollbar(self.table_holder,orient="horizontal",command=self.tree.xview);self.tree.configure(yscrollcommand=ys.set,xscrollcommand=xs.set)
        self.tree.grid(row=0,column=0,sticky="nsew");ys.grid(row=0,column=1,sticky="ns");xs.grid(row=1,column=0,sticky="ew");self.table_holder.grid_rowconfigure(0,weight=1);self.table_holder.grid_columnconfigure(0,weight=1)
        self.tree.tag_configure("new",background=LIGHT_BLUE);self.tree.tag_configure("changed",background=ORANGE);self.tree.tag_configure("alert",background=RED);self.tree.tag_configure("edited",background=PURPLE)
        self.tree.bind("<<TreeviewSelect>>",lambda e:self.details());self.tree.bind("<Double-1>",self.edit_cell);self.tree.bind("<Button-3>",self.context_menu);self.apply_density()
        self.gallery=tk.Frame(self.left,bg=CARD)
    def build_details(self):
        tk.Label(self.right,text="Detalhes",bg=CARD,fg=TEXT,font=("Segoe UI",12,"bold")).pack(anchor="w",padx=14,pady=(14,5))
        self.status_chip=tk.Label(self.right,text="—",bg=LIGHT_BLUE,fg=LIGHT_BLUE_TXT,font=("Segoe UI",8,"bold"),padx=8,pady=4);self.status_chip.pack(anchor="w",padx=14)
        self.detail=tk.Label(self.right,text="Selecione um cartaz.",bg=CARD,fg=TEXT,justify="left",anchor="nw",wraplength=285,font=("Segoe UI",9));self.detail.pack(fill="x",padx=14,pady=(8,6))
        tk.Label(self.right,text="Nível de atenção",bg=CARD,fg=MUTED,font=("Segoe UI",8,"bold")).pack(anchor="w",padx=14)
        self.attention=tk.Label(self.right,text="OK",bg=GREEN,fg=GREEN_TXT,font=("Segoe UI",8,"bold"),padx=8,pady=4);self.attention.pack(anchor="w",padx=14,pady=(3,3));add_tooltip(self.attention,"CRÍTICO exige correção; ATENÇÃO pede conferência; INFO indica edição manual; OK não possui alerta conhecido.")
        self.explain=tk.Label(self.right,text="Nenhum alerta.",bg=CARD,fg=MUTED,font=("Segoe UI",8),justify="left",wraplength=285);self.explain.pack(anchor="w",padx=14,pady=(3,8));add_tooltip(self.explain,"Explicação do alerta detectado pelo SR Studio.")
        self.preview_btn=tk.Button(self.right,text="PRÉVIA REAL",command=self.preview,bg=BLUE,fg="white",relief="flat",font=("Segoe UI",8,"bold"),pady=7);self.preview_btn.pack(fill="x",padx=14,pady=3)
        tk.Button(self.right,text="EDITAR NOME DO GRUPO",command=self.edit_group,bg=LIGHT_BLUE,fg=LIGHT_BLUE_TXT,relief="flat",font=("Segoe UI",8,"bold"),pady=7).pack(fill="x",padx=14,pady=3)
        tk.Button(self.right,text="NUNCA AGRUPAR",command=self.never_group,bg=ORANGE,fg=ORANGE_TXT,relief="flat",font=("Segoe UI",8,"bold"),pady=7).pack(fill="x",padx=14,pady=3)
        tk.Button(self.right,text="NÃO GERAR ESTE PRODUTO",command=self.ignore_selected,bg=RED,fg=RED_TXT,relief="flat",font=("Segoe UI",8,"bold"),pady=7).pack(fill="x",padx=14,pady=3)
        tk.Button(self.right,text="HISTÓRICO DO PRODUTO",command=self.show_product_history,bg=GREEN,fg=GREEN_TXT,relief="flat",font=("Segoe UI",8,"bold"),pady=7).pack(fill="x",padx=14,pady=(3,12))
    def visible(self):
        q=norm(self.search.get());f=self.filter.get();out=[]
        for p in self.posters:
            if q and q not in norm(p["nome"]) and not any(q in norm(c) for c in p["codigos"]):continue
            if f=="NOVOS" and p["status"]!="NOVO":continue
            if f=="ALTERADOS" and p["status"]!="ALTERADO":continue
            if f=="NOVOS + ALTERADOS" and p["status"] not in {"NOVO","ALTERADO"}:continue
            if f=="GERADOS" and p["status"]!="GERADO":continue
            if f=="SEM ALTERAÇÃO" and p["status"]!="SEM ALTERAÇÃO":continue
            if f=="AGRUPADOS" and not p["agrupado"]:continue
            if f=="COM ALERTA" and not p.get("alerta"):continue
            if f=="EDITADOS" and not p.get("manual_edit"):continue
            out.append(p)
        return out
    def attention_level(self,p):
        a=(p.get("alerta") or "").lower()
        if any(x in a for x in ["inválido","atacado ≥ varejo"]):return "CRÍTICO"
        if a:return "ATENÇÃO"
        if p.get("manual_edit"):return "INFO"
        return "OK"
    def refresh_current(self):self.refresh_gallery() if self.view.get()=="Galeria" else self.refresh()
    def refresh(self):
        if not hasattr(self,"tree"):return
        sel=set(self.tree.selection());self.tree.delete(*self.tree.get_children())
        for p in self.visible():
            att=self.attention_level(p);tag="edited" if p.get("manual_edit") else "alert" if att=="CRÍTICO" else "new" if p["status"]=="NOVO" else "changed" if p["status"]=="ALTERADO" else ""
            self.tree.insert("","end",iid=str(id(p)),tags=(tag,) if tag else (),values=("✓" if p.get("selected") else "—",p["status"],p["nome"],p["varejo"],p["quantidade"],p["unidade"],p["atacado"],p["total"],p.get("copies",1),att))
        keep=[x for x in sel if self.tree.exists(x)];
        if keep:self.tree.selection_set(keep)
        selected=sum(bool(p.get("selected")) for p in self.posters);edited=sum(bool(p.get("manual_edit")) for p in self.posters);self.counter.set(f"{selected} selecionados • {len(self.posters)} cartazes • {edited} editados");self.panel.refresh_summary()
    def apply_density(self):
        try:self.app.style.configure("Treeview",rowheight=24 if self.density.get()=="Compacto" else 31,font=("Segoe UI",8 if self.density.get()=="Compacto" else 9))
        except Exception:pass
    def selected(self):
        ids=set(self.tree.selection()) if self.view.get()=="Tabela" else set();return [p for p in self.posters if str(id(p)) in ids]
    def set_visible(self,val):
        for p in self.visible():p["selected"]=val
        self.refresh_current()
    def details(self):
        ps=self.selected();
        if not ps:return
        p=ps[0];codes=", ".join(p["codigos"][:12])+("..." if len(p["codigos"])>12 else "")
        txt=f"{p['nome']}\n\nVarejo: R$ {p['varejo']}\nQuantidade: {p['quantidade']} {p['unidade']}\nAtacado: R$ {p['atacado']}\nTotal: R$ {p['total']}\n\nCódigos: {codes or 'manual'}"
        if p.get("motivo"):txt+=f"\n\nAlteração: {p['motivo']}"
        if p.get("status")=="ALTERADO" and p.get("_previous"):
            prev=p["_previous"];changes=[]
            for f,l in [("varejo","Varejo"),("quantidade","Quantidade"),("unidade","Unidade"),("atacado","Atacado")]:
                a=str(prev.get(f,"") or "");b=str(p.get(f,"") or "")
                if a!=b:changes.append(f"{l}: {a} → {b}")
            if changes:txt+="\n\nANTES → AGORA\n"+"\n".join(changes)
        if p.get("manual_edit") and p.get("_original"):
            changes=[]
            for f,l in [("nome","Produto"),("varejo","Varejo"),("quantidade","Quantidade"),("unidade","Unidade"),("atacado","Atacado")]:
                a=str(p["_original"].get(f,"") or "");b=str(p.get(f,"") or "")
                if a!=b:changes.append(f"{l}: {a} → {b}")
            if changes:txt+="\n\nEDITADO MANUALMENTE\n"+"\n".join(changes)
        self.detail.config(text=txt)
        st=p["status"];self.status_chip.config(text=("GRUPO • " if p.get("agrupado") else "")+st,bg=YELLOW if p.get("agrupado") else LIGHT_BLUE,fg=YELLOW_TXT if p.get("agrupado") else LIGHT_BLUE_TXT)
        att=self.attention_level(p);styles={"CRÍTICO":(RED,RED_TXT),"ATENÇÃO":(ORANGE,ORANGE_TXT),"INFO":(LIGHT_BLUE,LIGHT_BLUE_TXT),"OK":(GREEN,GREEN_TXT)};bg,fg=styles[att];self.attention.config(text=att,bg=bg,fg=fg);self.explain.config(text=p.get("alerta") or ("Item alterado manualmente; confira antes de gerar." if p.get("manual_edit") else "Nenhum alerta detectado."))
    def edit_cell(self,event):
        iid=self.tree.identify_row(event.y);col=self.tree.identify_column(event.x);region=self.tree.identify("region",event.x,event.y)
        if not iid or region!="cell":return
        cols=("sel","status","produto","varejo","qtd","unit","atacado","total","copies","atencao");key=cols[int(col[1:])-1];p=next((x for x in self.posters if str(id(x))==iid),None)
        if not p:return
        if key=="sel":p["selected"]=not p.get("selected",True);self.refresh();return
        fmap={"produto":"nome","varejo":"varejo","qtd":"quantidade","unit":"unidade","atacado":"atacado","copies":"copies"}
        if key not in fmap:return
        field=fmap[key];bbox=self.tree.bbox(iid,col);old=str(p.get(field,"") or "");var=tk.StringVar(value=old)
        editor=ttk.Combobox(self.tree,textvariable=var,state="readonly",values=ATACADO_UNIT_OPTIONS) if field=="unidade" else tk.Entry(self.tree,textvariable=var,bg=CARD,fg=TEXT,insertbackground=TEXT,relief="solid",bd=1)
        x,y,w,h=bbox;editor.place(x=x,y=y,width=w,height=h);editor.focus_set();
        if isinstance(editor,tk.Entry):editor.select_range(0,"end")
        done={"v":False}
        def commit(_=None):
            if done["v"]:return
            done["v"]=True;new=var.get().strip();editor.destroy()
            if new!=old:self.apply_edit(p,field,new,True)
        editor.bind("<Return>",commit);editor.bind("<FocusOut>",commit);editor.bind("<Escape>",lambda e:editor.destroy())
    def apply_edit(self,p,field,value,record=True):
        old=p.get(field,"")
        if "_original" not in p:p["_original"]={x:p.get(x) for x in ["nome","varejo","quantidade","unidade","atacado","total"]}
        if record:self.undo_stack.append((id(p),field,old,value));self.redo_stack.clear()
        if field in {"varejo","atacado"}:value=money(value)
        if field=="copies":
            try:value=max(1,min(99,int(str(value).strip())))
            except Exception:value=1
        p[field]=value;p["manual_edit"]=True;p["status"]="ALTERADO";p["motivo"]="Edição manual"
        if field in {"quantidade","atacado"}:
            try:p["total"]=money((dec(p["quantidade"]) or Decimal("0"))*(dec(p["atacado"]) or Decimal("0")))
            except Exception:pass
        p["alerta"]=poster_alert(p);upsert_current_poster(self.analysis["report_id"],p)
        if p.get("agrupado") and field=="nome" and p.get("base_key"):update_group_name(p["base_key"],p["nome"],p.get("complemento","VARIEDADES"))
        self.refresh_current();self.details();
        try:self.app.toast.show("Alteração salva automaticamente.","ok",1600)
        except Exception:pass
    def undo(self):
        if not self.undo_stack:return
        pid,field,old,new=self.undo_stack.pop();p=next((x for x in self.posters if id(x)==pid),None)
        if p:self.redo_stack.append((pid,field,old,new));self.apply_edit(p,field,old,False)
    def redo(self):
        if not self.redo_stack:return
        pid,field,old,new=self.redo_stack.pop();p=next((x for x in self.posters if id(x)==pid),None)
        if p:self.undo_stack.append((pid,field,old,new));self.apply_edit(p,field,new,False)
    def context_menu(self,event):
        iid=self.tree.identify_row(event.y)
        if iid:self.tree.selection_set(iid);self.details()
        m=tk.Menu(self,tearoff=0);m.add_command(label="Prévia real",command=self.preview);m.add_command(label="Incluir / excluir",command=self.toggle_selected);m.add_separator();m.add_command(label="Nunca agrupar",command=self.never_group);m.add_command(label="Não gerar este produto",command=self.ignore_selected);m.add_command(label="Histórico do produto",command=self.show_product_history)
        try:m.tk_popup(event.x_root,event.y_root)
        finally:m.grab_release()
    def toggle_selected(self):
        ps=self.selected();
        if not ps:return
        v=not ps[0].get("selected",True)
        for p in ps:p["selected"]=v
        self.refresh()
    def toggle_view(self):
        if self.view.get()=="Tabela":self.view.set("Galeria");self.view_btn.config(text="TABELA");self.table_holder.pack_forget();self.gallery.pack(fill="both",expand=True);self.refresh_gallery()
        else:self.view.set("Tabela");self.view_btn.config(text="GALERIA");self.gallery.pack_forget();self.table_holder.pack(fill="both",expand=True);self.refresh()
    def thumb_path(self,p):return self.thumb_dir/(cache_key(p.get("nome"),p.get("varejo"),p.get("quantidade"),p.get("unidade"),p.get("atacado"),p.get("total"),file_signature(MODEL))+".png")
    def refresh_gallery(self):
        self._token+=1;token=self._token;self._images=[]
        for w in self.gallery.winfo_children():w.destroy()
        canvas=tk.Canvas(self.gallery,bg=CARD,highlightthickness=0);sb=ttk.Scrollbar(self.gallery,orient="vertical",command=canvas.yview);canvas.configure(yscrollcommand=sb.set);canvas.pack(side="left",fill="both",expand=True);sb.pack(side="right",fill="y")
        inner=tk.Frame(canvas,bg=CARD);win=canvas.create_window((0,0),window=inner,anchor="nw");inner.bind("<Configure>",lambda e:canvas.configure(scrollregion=canvas.bbox("all")));canvas.bind("<Configure>",lambda e:canvas.itemconfigure(win,width=e.width))
        for i,p in enumerate(self.visible()[:30]):
            card=tk.Frame(inner,bg=ROW_ALT,highlightbackground=LINE,highlightthickness=1,width=210,height=300);card.grid(row=i//3,column=i%3,sticky="nsew",padx=7,pady=7);card.grid_propagate(False);inner.grid_columnconfigure(i%3,weight=1)
            lab=tk.Label(card,text="Gerando miniatura...",bg=ROW_ALT,fg=MUTED,font=("Segoe UI",8),height=11);lab.pack(fill="both",expand=True,padx=8,pady=(8,3))
            tk.Label(card,text=p["status"],bg=ROW_ALT,fg=BLUE2,font=("Segoe UI",7,"bold")).pack(anchor="w",padx=8);tk.Label(card,text=p["nome"],bg=ROW_ALT,fg=TEXT,font=("Segoe UI",8,"bold"),wraplength=190,justify="left").pack(anchor="w",padx=8,pady=(2,8))
            lab.bind("<Button-1>",lambda e,p=p:self.select_gallery(p));self.load_thumb(p,lab,token)
    def load_thumb(self,p,label,token):
        path=self.thumb_path(p)
        def show(x):
            if token!=self._token or not label.winfo_exists():return
            try:img=tk.PhotoImage(file=str(x));factor=max(1,math.ceil(max(img.width()/180,img.height()/205)));img=img.subsample(factor,factor);self._images.append(img);label.config(image=img,text="",height=0)
            except Exception:label.config(text="Miniatura indisponível")
        if path.exists():show(path);return
        self._thumb_queue.put((p,label,token,path,show));self._ensure_thumb_worker()
    def _ensure_thumb_worker(self):
        if self._thumb_worker_running:return
        self._thumb_worker_running=True
        def worker():
            while True:
                try:p,label,token,path,show=self._thumb_queue.get_nowait()
                except queue.Empty:break
                try:raw=generate_preview(p);shutil.copy2(raw,path);self.after(0,lambda x=path,show=show:show(x))
                except Exception:self.after(0,lambda label=label:label.config(text="Prévia disponível no Windows") if label.winfo_exists() else None)
            self._thumb_worker_running=False
            if not self._thumb_queue.empty():self.after(0,self._ensure_thumb_worker)
        threading.Thread(target=worker,daemon=True).start()
    def select_gallery(self,p):
        self.toggle_view();iid=str(id(p));
        if self.tree.exists(iid):self.tree.selection_set(iid);self.tree.see(iid);self.details()
    def edit_group(self):
        ps=self.selected()
        if len(ps)!=1 or not ps[0]["agrupado"]:messagebox.showinfo("Atacado","Selecione um único grupo.");return
        p=ps[0];new=ask_string(self.app,"Nome do grupo","Nome que deve aparecer no cartaz:",p["nome"])
        if new and new.strip():self.apply_edit(p,"nome"," ".join(new.upper().split()),True)
    def never_group(self):
        ps=self.selected();
        if not ps:return
        codes=[c for p in ps for c in p["codigos"]];set_never_group(codes,True);raw={x["codigo"]:x for x in self.analysis["parsed"]["items"]};added=[]
        for grp in list(ps):
            if not grp.get("agrupado"):continue
            if grp in self.posters:self.posters.remove(grp)
            remove_current_poster(self.analysis["report_id"],grp["cartaz_chave"])
            for code in grp["codigos"]:
                it=raw.get(code)
                if not it:continue
                p={"cartaz_chave":"P:"+code,"nome":it["descricao"],"varejo":it["varejo"],"quantidade":it["quantidade"],"unidade":it["unidade"],"atacado":it["atacado"],"total":it["total"],"desconto":it.get("desconto",""),"codigos":[code],"agrupado":False,"complemento":"","base_key":"","selected":True,"copies":1,"status":"ALTERADO","motivo":"Desagrupado manualmente"};p["alerta"]=poster_alert(p);self.posters.append(p);upsert_current_poster(self.analysis["report_id"],p);added.append(p)
        self.refresh();messagebox.showinfo("Atacado",f"Regra salva. {len(added)} cartaz(es) individual(is) preparados.")
    def ignore_selected(self):
        ps=self.selected();
        if not ps:return
        if not messagebox.askyesno("Atacado","Ignorar permanentemente os códigos selecionados?"):return
        codes=[c for p in ps for c in p["codigos"]];set_ignored(codes,True)
        for p in list(ps):
            if p in self.posters:self.posters.remove(p);remove_current_poster(self.analysis["report_id"],p["cartaz_chave"])
        self.refresh()
    def show_product_history(self):
        ps=self.selected();
        if not ps:return
        code=ps[0]["codigos"][0] if ps[0]["codigos"] else "MANUAL";rows=history_for_code(code);w=tk.Toplevel(self);w.title("Histórico - "+code);w.configure(bg=CARD);center_toplevel(w,self.app,720,420)
        tk.Label(w,text=f"Histórico do código {code}",bg=CARD,fg=TEXT,font=("Segoe UI",13,"bold")).pack(anchor="w",padx=16,pady=(14,8));tree=ttk.Treeview(w,columns=("data","nome","varejo","qtd","atacado"),show="headings")
        for c,t,ww in [("data","Relatório",130),("nome","Produto",300),("varejo","Varejo",70),("qtd","Qtd.",70),("atacado","Atacado",70)]:tree.heading(c,text=t);tree.column(c,width=ww)
        tree.pack(fill="both",expand=True,padx=16,pady=(0,16))
        for r in rows:tree.insert("","end",values=(r["data_relatorio"] or r["data_importacao"],r["descricao"],r["varejo"],f"{r['quantidade']} {r['unidade']}",r["atacado"]))
    def preview(self):
        ps=self.selected();
        if len(ps)!=1:messagebox.showinfo("Atacado","Selecione um cartaz.");return
        p=ps[0];self.preview_btn.config(state="disabled",text="GERANDO...")
        def worker():
            try:png=generate_preview(p);self.after(0,lambda:self.show_preview(png))
            except Exception as e:
                msg=str(e)
                self.after(0,lambda msg=msg:messagebox.showerror("Prévia",msg))
            finally:self.after(0,lambda:self.preview_btn.config(state="normal",text="PRÉVIA REAL"))
        threading.Thread(target=worker,daemon=True).start()
    def show_preview(self,png):
        w=tk.Toplevel(self);w.title("Prévia Atacado");w.configure(bg=APP_BG);img=tk.PhotoImage(file=str(png));factor=max(1,math.ceil(max(img.width()/650,img.height()/720)));img=img.subsample(factor,factor);w._img=img;tk.Label(w,image=img,bg=APP_BG).pack(padx=12,pady=12);center_toplevel(w,self.app,max(420,img.width()+24),max(480,img.height()+24))
    def close(self):self.panel.refresh_summary();self.destroy()


class AtacadoPanel(tk.Frame):
    def __init__(self,master,app,reduced_animations=False):
        super().__init__(master,bg=APP_BG)
        self.app=app; self.analysis=None; self.busy=False; self.cancel_event=threading.Event()
        self.reduced_animations=reduced_animations
        self.mode=tk.StringVar(value="NOVOS + ALTERADOS")
        self.status=tk.StringVar(value="Importe o relatório 782 do CISS para começar.")
        self.build()
    def build(self):
        # Área rolável para funcionar também em janela menor.
        canvas=tk.Canvas(self,bg=APP_BG,highlightthickness=0)
        sb=ttk.Scrollbar(self,orient="vertical",command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left",fill="both",expand=True); sb.pack(side="right",fill="y")
        outer=tk.Frame(canvas,bg=APP_BG)
        win=canvas.create_window((0,0),window=outer,anchor="nw")
        outer.bind("<Configure>",lambda e:canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",lambda e:canvas.itemconfigure(win,width=e.width))

        tk.Label(outer,text="Atacado",bg=APP_BG,fg=TEXT,font=("Segoe UI",20,"bold")).pack(anchor="w",padx=24,pady=(17,10))

        upload=tk.Frame(outer,bg=CARD,highlightbackground=LINE,highlightthickness=1)
        upload.pack(fill="x",padx=24)
        row=tk.Frame(upload,bg=CARD);row.pack(fill="x",padx=18,pady=15)
        tk.Label(row,text="Relatório Atacado",bg=CARD,fg=TEXT,font=("Segoe UI",11,"bold")).pack(side="left")
        self.import_btn=tk.Button(row,text="IMPORTAR PDF",command=self.pick,bg=BLUE,fg="white",relief="flat",font=("Segoe UI",9,"bold"),padx=14,pady=8)
        self.import_btn.pack(side="right")
        self.file_label=tk.Label(upload,text="Nenhum relatório importado",bg=CARD,fg=MUTED,font=("Segoe UI",8),anchor="w")
        self.file_label.pack(fill="x",padx=18,pady=(0,8))

        atacado_clear_row=tk.Frame(upload,bg=CARD)
        atacado_clear_row.pack(fill="x",padx=18,pady=(0,13))
        self.clear_btn=tk.Button(
            atacado_clear_row,text="LIMPAR",command=self.clear_generation,
            bg=RED,fg=RED_TXT,activebackground=RED,activeforeground=RED_TXT,
            relief="flat",bd=0,font=("Segoe UI",8,"bold"),
            padx=14,pady=7,state="disabled"
        )
        self.clear_btn.pack(side="right")
        add_tooltip(
            self.clear_btn,
            "Remove o relatório carregado da tela. "
            "A memória, agrupamentos e histórico do Atacado permanecem salvos."
        )

        self.loading_card=tk.Frame(outer,bg=CARD,highlightbackground=LINE,highlightthickness=1)
        self.loading_title=tk.Label(self.loading_card,text="",bg=CARD,fg=TEXT,font=("Segoe UI",11,"bold"))
        self.loading_title.pack(anchor="w",padx=16,pady=(12,3))
        self.loading_stage=tk.StringVar(value="")
        stage_row=tk.Frame(self.loading_card,bg=CARD);stage_row.pack(fill="x",padx=16)
        tk.Label(stage_row,textvariable=self.loading_stage,bg=CARD,fg=MUTED,font=("Segoe UI",8),anchor="w").pack(side="left",fill="x",expand=True)
        self.loading_percent=tk.StringVar(value="0%")
        tk.Label(stage_row,textvariable=self.loading_percent,bg=CARD,fg=BLUE2,font=("Segoe UI",8,"bold")).pack(side="right")
        self.loading_progress=ttk.Progressbar(self.loading_card,maximum=100,style="SR.Horizontal.TProgressbar")
        self.loading_progress.pack(fill="x",padx=16,pady=(8,4))
        self.loading_elapsed=tk.StringVar(value="")
        tk.Label(self.loading_card,textvariable=self.loading_elapsed,bg=CARD,fg=BLUE2,font=("Segoe UI",8,"bold"),anchor="w").pack(fill="x",padx=16,pady=(0,10))
        self._loading_started=None; self._loading_active=False

        stats=tk.Frame(outer,bg=APP_BG);self.stats_frame=stats;stats.pack(fill="x",padx=24,pady=10)
        self.stats={}
        defs=[("Produtos","posters",GREEN,GREEN_TXT),("Novos","new",LIGHT_BLUE,LIGHT_BLUE_TXT),
              ("Alterados","changed",ORANGE,ORANGE_TXT),("Removidos","removed",RED,RED_TXT),
              ("Agrupados","grouped",YELLOW,YELLOW_TXT),("Alertas","alerts",RED,RED_TXT)]
        for i,(title,key,bg,fg) in enumerate(defs):
            stats.grid_columnconfigure(i,weight=1)
            f=tk.Frame(stats,bg=bg);f.grid(row=0,column=i,sticky="ew",padx=(0 if i==0 else 2,0 if i==len(defs)-1 else 2))
            rowc=tk.Frame(f,bg=bg);rowc.pack(fill="x",padx=8,pady=6)
            v=tk.Label(rowc,text="0",bg=bg,fg=fg,font=("Segoe UI",12,"bold"));v.pack(side="left");self.stats[key]=v
            tk.Label(rowc,text=title,bg=bg,fg=fg,font=("Segoe UI",7,"bold")).pack(side="left",padx=(5,0),pady=(2,0))

        body=tk.Frame(outer,bg=APP_BG);body.pack(fill="x",padx=24,pady=(0,20))
        body.grid_columnconfigure(0,weight=3);body.grid_columnconfigure(1,weight=2)
        left=tk.Frame(body,bg=CARD,highlightbackground=LINE,highlightthickness=1);left.grid(row=0,column=0,sticky="nsew",padx=(0,8))
        right=tk.Frame(body,bg=CARD,highlightbackground=LINE,highlightthickness=1);right.grid(row=0,column=1,sticky="nsew",padx=(8,0))
        self.left=left;self.right=right
        def reflow(e):
            if e.width<850:
                left.grid_configure(row=0,column=0,padx=0)
                right.grid_configure(row=1,column=0,padx=0,pady=(12,0))
                body.grid_columnconfigure(1,weight=0)
            else:
                left.grid_configure(row=0,column=0,padx=(0,8),pady=0)
                right.grid_configure(row=0,column=1,padx=(8,0),pady=0)
                body.grid_columnconfigure(1,weight=2)
        body.bind("<Configure>",reflow)

        tk.Label(left,text="Resumo",bg=CARD,fg=TEXT,font=("Segoe UI",12,"bold")).pack(anchor="w",padx=16,pady=(15,5))
        self.summary=tk.Label(left,text="Nenhum relatório carregado.",bg=ROW_ALT,fg=MUTED,justify="left",anchor="w",wraplength=600,font=("Segoe UI",9),padx=12,pady=12)
        self.summary.pack(fill="x",padx=16,pady=(4,10))
        actions=tk.Frame(left,bg=CARD);actions.pack(fill="x",padx=16,pady=(0,14))
        self.review_btn=tk.Button(actions,text="REVISAR",command=self.review,state="disabled",bg=LIGHT_BLUE,fg=LIGHT_BLUE_TXT,relief="flat",font=("Segoe UI",8,"bold"),padx=10,pady=7)
        self.review_btn.pack(side="left",padx=(0,5))
        self.baseline_btn=tk.Button(actions,text="USAR COMO BASE",command=self.baseline,state="disabled",bg=GREEN,fg=GREEN_TXT,relief="flat",font=("Segoe UI",8,"bold"),padx=10,pady=7)
        self.baseline_btn.pack(side="left",padx=5)
        tk.Button(actions,text="HISTÓRICO",command=self.history,bg=ROW_ALT,fg=TEXT,relief="flat",font=("Segoe UI",8,"bold"),padx=10,pady=7).pack(side="left",padx=5)
        tk.Button(actions,text="IGNORADOS",command=self.manage_ignored,bg=ROW_ALT,fg=TEXT,relief="flat",font=("Segoe UI",8,"bold"),padx=10,pady=7).pack(side="left",padx=5)

        tk.Label(right,text="Geração",bg=CARD,fg=TEXT,font=("Segoe UI",12,"bold")).pack(anchor="w",padx=16,pady=(15,6))
        tk.Label(right,text="Modo",bg=CARD,fg=TEXT,font=("Segoe UI",8,"bold")).pack(anchor="w",padx=16)
        ttk.Combobox(right,textvariable=self.mode,state="readonly",values=["TODOS","SOMENTE ALTERADOS","NOVOS + ALTERADOS","SELEÇÃO MANUAL"]).pack(fill="x",padx=16,pady=(4,10))
        self.progress=ttk.Progressbar(right,maximum=100,style="SR.Horizontal.TProgressbar");self.progress.pack(fill="x",padx=16,pady=(5,4))
        tk.Label(right,textvariable=self.status,bg=CARD,fg=MUTED,font=("Segoe UI",8),wraplength=360,justify="left").pack(fill="x",padx=16,pady=(2,7))
        self.gen_btn=tk.Button(right,text="GERAR CARTAZES",command=self.generate,state="disabled",bg=BLUE,fg="white",relief="flat",font=("Segoe UI",9,"bold"),pady=9)
        self.gen_btn.pack(fill="x",padx=16,pady=(4,5))
        printrow=tk.Frame(right,bg=CARD);printrow.pack(fill="x",padx=16,pady=(0,5))
        self.print_btn=tk.Button(printrow,text="IMPRIMIR DIRETO",command=lambda:self.generate("print"),state="disabled",bg=GREEN,fg=GREEN_TXT,relief="flat",font=("Segoe UI",8,"bold"),pady=7)
        self.print_btn.pack(side="left",fill="x",expand=True,padx=(0,3))
        self.both_btn=tk.Button(printrow,text="SALVAR + IMPRIMIR",command=lambda:self.generate("both"),state="disabled",bg=ORANGE,fg=ORANGE_TXT,relief="flat",font=("Segoe UI",8,"bold"),pady=7)
        self.both_btn.pack(side="left",fill="x",expand=True,padx=(3,0))
        self.queue_btn=tk.Button(right,text="＋ FILA",command=self.add_to_queue,state="disabled",bg=PURPLE,fg=PURPLE_TXT,relief="flat",font=("Segoe UI",8,"bold"),pady=7)
        self.queue_btn.pack(fill="x",padx=16,pady=(0,5))
        self.cancel_btn=tk.Button(right,text="CANCELAR",command=self.cancel,state="disabled",bg=RED,fg=RED_TXT,relief="flat",font=("Segoe UI",8,"bold"),pady=7)
        self.cancel_btn.pack(fill="x",padx=16,pady=(0,14))
    def start_inline_loading(self,title):
        self._loading_started=time.time(); self._loading_active=True
        self.loading_title.config(text=title); self.loading_stage.set("Preparando..."); self.loading_progress["value"]=4
        if hasattr(self,"loading_percent"):self.loading_percent.set("4%")
        if not self.loading_card.winfo_ismapped(): self.loading_card.pack(fill="x",padx=24,pady=(10,0),before=self.stats_frame)
        self._tick_loading_time()
    def _tick_loading_time(self):
        if not self._loading_active or not self._loading_started:return
        elapsed=time.time()-self._loading_started
        self.loading_elapsed.set(f"{elapsed:0.1f}s decorridos")
        self.after(250 if not self.reduced_animations else 650,self._tick_loading_time)
    def update_inline_loading(self,a,b,text):
        self.loading_stage.set(text)
        value=(a/b*100 if b else min(92,self.loading_progress["value"]+4))
        self.loading_progress["value"]=value
        if hasattr(self,"loading_percent"):self.loading_percent.set(f"{int(value)}%")
    def stop_inline_loading(self,success=True):
        self._loading_active=False
        self.loading_progress["value"]=100 if success else 0
        if hasattr(self,"loading_percent"):self.loading_percent.set("100%" if success else "—")
        self.loading_elapsed.set("Concluído  ✓" if success else "Interrompido")
        self.after(800 if success else 1200,lambda:self.loading_card.pack_forget() if self.loading_card.winfo_exists() else None)

    def clear_generation(self, automatic=False):
        """Limpa o relatório atual da interface sem apagar a memória histórica do Atacado."""
        if self.busy:
            if not automatic:
                messagebox.showinfo("Limpar geração","Aguarde a tarefa atual terminar.")
            return False
        if self.analysis and not automatic:
            if not messagebox.askyesno(
                "Limpar geração",
                "Remover o relatório atual da tela?\n\n"
                "A memória, os agrupamentos e o histórico do Atacado continuarão salvos."
            ):
                return False

        self.analysis=None
        self.file_label.config(text="Nenhum relatório importado",fg=MUTED)
        for w in self.stats.values():
            try:w.config(text="0")
            except Exception:pass
        self.summary.config(
            text=("✓ Geração concluída • pronto para importar outro relatório"
                  if automatic else
                  "▦  Nenhum relatório carregado\nImporte o relatório 782 do CISS para comparar produtos, agrupamentos e alterações."),
            fg=GREEN_TXT if automatic else MUTED
        )
        self.review_btn.config(state="disabled")
        self.baseline_btn.config(state="disabled")
        self.gen_btn.config(state="disabled")
        self.print_btn.config(state="disabled")
        self.both_btn.config(state="disabled")
        if hasattr(self,"queue_btn"):self.queue_btn.config(state="disabled")
        self.clear_btn.config(state="disabled")
        self.progress["value"]=0
        self.status.set(
            "Geração concluída. Importe um novo relatório."
            if automatic else "Geração limpa. Importe um novo relatório."
        )
        return True

    def pick(self):
        if self.busy:return
        p=filedialog.askopenfilename(title="Selecionar relatório Atacarejo",filetypes=[("Relatório PDF","*.pdf")])
        if p:self.import_report(p)
    def import_report(self,p):
        self.busy=True;self.app.busy=True;self.import_btn.config(state="disabled",text="ANALISANDO...")
        self.start_inline_loading("Analisando relatório do Atacado")
        self.file_label.config(text=Path(p).name,fg=TEXT)
        def prog(a,b,t):self.after(0,lambda:self.update_inline_loading(a,b,t))
        def worker():
            try:
                a=analyze_and_store(p,prog)
                self.after(0,lambda:self.finish_import(a))
            except Exception as e:
                msg=str(e)
                self.after(0,lambda msg=msg:self.import_error(msg))
        threading.Thread(target=worker,daemon=True).start()
    def finish_import(self,a):
        self.stop_inline_loading(True);self.busy=False;self.app.busy=False;self.import_btn.config(state="normal",text="IMPORTAR PDF")
        self.analysis=a;self.review_btn.config(state="normal");self.gen_btn.config(state="normal");self.print_btn.config(state="normal");self.both_btn.config(state="normal");self.queue_btn.config(state="normal")
        self.clear_btn.config(state="normal")
        self.baseline_btn.config(state="normal" if a["first_report"] else "disabled")
        self.status.set("Relatório analisado. Revise as alterações antes de gerar.")
        try:self.app.last_update_text.set(f"Atacado: {a['parsed']['data_relatorio'] or 'agora'}")
        except Exception:pass
        self.refresh_summary()
        if a["duplicate"]:messagebox.showinfo("Atacado","Este relatório já estava na memória. O registro existente foi carregado.")
    def import_error(self,e):
        self.stop_inline_loading(False);self.busy=False;self.app.busy=False;self.import_btn.config(state="normal",text="IMPORTAR PDF")
        self.status.set(str(e));messagebox.showerror("Atacado",str(e))
    def refresh_summary(self):
        if not self.analysis:return
        c=self.analysis["counts"]
        # recalcula em memória após decisões da revisão
        posters=self.analysis["posters"]
        c["posters"]=len(posters);c["new"]=sum(p["status"]=="NOVO" for p in posters);c["changed"]=sum(p["status"]=="ALTERADO" for p in posters)
        c["same"]=sum(p["status"]=="SEM ALTERAÇÃO" for p in posters);c["grouped"]=sum(p["agrupado"] for p in posters);c["alerts"]=sum(bool(p.get("alerta")) for p in posters)
        for k,w in self.stats.items():w.config(text=str(c.get(k,0)))
        meta=self.analysis["parsed"]
        selected=sum(bool(p.get("selected")) for p in posters)
        self.summary.config(text=(
            f"{meta['empresa_codigo']} - {meta['empresa_nome']}  •  {meta['data_relatorio'] or 'data não identificada'}\n"
            f"{c['posters']} cartazes  •  {c['new']} novos  •  {c['changed']} alterados  •  {c['alerts']} alertas\n"
            f"{selected} selecionados  •  {c['grouped']} agrupados  •  {c['removed']} removidos"
        ),fg=RED_TXT if c["alerts"] else TEXT)
    def review(self):
        if self.analysis:AtacadoReviewWindow(self,self,self.analysis)
    def baseline(self):
        if not self.analysis:return
        if not messagebox.askyesno("Base inicial","Usar este relatório apenas como base inicial?\n\nNenhum cartaz ficará marcado como novo."):return
        set_baseline(self.analysis["report_id"])
        for p in self.analysis["posters"]:
            p["status"]="SEM ALTERAÇÃO";p["motivo"]="";p["selected"]=False
        self.analysis["first_report"]=False;self.baseline_btn.config(state="disabled");self.refresh_summary()
        messagebox.showinfo("Atacado","Base inicial salva. O próximo relatório será comparado com este.")
    def posters_to_generate(self):
        if not self.analysis:return []
        mode=self.mode.get(); ps=self.analysis["posters"]
        if mode=="TODOS":return list(ps)
        if mode=="SOMENTE ALTERADOS":return [p for p in ps if p["status"]=="ALTERADO"]
        if mode=="NOVOS + ALTERADOS":return [p for p in ps if p["status"] in {"NOVO","ALTERADO"}]
        return [p for p in ps if p.get("selected")]
    def add_to_queue(self):
        ps=self.posters_to_generate()
        if not ps:messagebox.showinfo("Fila","Não há cartazes para adicionar à fila.");return
        alerts=sum(bool(p.get("alerta")) for p in ps)
        if not messagebox.askyesno("Antes de adicionar à fila",f"{len(ps)} cartazes do Atacado serão adicionados à fila.\n\nAlertas para conferência: {alerts}\n\nContinuar?"):return
        self.app.enqueue_atacado(ps,self.analysis.get("report_id") if self.analysis else None,self.analysis.get("parsed",{}).get("data_relatorio","") if self.analysis else "")
        self.app.navigate("queue")

    def generate(self,action="save"):
        if self.busy:return
        ps=self.posters_to_generate()
        if not ps:messagebox.showinfo("Atacado","Não há cartazes para gerar neste modo.");return
        alerts=sum(bool(p.get("alerta")) for p in ps);groups=sum(bool(p.get("agrupado")) for p in ps)
        if not messagebox.askyesno("Antes de gerar",f"{len(ps)} cartazes do Atacado\n{groups} grupo(s) inteligente(s)\n{alerts} alerta(s)\n\nDeseja continuar?"):return
        if action in {"save","both"}:
            meta=self.analysis.get("parsed",{}) if self.analysis else {};base=dated_output_dir("Atacado",getattr(self.app,"ui_settings",{}));name=smart_pdf_name("Atacado","ATACADO",meta.get("data_relatorio",""))
            out=filedialog.asksaveasfilename(title="Salvar cartazes Atacado",defaultextension=".pdf",filetypes=[("PDF","*.pdf")],initialdir=str(base),initialfile=name)
            if not out:return
            out=unique_path(Path(out)) if Path(out).exists() else Path(out)
        else:
            out=Path(tempfile.gettempdir())/"SR_STUDIO_ATACADO_IMPRESSAO.pdf"
        self.busy=True;self.app.busy=True;self.cancel_event.clear();self.gen_btn.config(state="disabled",text="GERANDO...");self.print_btn.config(state="disabled");self.both_btn.config(state="disabled");self.cancel_btn.config(state="normal")
        self.start_inline_loading("Gerando cartazes do Atacado")
        started=time.time()
        def prog(a,b,t):
            self.after(0,lambda:(self.update_inline_loading(a,b,t),self.progress.config(value=(a/b*100 if b else 0)),self.status.set(t)))
        def worker():
            try:
                result=run_engine(ps,Path(out),prog,self.cancel_event)
                if action in {"print","both"}:
                    temp_copy=LOCAL_DATA/"temp"/"ATACADO_IMPRESSAO_COM_COPIAS.pdf";temp_copy.parent.mkdir(parents=True,exist_ok=True)
                    source=pdf_with_copies(out,ps,temp_copy)
                    self.app.print_document(source,"atacado") if hasattr(self.app,"print_document") else print_pdf(source)
                elapsed=time.time()-started
                self.after(0,lambda:self.finish_generate(out,result,elapsed,action))
            except Exception as e:
                msg=str(e)
                self.after(0,lambda msg=msg:self.gen_error(msg))
        threading.Thread(target=worker,daemon=True).start()
    def finish_generate(self,out,result,elapsed,action="save"):
        self.stop_inline_loading(True);self.busy=False;self.app.busy=False;self.gen_btn.config(state="normal",text="GERAR CARTAZES");self.print_btn.config(state="normal");self.both_btn.config(state="normal");self.cancel_btn.config(state="disabled");self.progress["value"]=100
        count=result.get("success",0);failed=result.get("failed",[])
        success_keys=set(result.get("success_keys") or [])
        if self.analysis and success_keys:
            mark_posters_generated(self.analysis.get("report_id"),success_keys)
            for p in self.analysis.get("posters",[]):
                if p.get("cartaz_chave") in success_keys:
                    p["status"]="GERADO"
                    p["motivo"]="Cartaz gerado"
                    p["selected"]=False
            self.refresh_summary()
            try:
                if hasattr(self.app,"refresh_home_if_visible"):
                    self.app.refresh_home_if_visible()
            except Exception:
                pass
        successful=[p for p in (self.analysis.get("posters",[]) if self.analysis else []) if p.get("cartaz_chave") in success_keys]
        if successful:record_product_jobs(successful,"Atacado",str(out))
        if count:record_reprint("Atacado",[out],count,"Atacado",{"report_id":self.analysis.get("report_id") if self.analysis else None})
        if failed:
            self.status.set(f"⚠ {count} gerados • {len(failed)} com erro • {elapsed:.1f}s")
            log=Path(out).with_name(Path(out).stem+"_ERROS.txt")
            lines=["SR STUDIO - ERROS ATACADO",datetime.now().strftime("%d/%m/%Y %H:%M:%S"),""]
            for x in failed: lines.append(f"• {x.get('nome','')}: {x.get('message','')}")
            log.write_text("\n".join(lines),encoding="utf-8")
            messagebox.showwarning("Atacado",f"{count} cartazes foram gerados.\n{len(failed)} tiveram erro.\n\nPDF: {out}\nLog: {log}")
        else:
            self.status.set(f"✓ {count} cartazes gerados em {elapsed:.1f}s.")
            if action=="print": messagebox.showinfo("Atacado",f"{count} cartazes enviados para a impressora padrão.")
            elif action=="both": messagebox.showinfo("Atacado",f"{count} cartazes salvos e enviados para impressão.\n\n{out}")
            else: messagebox.showinfo("Atacado",f"{count} cartazes gerados com sucesso.\n\n{out}")
            # O relatório continua no banco/histórico, mas sai da sessão atual.
            self.after(120,lambda:self.clear_generation(automatic=True))
    def gen_error(self,e):
        self.stop_inline_loading(False);self.busy=False;self.app.busy=False;self.gen_btn.config(state="normal",text="GERAR CARTAZES");self.print_btn.config(state="normal");self.both_btn.config(state="normal");self.cancel_btn.config(state="disabled")
        self.status.set(str(e))
        if "cancelada" not in str(e).lower():messagebox.showerror("Atacado",str(e))
    def cancel(self):
        self.cancel_event.set();self.status.set("Cancelando com segurança...")
    def history(self):
        rows=reports_history();w=tk.Toplevel(self);w.title("Histórico de Relatórios Atacado");w.configure(bg=CARD);center_toplevel(w,self.app,900,480)
        tk.Label(w,text="Histórico de Relatórios",bg=CARD,fg=TEXT,font=("Segoe UI",14,"bold")).pack(anchor="w",padx=16,pady=(14,8))
        tree=ttk.Treeview(w,columns=("data","arquivo","empresa","prod","novos","alt","rem","grp","alerta"),show="headings")
        defs=[("data","Relatório",130),("arquivo","Arquivo",210),("empresa","Empresa",180),("prod","Produtos",65),("novos","Novos",55),("alt","Alter.",55),("rem","Rem.",55),("grp","Grupos",55),("alerta","Alertas",55)]
        for c,t,ww in defs:tree.heading(c,text=t);tree.column(c,width=ww)
        tree.pack(fill="both",expand=True,padx=16,pady=(0,16))
        for r in rows:tree.insert("","end",values=(r["data_relatorio"],r["arquivo"],r["empresa_nome"],r["total_produtos"],r["novos"],r["alterados"],r["removidos"],r["agrupados"],r["alertas"]))
    def manage_ignored(self):
        rows=ignored_products();w=tk.Toplevel(self);w.title("Produtos ignorados");w.configure(bg=CARD);center_toplevel(w,self.app,650,430)
        tk.Label(w,text="Produtos ignorados permanentemente",bg=CARD,fg=TEXT,font=("Segoe UI",13,"bold")).pack(anchor="w",padx=16,pady=(14,8))
        tree=ttk.Treeview(w,columns=("codigo","nome"),show="headings",selectmode="extended");tree.heading("codigo",text="Código");tree.heading("nome",text="Produto");tree.column("codigo",width=100);tree.column("nome",width=470)
        tree.pack(fill="both",expand=True,padx=16)
        for r in rows:tree.insert("","end",iid=r["codigo"],values=(r["codigo"],r["ultimo_nome"]))
        def reactivate():
            ids=list(tree.selection())
            if not ids:return
            set_ignored(ids,False)
            for x in ids:
                if tree.exists(x):tree.delete(x)
            messagebox.showinfo("Atacado","Produtos reativados. Eles voltarão a aparecer na próxima importação.")
        tk.Button(w,text="REATIVAR SELECIONADOS",command=reactivate,bg=GREEN,fg=GREEN_TXT,relief="flat",font=("Segoe UI",8,"bold"),padx=12,pady=7).pack(anchor="e",padx=16,pady=12)
