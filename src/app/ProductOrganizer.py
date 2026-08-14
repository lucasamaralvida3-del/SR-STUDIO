# -*- coding: utf-8 -*-
"""Organizador inteligente do Banco de Produtos do SR Studio.

O histórico bruto nunca é apagado. Este módulo cria uma camada derivada de:
- produtos únicos;
- famílias comerciais;
- variações;
- possíveis duplicidades;
- decisões aprendidas do usuário.
"""
import re, json, sqlite3, hashlib, unicodedata, threading
from pathlib import Path
from datetime import datetime
from collections import Counter, defaultdict
from difflib import SequenceMatcher
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

from SRStudio21 import PRODUCT_DB, norm, normalize_product_name, apply_learned_correction
from ProductImages import ProductImageManager, get_image_info, get_category, set_category, guess_category
from ui_v2 import add_tooltip

FAMILY_TYPES=("SABORES","FRAGRÂNCIAS","TIPOS","TAMANHOS","CORES","VARIEDADES")

# Palavras pouco úteis para construir assinatura de produto.
STOPWORDS={
    "DE","DA","DO","DAS","DOS","COM","SEM","PARA","E","EM","A","O","AS","OS",
    "UN","UND","UNID","UNIDADE","CX","PCT","PT","BDJ","PET","LT","LATA","GARRAFA"
}

MEASURE_RE=re.compile(r"^\d+(?:[.,]\d+)?(?:ML|MG|KG|G|L)$",re.I)
PACK_RE=re.compile(r"^\d+X\d+(?:ML|MG|KG|G|L)?$",re.I)


def _conn():
    con=sqlite3.connect(PRODUCT_DB)
    con.row_factory=sqlite3.Row
    return con


def _now():return datetime.now().isoformat(timespec="seconds")


# Cache em memória aquecido na inicialização. Evita reler milhares de linhas do SQLite
# toda vez que o Banco de Produtos é aberto ou filtrado.
_CATALOG_CACHE=None
_FAMILY_CACHE=None
_DUP_CACHE=None
_COUNTS_CACHE=None
_CACHE_LOCK=threading.RLock()

def invalidate_catalog_cache():
    global _CATALOG_CACHE,_FAMILY_CACHE,_DUP_CACHE,_COUNTS_CACHE
    with _CACHE_LOCK:
        _CATALOG_CACHE=None;_FAMILY_CACHE=None;_DUP_CACHE=None;_COUNTS_CACHE=None

def preload_product_catalog(force=False):
    global _CATALOG_CACHE,_FAMILY_CACHE,_DUP_CACHE,_COUNTS_CACHE
    with _CACHE_LOCK:
        if _CATALOG_CACHE is not None and not force:
            return len(_CATALOG_CACHE)
        ensure_schema()
        with _conn() as con:
            products=[dict(x) for x in con.execute("SELECT * FROM catalog_products ORDER BY canonical_name COLLATE NOCASE").fetchall()]
            families=[dict(x) for x in con.execute("SELECT * FROM catalog_families ORDER BY CASE decision WHEN 'REVISAR' THEN 0 WHEN 'AUTO' THEN 1 ELSE 2 END,canonical_name COLLATE NOCASE").fetchall()]
            dups=[dict(x) for x in con.execute("""SELECT d.*,a.canonical_name left_name,a.codigo left_code,b.canonical_name right_name,b.codigo right_code
                     FROM catalog_duplicates d JOIN catalog_products a ON a.identity_key=d.left_key JOIN catalog_products b ON b.identity_key=d.right_key
                     WHERE d.status='REVISAR' ORDER BY d.confidence DESC""").fetchall()]
            raw=con.execute("SELECT COUNT(*) FROM history").fetchone()[0]
        fam_ok=[x for x in families if x.get('decision') in ('AUTO','CONFIRMADO')]
        review_fam=sum(1 for x in families if x.get('decision')=='REVISAR')
        _CATALOG_CACHE=products;_FAMILY_CACHE=families;_DUP_CACHE=dups
        _COUNTS_CACHE={
            'records':int(raw or 0),'unique':len(products),'families':len(fam_ok),
            'variants':sum(int(x.get('member_count') or 0) for x in fam_ok),
            'review':review_fam+len(dups),'duplicates':len(dups)
        }
        return len(products)


def _hash(text):return hashlib.sha1(str(text).encode("utf-8","ignore")).hexdigest()[:20]


def ensure_schema():
    with _conn() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS catalog_products(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            identity_key TEXT NOT NULL UNIQUE,
            codigo TEXT,
            canonical_name TEXT NOT NULL,
            canonical_norm TEXT NOT NULL,
            unidade TEXT,
            categoria TEXT,
            codigo_ciss TEXT,
            custo_reposicao TEXT,
            preco_varejo_atual TEXT,
            preco_atacado_atual TEXT,
            ciss_updated_at TEXT,
            occurrence_count INTEGER DEFAULT 0,
            first_seen TEXT,
            last_seen TEXT,
            family_key TEXT,
            variant_label TEXT,
            active INTEGER DEFAULT 1,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_catalog_code ON catalog_products(codigo);
        CREATE INDEX IF NOT EXISTS idx_catalog_name ON catalog_products(canonical_norm);
        CREATE INDEX IF NOT EXISTS idx_catalog_family ON catalog_products(family_key);

        CREATE TABLE IF NOT EXISTS catalog_families(
            family_key TEXT PRIMARY KEY,
            canonical_name TEXT NOT NULL,
            family_type TEXT NOT NULL DEFAULT 'VARIEDADES',
            confidence REAL DEFAULT 0,
            decision TEXT NOT NULL DEFAULT 'AUTO',
            member_count INTEGER DEFAULT 0,
            occurrence_count INTEGER DEFAULT 0,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS catalog_family_rules(
            family_key TEXT PRIMARY KEY,
            action TEXT NOT NULL,
            canonical_name TEXT,
            family_type TEXT,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS catalog_alias_rules(
            secondary_key TEXT PRIMARY KEY,
            primary_key TEXT NOT NULL,
            action TEXT NOT NULL DEFAULT 'MERGE',
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS catalog_duplicate_rules(
            pair_key TEXT PRIMARY KEY,
            action TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS catalog_duplicates(
            pair_key TEXT PRIMARY KEY,
            left_key TEXT NOT NULL,
            right_key TEXT NOT NULL,
            confidence REAL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'REVISAR',
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS catalog_meta(
            key TEXT PRIMARY KEY,
            value TEXT
        );
        """)
        cols=[r[1] for r in con.execute("PRAGMA table_info(catalog_products)").fetchall()]
        additions={
            "categoria":"TEXT",
            "codigo_ciss":"TEXT",
            "custo_reposicao":"TEXT",
            "preco_varejo_atual":"TEXT",
            "preco_atacado_atual":"TEXT",
            "ciss_updated_at":"TEXT",
        }
        for col,typ in additions.items():
            if col not in cols:
                try:con.execute(f"ALTER TABLE catalog_products ADD COLUMN {col} {typ}")
                except Exception:pass
ensure_schema()


def _tokens(name):
    n=norm(normalize_product_name(name))
    return [x for x in n.split() if x]


def _measure_tokens(tokens):
    return [x for x in tokens if MEASURE_RE.match(x) or PACK_RE.match(x)]


def _semantic_tokens(tokens):
    return [x for x in tokens if x not in STOPWORDS and not MEASURE_RE.match(x) and not PACK_RE.match(x) and not x.isdigit()]


def _family_type(name):
    n=norm(name)
    fragrance=("AMACIANTE","SABONETE","SHAMPOO","CONDICIONADOR","DESODORANTE","AROMATIZADOR","LIMPADOR","DESINFETANTE","DETERGENTE","SABAO")
    flavor=("ENERGETICO","REFRIGERANTE","SUCO","IOGURTE","BEBIDA","BISCOITO","BOLACHA","GELATINA","SORVETE","CHOCOLATE","ACHOCOLATADO","MACARRAO","TEMPERO","CHA","CERVEJA")
    size=("FRALDA","MEIA","CAMISETA","ROUPA","SHORT","CALCA","LUVA")
    color=("ESMALTE","COLORACAO","TONALIZANTE","TINTA")
    if any(x in n for x in fragrance):return "FRAGRÂNCIAS"
    if any(x in n for x in flavor):return "SABORES"
    if any(x in n for x in size):return "TAMANHOS"
    if any(x in n for x in color):return "CORES"
    return "VARIEDADES"


def _mode(values):
    vals=[str(x or "").strip() for x in values if str(x or "").strip()]
    if not vals:return ""
    return Counter(vals).most_common(1)[0][0]


def _canonical_name(rows):
    # Prefer learned correction and the most frequent visible form.
    names=[]
    for r in rows:
        raw=str(r["produto"] or "").strip()
        if raw:names.append(apply_learned_correction(raw))
    if not names:return "PRODUTO SEM NOME"
    counts=Counter(names)
    best=max(counts, key=lambda x:(counts[x], len(x)))
    return normalize_product_name(best)


def _identity_for_row(r):
    code=str(r["codigo"] or "").strip()
    if code:return "CODE:"+norm(code)
    corrected=apply_learned_correction(r["produto"] or "")
    return "NAME:"+norm(corrected)


def _resolve_alias(key,alias_map):
    seen=set()
    while key in alias_map and key not in seen:
        seen.add(key);key=alias_map[key]
    return key


def _family_bucket(item):
    toks=_tokens(item["canonical_name"])
    sem=_semantic_tokens(toks);measures=_measure_tokens(toks)
    if len(sem)<2:return None
    # Categoria + marca/linha + embalagem formam uma âncora estável.
    prefix=sem[:2]
    measure="+".join(measures[-2:]) if measures else ""
    return "|".join(prefix+[measure])


def _family_candidate(bucket_items):
    if len(bucket_items)<2:return None
    token_lists=[_tokens(x["canonical_name"]) for x in bucket_items]
    sem_lists=[_semantic_tokens(x) for x in token_lists]
    measures=[tuple(_measure_tokens(x)) for x in token_lists]
    # Não mistura embalagens/gramaturas diferentes quando ambas são conhecidas.
    nonempty={m for m in measures if m}
    if len(nonempty)>1:return None

    common=set(sem_lists[0])
    for x in sem_lists[1:]:common &= set(x)
    if len(common)<2:return None
    # Mantém a ordem da primeira descrição.
    base=[x for x in sem_lists[0] if x in common]
    meas=list(next(iter(nonempty))) if nonempty else []
    base_name=" ".join(base+meas)
    shortest=max(1,min(len(x) for x in sem_lists))
    ratio=len(common)/shortest
    # Quanto mais membros e tokens comuns, maior a confiança.
    confidence=min(0.99,0.52 + 0.12*min(3,len(common)-1) + 0.04*min(5,len(bucket_items)-2) + 0.16*ratio)
    return base_name,confidence


def _variant_label(product_name,family_name):
    pt=_tokens(product_name);ft=set(_tokens(family_name))
    diff=[x for x in pt if x not in ft and x not in STOPWORDS and not MEASURE_RE.match(x) and not PACK_RE.match(x)]
    return " ".join(diff).strip() or "PADRÃO"


def _duplicate_pair_key(a,b):return "|".join(sorted([a,b]))


def rebuild_catalog(progress=None):
    """Reconstrói somente a camada derivada. O histórico bruto permanece intacto."""
    ensure_schema()
    if progress:progress(2,"Lendo histórico bruto...")
    with _conn() as con:
        rows=con.execute("SELECT id,codigo,produto,unidade,gerado_em FROM history ORDER BY id").fetchall()
        alias_rows=con.execute("SELECT secondary_key,primary_key FROM catalog_alias_rules WHERE action='MERGE'").fetchall()
        alias_map={r["secondary_key"]:r["primary_key"] for r in alias_rows}
        family_rules={r["family_key"]:dict(r) for r in con.execute("SELECT * FROM catalog_family_rules").fetchall()}
        dup_rules={r["pair_key"]:r["action"] for r in con.execute("SELECT * FROM catalog_duplicate_rules").fetchall()}

    groups=defaultdict(list)
    for r in rows:
        key=_resolve_alias(_identity_for_row(r),alias_map)
        groups[key].append(r)

    if progress:progress(18,"Consolidando produtos repetidos...")
    products=[]
    for key,rs in groups.items():
        name=_canonical_name(rs)
        code=_mode([r["codigo"] for r in rs])
        unit=_mode([r["unidade"] for r in rs])
        dates=sorted([str(r["gerado_em"] or "") for r in rs if r["gerado_em"]])
        products.append({
            "identity_key":key,"codigo":code,"canonical_name":name,"canonical_norm":norm(name),
            "unidade":unit,"occurrence_count":len(rs),"first_seen":dates[0] if dates else "",
            "last_seen":dates[-1] if dates else "","family_key":"","variant_label":""
        })

    # Candidate families using stable bucket signatures.
    if progress:progress(38,"Identificando sabores, fragrâncias e variações...")
    buckets=defaultdict(list)
    for p in products:
        b=_family_bucket(p)
        if b:buckets[b].append(p)

    families=[];family_by_key={}
    for bucket,items in buckets.items():
        cand=_family_candidate(items)
        if not cand:continue
        base_name,confidence=cand
        family_key="FAM:"+_hash(bucket)
        rule=family_rules.get(family_key,{})
        action=str(rule.get("action") or "").upper()
        if action=="SEPARATE":continue
        # 2 itens ou confiança menor ficam marcados para revisão; não são perdidos.
        decision="CONFIRMADO" if action=="GROUP" else "AUTO" if confidence>=0.74 and len(items)>=3 else "REVISAR"
        canonical=normalize_product_name(rule.get("canonical_name") or base_name)
        ftype=str(rule.get("family_type") or _family_type(canonical)).upper()
        if ftype not in FAMILY_TYPES:ftype="VARIEDADES"
        fam={"family_key":family_key,"canonical_name":canonical,"family_type":ftype,
             "confidence":confidence,"decision":decision,"member_count":len(items),
             "occurrence_count":sum(x["occurrence_count"] for x in items)}
        families.append(fam);family_by_key[family_key]=fam
        for p in items:
            p["family_key"]=family_key
            p["variant_label"]=_variant_label(p["canonical_name"],canonical)

    # Possible exact-ish duplicates that are not already the same identity.
    if progress:progress(58,"Procurando possíveis duplicidades...")
    dup_candidates=[]
    dup_buckets=defaultdict(list)
    for p in products:
        toks=_tokens(p["canonical_name"]);sem=_semantic_tokens(toks);meas=_measure_tokens(toks)
        if not sem:continue
        key="|".join(sem[:2]+meas[-1:])
        dup_buckets[key].append(p)
    for _,items in dup_buckets.items():
        if len(items)<2:continue
        # Limit combinatorial work for huge generic buckets.
        items=sorted(items,key=lambda x:x["canonical_norm"])[:60]
        for i in range(len(items)):
            for j in range(i+1,len(items)):
                a,b=items[i],items[j]
                if a["identity_key"]==b["identity_key"]:continue
                # Family variants should not be suggested as exact duplicates unless names are nearly equal.
                sim=SequenceMatcher(None,a["canonical_norm"],b["canonical_norm"]).ratio()
                if sim<0.90:continue
                pair=_duplicate_pair_key(a["identity_key"],b["identity_key"])
                rule=dup_rules.get(pair)
                if rule=="SEPARATE":continue
                status="CONFIRMADO" if rule=="MERGE" else "REVISAR"
                dup_candidates.append((pair,a["identity_key"],b["identity_key"],sim,status))

    if progress:progress(76,"Atualizando Banco de Produtos...")
    with _conn() as con:
        con.execute("DELETE FROM catalog_products")
        con.execute("DELETE FROM catalog_families")
        con.execute("DELETE FROM catalog_duplicates")
        now=_now()
        con.executemany("""INSERT INTO catalog_products(identity_key,codigo,canonical_name,canonical_norm,unidade,occurrence_count,first_seen,last_seen,family_key,variant_label,active,updated_at)
                           VALUES(?,?,?,?,?,?,?,?,?,?,1,?)""",
                        [(p["identity_key"],p["codigo"],p["canonical_name"],p["canonical_norm"],p["unidade"],p["occurrence_count"],p["first_seen"],p["last_seen"],p["family_key"],p["variant_label"],now) for p in products])
        con.executemany("""INSERT INTO catalog_families(family_key,canonical_name,family_type,confidence,decision,member_count,occurrence_count,updated_at)
                           VALUES(?,?,?,?,?,?,?,?)""",
                        [(f["family_key"],f["canonical_name"],f["family_type"],f["confidence"],f["decision"],f["member_count"],f["occurrence_count"],now) for f in families])
        con.executemany("""INSERT INTO catalog_duplicates(pair_key,left_key,right_key,confidence,status,updated_at) VALUES(?,?,?,?,?,?)""",
                        [(x[0],x[1],x[2],x[3],x[4],now) for x in dup_candidates])
        con.execute("INSERT OR REPLACE INTO catalog_meta(key,value) VALUES('last_rebuild',?)",(now,))
        con.execute("INSERT OR REPLACE INTO catalog_meta(key,value) VALUES('raw_count',?)",(str(len(rows)),))
    # Reaplica os produtos/preços atuais do CISSPoder depois de cada reorganização.
    # Assim os vínculos Código CISS ↔ EAN não se perdem quando o catálogo derivado é reconstruído.
    try:
        from CISSProductSync import apply_ciss_to_catalog
        apply_ciss_to_catalog(progress if progress else None)
    except Exception:
        pass
    invalidate_catalog_cache()
    preload_product_catalog(force=True)
    # Mantém as telas que trabalham com cache sincronizadas após mesclagens/reorganização.
    try:
        from PromotionBuilder import invalidate_builder_catalog_cache, preload_builder_catalog
        invalidate_builder_catalog_cache();preload_builder_catalog(force=True)
    except Exception:pass
    try:
        from ManualModule import preload_sale_catalog
        preload_sale_catalog(force=True)
    except Exception:pass
    if progress:progress(100,"Banco organizado.")
    return catalog_counts()


def catalog_counts():
    global _COUNTS_CACHE
    if _COUNTS_CACHE is not None:
        return dict(_COUNTS_CACHE)
    preload_product_catalog()
    return dict(_COUNTS_CACHE or {})


def list_catalog(query="",filter_name="TODOS",limit=5000):
    preload_product_catalog()
    q=norm(query); raw=str(query or "").strip().upper(); f=str(filter_name or "TODOS").upper()
    out=[]
    for r in (_CATALOG_CACHE or []):
        if q:
            blob=" ".join(str(r.get(k) or "") for k in ("canonical_norm","codigo","codigo_ciss","variant_label")).upper()
            if q not in norm(blob) and raw not in blob: continue
        fam=str(r.get("family_key") or "")
        if f=="COM FAMÍLIA" and not fam: continue
        if f=="SEM FAMÍLIA" and fam: continue
        out.append(dict(r))
        if len(out)>=int(limit):break
    return out


def list_families(filter_name="TODAS",query=""):
    preload_product_catalog(); q=norm(query); f=str(filter_name or "TODAS").upper();out=[]
    for r in (_FAMILY_CACHE or []):
        if f=="REVISAR" and r.get("decision")!="REVISAR":continue
        if f=="CONFIRMADAS" and r.get("decision") not in ("AUTO","CONFIRMADO"):continue
        if q and q not in norm(r.get("canonical_name")):continue
        out.append(dict(r))
    return out


def family_members(family_key):
    preload_product_catalog()
    return [dict(x) for x in (_CATALOG_CACHE or []) if x.get("family_key")==family_key]


def list_duplicates(query=""):
    preload_product_catalog();q=norm(query);out=[]
    for r in (_DUP_CACHE or []):
        if q and q not in norm(" ".join(str(r.get(k) or "") for k in ("left_name","right_name","left_code","right_code"))):continue
        out.append(dict(r))
        if len(out)>=1000:break
    return out


def set_family_rule(family_key,action,canonical_name="",family_type="",rebuild=True):
    action=str(action).upper();
    if action not in {"GROUP","SEPARATE"}:raise RuntimeError("Decisão inválida.")
    with _conn() as con:
        con.execute("INSERT OR REPLACE INTO catalog_family_rules(family_key,action,canonical_name,family_type,updated_at) VALUES(?,?,?,?,?)",
                    (family_key,action,canonical_name,family_type,_now()))
    if rebuild:rebuild_catalog()


def clear_family_rule(family_key):
    with _conn() as con:con.execute("DELETE FROM catalog_family_rules WHERE family_key=?",(family_key,))
    rebuild_catalog()


def set_duplicate_rule(pair_key,left_key,right_key,action,rebuild=True):
    action=str(action).upper()
    if action not in {"MERGE","SEPARATE"}:raise RuntimeError("Decisão inválida.")
    with _conn() as con:
        con.execute("INSERT OR REPLACE INTO catalog_duplicate_rules(pair_key,action,updated_at) VALUES(?,?,?)",(pair_key,action,_now()))
        if action=="MERGE":
            left_ciss=str(left_key).startswith("CISS:")
            right_ciss=str(right_key).startswith("CISS:")
            # Caso especial: um registro veio do relatório 208 e o outro das planilhas.
            # O vínculo CISS passa a apontar para o produto comercial/EAN e o stub desaparece.
            if left_ciss ^ right_ciss:
                ciss_key=left_key if left_ciss else right_key
                primary=right_key if left_ciss else left_key
                ciss_code=str(ciss_key).split(":",1)[1]
                try:
                    con.execute("""UPDATE ciss_product_links SET identity_key=?,link_method='MANUAL_DUPLICATE',confirmed=1,confidence=1.0,updated_at=? WHERE ciss_code=?""",
                                (primary,_now(),ciss_code))
                except Exception:
                    pass
                con.execute("DELETE FROM catalog_products WHERE identity_key=?",(ciss_key,))
            else:
                # Duplicidade entre dois cadastros comerciais: regra de alias tradicional.
                l=con.execute("SELECT codigo,occurrence_count FROM catalog_products WHERE identity_key=?",(left_key,)).fetchone()
                r=con.execute("SELECT codigo,occurrence_count FROM catalog_products WHERE identity_key=?",(right_key,)).fetchone()
                primary,secondary=left_key,right_key
                if r and r["codigo"] and not (l and l["codigo"]):primary,secondary=right_key,left_key
                elif l and r and int(r["occurrence_count"] or 0)>int(l["occurrence_count"] or 0):primary,secondary=right_key,left_key
                con.execute("INSERT OR REPLACE INTO catalog_alias_rules(secondary_key,primary_key,action,updated_at) VALUES(?,?, 'MERGE',?)",(secondary,primary,_now()))
    invalidate_catalog_cache()
    if rebuild:rebuild_catalog()


def reset_organizer_decisions():
    with _conn() as con:
        con.execute("DELETE FROM catalog_family_rules");con.execute("DELETE FROM catalog_alias_rules");con.execute("DELETE FROM catalog_duplicate_rules")
    invalidate_catalog_cache()
    rebuild_catalog()


class BatchReviewWindow(tk.Toplevel):
    """Revisão sequencial dos itens selecionados no Banco de Produtos."""
    def __init__(self,parent,items):
        super().__init__(parent)
        self.parent=parent;self.app=parent.app;self.p=parent.p
        self.items=[(kind,dict(row)) for kind,row in items]
        self.index=0;self.changed=False
        self.summary={"group":0,"separate":0,"merge":0,"kept":0,"skip":0}
        self.title("Banco de Produtos • Revisar Todos")
        self.configure(bg=self.p["APP_BG"])
        self.geometry("700x560")
        self.minsize(620,500)
        self.transient(self.app)
        self.protocol("WM_DELETE_WINDOW",self.finish)
        self._center()
        self._build()
        self.render_current()

    def _center(self):
        try:
            self.update_idletasks()
            master=self.app
            x=master.winfo_rootx()+max(0,(master.winfo_width()-700)//2)
            y=master.winfo_rooty()+max(0,(master.winfo_height()-560)//2)
            self.geometry(f"700x560+{x}+{y}")
        except Exception:pass

    def _build(self):
        p=self.p
        head=tk.Frame(self,bg=p["APP_BG"]);head.pack(fill="x",padx=22,pady=(18,10))
        tk.Label(head,text="Revisar todos",bg=p["APP_BG"],fg=p["TEXT"],font=("Segoe UI",18,"bold")).pack(anchor="w")
        self.progress_text=tk.StringVar(value="")
        tk.Label(head,textvariable=self.progress_text,bg=p["APP_BG"],fg=p["MUTED"],font=("Segoe UI",9)).pack(anchor="w",pady=(2,0))
        self.progress=ttk.Progressbar(self,maximum=max(1,len(self.items)),style="SR.Horizontal.TProgressbar");self.progress.pack(fill="x",padx=22,pady=(0,12))

        card=tk.Frame(self,bg=p["CARD"],highlightbackground=p["LINE"],highlightthickness=1);card.pack(fill="both",expand=True,padx=22)
        self.kind_label=tk.Label(card,text="",bg=p["CARD"],fg=p["BLUE2"],font=("Segoe UI",8,"bold"));self.kind_label.pack(anchor="w",padx=18,pady=(16,2))
        self.title_label=tk.Label(card,text="",bg=p["CARD"],fg=p["TEXT"],font=("Segoe UI",14,"bold"),wraplength=610,justify="left");self.title_label.pack(anchor="w",padx=18,pady=(0,8))
        self.detail_label=tk.Label(card,text="",bg=p["ROW_ALT"],fg=p["TEXT"],font=("Segoe UI",9),justify="left",anchor="nw",wraplength=610,padx=13,pady=13)
        self.detail_label.pack(fill="both",expand=True,padx=18,pady=(0,10))
        self.actions=tk.Frame(card,bg=p["CARD"]);self.actions.pack(fill="x",padx=18,pady=(0,16))

        foot=tk.Frame(self,bg=p["APP_BG"]);foot.pack(fill="x",padx=22,pady=(10,18))
        tk.Button(foot,text="VOLTAR",command=self.previous,bg=p["ROW_ALT"],fg=p["TEXT"],relief="flat",font=("Segoe UI",8,"bold"),padx=14,pady=7).pack(side="left")
        tk.Button(foot,text="PULAR",command=self.skip,bg=p["ROW_ALT"],fg=p["TEXT"],relief="flat",font=("Segoe UI",8,"bold"),padx=14,pady=7).pack(side="left",padx=6)
        tk.Button(foot,text="ENCERRAR REVISÃO",command=self.finish,bg=p["RED"],fg=p["RED_TXT"],relief="flat",font=("Segoe UI",8,"bold"),padx=14,pady=7).pack(side="right")

    def current(self):
        return self.items[self.index] if 0<=self.index<len(self.items) else None

    def _clear_actions(self):
        for w in self.actions.winfo_children():w.destroy()

    def render_current(self):
        if not self.items or self.index>=len(self.items):
            self.finish();return
        p=self.p;kind,r=self.current();self._clear_actions()
        self.progress["value"]=self.index+1
        self.progress_text.set(f"Item {self.index+1} de {len(self.items)} • as decisões são salvas no Banco de Produtos")

        if kind=="FAMÍLIAS":
            members=family_members(r["family_key"])
            self.kind_label.config(text="FAMÍLIA / VARIAÇÕES")
            self.title_label.config(text=r["canonical_name"])
            lines=[f"Tipo: {r['family_type']}",f"Confiança: {r['confidence']*100:.0f}%",f"Produtos/variações: {len(members)}",f"Ocorrências: {r['occurrence_count']}",""]
            lines += [f"• {m['canonical_name']}  →  {m['variant_label']}" for m in members[:12]]
            if len(members)>12:lines.append(f"• +{len(members)-12} outros")
            self.detail_label.config(text="\n".join(lines))
            tk.Button(self.actions,text="CONFIRMAR AGRUPAMENTO",command=lambda:self.family_decision("GROUP"),bg=p["GREEN"],fg=p["GREEN_TXT"],relief="flat",font=("Segoe UI",9,"bold"),pady=8).pack(fill="x",pady=2)
            tk.Button(self.actions,text="MANTER SEPARADOS / NUNCA AGRUPAR",command=lambda:self.family_decision("SEPARATE"),bg=p["RED"],fg=p["RED_TXT"],relief="flat",font=("Segoe UI",9,"bold"),pady=8).pack(fill="x",pady=2)
            tk.Button(self.actions,text="EDITAR NOME E TIPO",command=self.edit_family_current,bg=p["LIGHT_BLUE"],fg=p["LIGHT_BLUE_TXT"],relief="flat",font=("Segoe UI",8,"bold"),pady=7).pack(fill="x",pady=2)

        elif kind=="DUPLICIDADES":
            self.kind_label.config(text="POSSÍVEL DUPLICIDADE")
            self.title_label.config(text=f"{r['left_name']}  ⇄  {r['right_name']}")
            self.detail_label.config(text=(f"Código/EAN 1: {r.get('left_code') or '—'}\nCódigo/EAN 2: {r.get('right_code') or '—'}\n\n"
                                           f"Semelhança: {r['confidence']*100:.0f}%\n\n"
                                           "Escolha se os dois registros representam o mesmo produto ou devem permanecer separados."))
            tk.Button(self.actions,text="É O MESMO PRODUTO",command=lambda:self.duplicate_decision("MERGE"),bg=p["GREEN"],fg=p["GREEN_TXT"],relief="flat",font=("Segoe UI",9,"bold"),pady=8).pack(fill="x",pady=2)
            tk.Button(self.actions,text="MANTER SEPARADOS / NUNCA MESCLAR",command=lambda:self.duplicate_decision("SEPARATE"),bg=p["RED"],fg=p["RED_TXT"],relief="flat",font=("Segoe UI",9,"bold"),pady=8).pack(fill="x",pady=2)

        else:
            self.kind_label.config(text="PRODUTO")
            self.title_label.config(text=r["canonical_name"])
            self.detail_label.config(text=(f"Código/EAN: {r['codigo'] or '—'}\nUnidade: {r['unidade'] or '—'}\n"
                                           f"Ocorrências históricas: {r['occurrence_count']}\nPrimeira aparição: {r['first_seen'] or '—'}\n"
                                           f"Última aparição: {r['last_seen'] or '—'}\nFamília: {r['family_key'] or 'Sem família'}\n"
                                           f"Variação: {r['variant_label'] or '—'}"))
            tk.Button(self.actions,text="VER HISTÓRICO DE PREÇOS",command=lambda:self.app.show_product_history_dialog(r["codigo"],r["canonical_name"]),bg=p["BLUE"],fg="white",relief="flat",font=("Segoe UI",8,"bold"),pady=8).pack(fill="x",pady=2)
            tk.Button(self.actions,text="REVISADO • PRÓXIMO",command=self.keep_product,bg=p["GREEN"],fg=p["GREEN_TXT"],relief="flat",font=("Segoe UI",9,"bold"),pady=8).pack(fill="x",pady=2)

    def advance(self):
        self.index+=1
        if self.index>=len(self.items):self.finish()
        else:self.render_current()

    def previous(self):
        if self.index>0:self.index-=1;self.render_current()

    def skip(self):
        self.summary["skip"]+=1;self.advance()

    def keep_product(self):
        self.summary["kept"]+=1;self.advance()

    def family_decision(self,action):
        kind,r=self.current()
        set_family_rule(r["family_key"],action,r["canonical_name"],r["family_type"],rebuild=False)
        self.changed=True
        if action=="GROUP":self.summary["group"]+=1
        else:self.summary["separate"]+=1
        self.advance()

    def edit_family_current(self):
        kind,r=self.current()
        name=simpledialog.askstring("Nome da família","Nome consolidado:",initialvalue=r["canonical_name"],parent=self)
        if not name:return
        t=simpledialog.askstring("Tipo da família",f"Tipo ({', '.join(FAMILY_TYPES)}):",initialvalue=r["family_type"],parent=self)
        t=str(t or r["family_type"]).upper().strip()
        if t not in FAMILY_TYPES:t="VARIEDADES"
        set_family_rule(r["family_key"],"GROUP",normalize_product_name(name),t,rebuild=False)
        self.changed=True;self.summary["group"]+=1;self.advance()

    def duplicate_decision(self,action):
        kind,r=self.current()
        set_duplicate_rule(r["pair_key"],r["left_key"],r["right_key"],action,rebuild=False)
        self.changed=True
        if action=="MERGE":self.summary["merge"]+=1
        else:self.summary["separate"]+=1
        self.advance()

    def finish(self):
        if not self.winfo_exists():return
        if self.changed:
            try:rebuild_catalog()
            except Exception as e:
                messagebox.showerror("Banco de Produtos",str(e),parent=self);return
        try:self.parent.refresh()
        except Exception:pass
        total=sum(self.summary.values())
        msg=(f"Revisão encerrada.\n\n"
             f"Agrupamentos confirmados: {self.summary['group']}\n"
             f"Mesclagens confirmadas: {self.summary['merge']}\n"
             f"Mantidos separados: {self.summary['separate']}\n"
             f"Produtos revisados: {self.summary['kept']}\n"
             f"Pulados: {self.summary['skip']}")
        try:self.destroy()
        except Exception:pass
        if total:messagebox.showinfo("Banco de Produtos",msg,parent=self.parent)


class ProductOrganizerPanel(tk.Frame):
    def __init__(self,parent,app,palette):
        super().__init__(parent,bg=palette["APP_BG"])
        self.app=app;self.p=palette;self.busy=False;self.search_var=tk.StringVar();self.filter_var=tk.StringVar(value="TODOS")
        self.view_var=tk.StringVar(value="PRODUTOS");self.status_var=tk.StringVar(value="Banco pronto.");self.progress_var=tk.DoubleVar(value=0)
        self.records={};self._build();self.ensure_built()

    def _build(self):
        p=self.p
        head=tk.Frame(self,bg=p["APP_BG"]);head.pack(fill="x",padx=24,pady=(16,8))
        hrow=tk.Frame(head,bg=p["APP_BG"]);hrow.pack(fill="x")
        tk.Label(hrow,text="Banco de Produtos",bg=p["APP_BG"],fg=p["TEXT"],font=("Segoe UI",20,"bold")).pack(side="left")
        tip=tk.Label(hrow,text="ⓘ",bg=p["APP_BG"],fg=p["BLUE2"],font=("Segoe UI",10,"bold"));tip.pack(side="left",padx=8)
        add_tooltip(tip,"Cadastros, EAN/CISS, imagens, famílias e histórico. A tabela mostra somente o essencial; os detalhes aparecem ao selecionar um produto.")

        # Indicadores compactos.
        stats=tk.Frame(self,bg=p["APP_BG"]);stats.pack(fill="x",padx=24,pady=(0,8));self.stats={}
        defs=[("unique","Produtos"),("families","Famílias"),("review","Revisar")]
        for i,(key,title) in enumerate(defs):
            stats.grid_columnconfigure(i,weight=1)
            c=tk.Frame(stats,bg=p["CARD"],highlightbackground=p["LINE"],highlightthickness=1);c.grid(row=0,column=i,sticky="ew",padx=(0 if i==0 else 4,0 if i==len(defs)-1 else 4))
            row=tk.Frame(c,bg=p["CARD"]);row.pack(fill="x",padx=10,pady=7)
            v=tk.Label(row,text="0",bg=p["CARD"],fg=p["TEXT"],font=("Segoe UI",13,"bold"));v.pack(side="left");self.stats[key]=v
            tk.Label(row,text=title,bg=p["CARD"],fg=p["MUTED"],font=("Segoe UI",7,"bold")).pack(side="left",padx=(6,0),pady=(3,0))
        # Contadores preservados para a lógica existente, sem ocupar a tela.
        self.stats["variants"]=tk.Label(self,text="0");self.stats["records"]=tk.Label(self,text="0")

        bar=tk.Frame(self,bg=p["CARD"],highlightbackground=p["LINE"],highlightthickness=1);bar.pack(fill="x",padx=24,pady=(0,9))
        self.search=tk.Entry(bar,textvariable=self.search_var,bg=p["ROW_ALT"],fg=p["TEXT"],insertbackground=p["TEXT"],relief="flat",font=("Segoe UI",9));self.search.pack(side="left",fill="x",expand=True,padx=(12,6),pady=9,ipady=5);self.search.bind("<KeyRelease>",lambda e:self.refresh())
        self.view=ttk.Combobox(bar,textvariable=self.view_var,state="readonly",values=["PRODUTOS","FAMÍLIAS","DUPLICIDADES"],width=15);self.view.pack(side="left",padx=4);self.view.bind("<<ComboboxSelected>>",lambda e:self.view_changed())
        self.filter=ttk.Combobox(bar,textvariable=self.filter_var,state="readonly",values=["TODOS","COM FAMÍLIA","SEM FAMÍLIA"],width=16);self.filter.pack(side="left",padx=4);self.filter.bind("<<ComboboxSelected>>",lambda e:self.refresh())
        self.review_all_btn=tk.Button(bar,text="REVISAR",command=self.review_selected,bg=p["ORANGE"],fg=p["ORANGE_TXT"],relief="flat",font=("Segoe UI",7,"bold"),padx=10,pady=7,state="disabled")
        self.review_all_btn.pack(side="right",padx=(4,12))
        tk.Button(bar,text="LOCALIZAR DUPLICADOS",command=self.find_duplicates,bg=p["PURPLE"],fg=p["PURPLE_TXT"],relief="flat",font=("Segoe UI",7,"bold"),padx=10,pady=7).pack(side="right",padx=4)
        tk.Button(bar,text="↻ ORGANIZAR",command=self.rebuild,bg=p["BLUE"],fg="white",relief="flat",font=("Segoe UI",7,"bold"),padx=10,pady=7).pack(side="right",padx=4)

        body=tk.Frame(self,bg=p["APP_BG"]);body.pack(fill="both",expand=True,padx=24);body.grid_columnconfigure(0,weight=3);body.grid_columnconfigure(1,weight=2);body.grid_rowconfigure(0,weight=1)
        left=tk.Frame(body,bg=p["CARD"],highlightbackground=p["LINE"],highlightthickness=1);left.grid(row=0,column=0,sticky="nsew",padx=(0,7))
        right=tk.Frame(body,bg=p["CARD"],highlightbackground=p["LINE"],highlightthickness=1);right.grid(row=0,column=1,sticky="nsew",padx=(7,0));self.detail_frame=right
        cols=("codigo","nome","unidade","varejo","status")
        self.tree=ttk.Treeview(left,columns=cols,show="headings",selectmode="extended")
        for c,t,w in [("codigo","Código",105),("nome","Produto",330),("unidade","Unid.",62),("varejo","Venda",78),("status","Status",90)]:self.tree.heading(c,text=t);self.tree.column(c,width=w,anchor="w" if c=="nome" else "center")
        sb=ttk.Scrollbar(left,orient="vertical",command=self.tree.yview);self.tree.configure(yscrollcommand=sb.set);self.tree.pack(side="left",fill="both",expand=True,padx=(10,0),pady=10);sb.pack(side="right",fill="y",padx=(0,10),pady=10)
        self.tree.bind("<<TreeviewSelect>>",lambda e:self.selection_changed());self.tree.bind("<Control-a>",self.select_all_visible)

        # Painel de detalhe curto: ações e dados extras só aparecem depois do clique.
        top=tk.Frame(right,bg=p["CARD"]);top.pack(fill="x",padx=16,pady=(14,5))
        tk.Label(top,text="Detalhes",bg=p["CARD"],fg=p["MUTED"],font=("Segoe UI",7,"bold")).pack(side="left")
        self.detail_title=tk.Label(right,text="Selecione um item",bg=p["CARD"],fg=p["TEXT"],font=("Segoe UI",12,"bold"),wraplength=380,justify="left");self.detail_title.pack(anchor="w",padx=16,pady=(0,7))
        self.detail_text=tk.Label(right,text="Clique em um produto para ver preço, códigos e ações.",bg=p["ROW_ALT"],fg=p["MUTED"],font=("Segoe UI",8),justify="left",anchor="nw",wraplength=400,padx=11,pady=10);self.detail_text.pack(fill="x",padx=16,pady=(0,9))
        self.action_box=tk.Frame(right,bg=p["CARD"]);self.action_box.pack(fill="x",padx=16,pady=(0,12))

        foot=tk.Frame(self,bg=p["CARD"],highlightbackground=p["LINE"],highlightthickness=1);foot.pack(fill="x",padx=24,pady=(9,16))
        ttk.Progressbar(foot,variable=self.progress_var,maximum=100,style="SR.Horizontal.TProgressbar").pack(side="left",fill="x",expand=True,padx=12,pady=8)
        tk.Label(foot,textvariable=self.status_var,bg=p["CARD"],fg=p["MUTED"],font=("Segoe UI",7)).pack(side="right",padx=12)

    def ensure_built(self):
        c=catalog_counts()
        if c["records"] and not c["unique"]:self.rebuild()
        else:self.refresh()

    def set_stats(self):
        c=catalog_counts()
        for k,w in self.stats.items():w.config(text=str(c.get(k,0)))

    def view_changed(self):
        v=self.view_var.get()
        if v=="FAMÍLIAS":self.filter.config(values=["TODAS","CONFIRMADAS","REVISAR"]);self.filter_var.set("TODAS")
        elif v=="DUPLICIDADES":self.filter.config(values=["REVISAR"]);self.filter_var.set("REVISAR")
        else:self.filter.config(values=["TODOS","COM FAMÍLIA","SEM FAMÍLIA"]);self.filter_var.set("TODOS")
        self.refresh()

    def refresh(self):
        self.tree.delete(*self.tree.get_children());self.records={};q=self.search_var.get();v=self.view_var.get()
        if v=="FAMÍLIAS":
            rows=list_families(self.filter_var.get(),q)
            for r in rows:
                iid="F:"+r["family_key"];self.records[iid]=(v,r)
                status="REVISAR" if r["decision"]=="REVISAR" else "OK"
                self.tree.insert("","end",iid=iid,values=("",r["canonical_name"],"","",status))
        elif v=="DUPLICIDADES":
            rows=list_duplicates(q)
            for r in rows:
                iid="D:"+r["pair_key"];self.records[iid]=(v,r)
                self.tree.insert("","end",iid=iid,values=(r.get("left_code") or r.get("right_code") or "",f"{r['left_name']}  ⇄  {r['right_name']}","","","REVISAR"))
        else:
            rows=list_catalog(q,self.filter_var.get())
            for r in rows:
                iid="P:"+str(r["id"]);self.records[iid]=(v,r)
                display_code=r.get("codigo") or (("CISS "+str(r.get("codigo_ciss"))) if r.get("codigo_ciss") else "")
                self.tree.insert("","end",iid=iid,values=(display_code,r["canonical_name"],r["unidade"],r.get("preco_varejo_atual") or "—","OK"))
        self.set_stats();self.status_var.set(f"{len(rows)} item(ns) exibido(s).")
        if hasattr(self,"review_all_btn"):self.review_all_btn.config(state="disabled")
        self.clear_actions()

    def clear_actions(self):
        for w in self.action_box.winfo_children():w.destroy()
        self.detail_title.config(text="Selecione um item")
        self.detail_text.config(text="Clique em um produto para ver preço, códigos e ações.")

    def selected(self):
        s=self.tree.selection();return self.records.get(s[0]) if s else None

    def selected_items(self):
        return [self.records[i] for i in self.tree.selection() if i in self.records]

    def selection_changed(self):
        count=len(self.tree.selection())
        if hasattr(self,"review_all_btn"):self.review_all_btn.config(state="normal" if count else "disabled")
        if count>1:self.status_var.set(f"{count} itens selecionados • clique em REVISAR TODOS para revisar em sequência.")
        self.show_details()

    def select_all_visible(self,event=None):
        items=self.tree.get_children()
        if items:
            self.tree.selection_set(items)
            self.selection_changed()
        return "break"

    def review_selected(self):
        items=self.selected_items()
        if not items:
            messagebox.showinfo("Banco de Produtos","Selecione um ou mais itens para revisar.",parent=self);return
        BatchReviewWindow(self,items)

    def show_details(self):
        rec=self.selected()
        if not rec:return
        kind,r=rec;p=self.p
        for w in self.action_box.winfo_children():w.destroy()
        if kind=="FAMÍLIAS":
            members=family_members(r["family_key"]);self.detail_title.config(text=r["canonical_name"])
            lines=[f"Tipo: {r['family_type']}",f"Confiança: {r['confidence']*100:.0f}%",f"Produtos/variações: {len(members)}",f"Ocorrências históricas: {r['occurrence_count']}",""]
            lines += [f"• {m['canonical_name']}  →  {m['variant_label']}" for m in members[:10]]
            if len(members)>10:lines.append(f"• +{len(members)-10} outros")
            self.detail_text.config(text="\n".join(lines),fg=p["TEXT"])
            tk.Button(self.action_box,text="CONFIRMAR AGRUPAMENTO",command=lambda:self.family_action(r,"GROUP"),bg=p["GREEN"],fg=p["GREEN_TXT"],relief="flat",font=("Segoe UI",8,"bold"),pady=7).pack(fill="x",pady=2)
            tk.Button(self.action_box,text="MANTER SEPARADOS / NUNCA AGRUPAR",command=lambda:self.family_action(r,"SEPARATE"),bg=p["RED"],fg=p["RED_TXT"],relief="flat",font=("Segoe UI",8,"bold"),pady=7).pack(fill="x",pady=2)
            tk.Button(self.action_box,text="EDITAR NOME E TIPO DA FAMÍLIA",command=lambda:self.edit_family(r),bg=p["LIGHT_BLUE"],fg=p["LIGHT_BLUE_TXT"],relief="flat",font=("Segoe UI",8,"bold"),pady=7).pack(fill="x",pady=2)
        elif kind=="DUPLICIDADES":
            self.detail_title.config(text="Possível duplicidade")
            self.detail_text.config(text=f"{r['left_name']}\n\n⇄\n\n{r['right_name']}\n\nSemelhança: {r['confidence']*100:.0f}%\n\n'Mesmo produto' consolida os históricos. 'Manter separados' ensina o SR Studio a não sugerir este par novamente.",fg=p["TEXT"])
            tk.Button(self.action_box,text="É O MESMO PRODUTO",command=lambda:self.duplicate_action(r,"MERGE"),bg=p["GREEN"],fg=p["GREEN_TXT"],relief="flat",font=("Segoe UI",8,"bold"),pady=7).pack(fill="x",pady=2)
            tk.Button(self.action_box,text="MANTER SEPARADOS / NUNCA MESCLAR",command=lambda:self.duplicate_action(r,"SEPARATE"),bg=p["RED"],fg=p["RED_TXT"],relief="flat",font=("Segoe UI",8,"bold"),pady=7).pack(fill="x",pady=2)
        else:
            info=get_image_info(r.get("identity_key")) or {}
            categoria=get_category(r.get("identity_key")) or guess_category(r.get("canonical_name")) or "—"
            img_status="SIM" if info.get("official_path") else "NÃO"
            ciss_code=r.get("codigo_ciss") or "—"
            custo_ciss=r.get("custo_reposicao") or "—"
            varejo_ciss=r.get("preco_varejo_atual") or "—"
            atacado_ciss=r.get("preco_atacado_atual") or "—"
            ciss_dt=str(r.get("ciss_updated_at") or "—").replace("T"," ")[:16]
            self.detail_title.config(text=r["canonical_name"])
            self.detail_text.config(text=f"EAN: {r['codigo'] or '—'}   •   CISS: {ciss_code}\nUnidade: {r['unidade'] or '—'}\nVenda: R$ {varejo_ciss}   •   Custo: R$ {custo_ciss}\nImagem: {img_status}   •   Setor: {categoria}",fg=p["TEXT"])
            rowa=tk.Frame(self.action_box,bg=p["CARD"]);rowa.pack(fill="x",pady=2)
            tk.Button(rowa,text="HISTÓRICO",command=lambda:self.app.show_product_history_dialog(r["codigo"],r["canonical_name"]),bg=p["BLUE"],fg="white",relief="flat",font=("Segoe UI",7,"bold"),pady=7).pack(side="left",fill="x",expand=True,padx=(0,2))
            tk.Button(rowa,text="IMAGEM",command=lambda:self.open_image_manager(r),bg=p["GREEN"],fg=p["GREEN_TXT"],relief="flat",font=("Segoe UI",7,"bold"),pady=7).pack(side="left",fill="x",expand=True,padx=(2,0))
            tk.Button(self.action_box,text="MAIS DADOS",command=lambda:self.show_more_product_data(r,categoria,img_status),bg=p["ROW_ALT"],fg=p["TEXT"],relief="flat",font=("Segoe UI",7,"bold"),pady=6).pack(fill="x",pady=2)
            tk.Button(self.action_box,text="EDITAR SETOR",command=lambda:self.edit_category(r),bg=p["LIGHT_BLUE"],fg=p["LIGHT_BLUE_TXT"],relief="flat",font=("Segoe UI",7,"bold"),pady=6).pack(fill="x",pady=2)

    def show_more_product_data(self,r,categoria,img_status):
        lines=[
            f"Código/EAN: {r.get('codigo') or '—'}",
            f"Código CISS: {r.get('codigo_ciss') or '—'}",
            f"Unidade: {r.get('unidade') or '—'}",
            f"Custo reposição: {r.get('custo_reposicao') or '—'}",
            f"Preço varejo: {r.get('preco_varejo_atual') or '—'}",
            f"Preço atacado: {r.get('preco_atacado_atual') or '—'}",
            f"Atualizado CISSPoder: {str(r.get('ciss_updated_at') or '—').replace('T',' ')[:16]}",
            "",
            f"Ocorrências: {r.get('occurrence_count',0)}",
            f"Primeira aparição: {r.get('first_seen') or '—'}",
            f"Última aparição: {r.get('last_seen') or '—'}",
            f"Família: {r.get('family_key') or 'Sem família'}",
            f"Variação: {r.get('variant_label') or '—'}",
            f"Setor: {categoria}",
            f"Imagem oficial: {img_status}",
        ]
        messagebox.showinfo("Dados do Produto","\n".join(lines),parent=self)

    def family_action(self,r,action):
        msg="Confirmar este agrupamento e reaplicar nas próximas importações?" if action=="GROUP" else "Manter estes produtos separados e nunca agrupá-los automaticamente?"
        if not messagebox.askyesno("Banco de Produtos",msg,parent=self):return
        set_family_rule(r["family_key"],action,r["canonical_name"],r["family_type"]);self.refresh()

    def edit_family(self,r):
        name=simpledialog.askstring("Nome da família","Nome consolidado:",initialvalue=r["canonical_name"],parent=self)
        if not name:return
        t=simpledialog.askstring("Tipo da família",f"Tipo ({', '.join(FAMILY_TYPES)}):",initialvalue=r["family_type"],parent=self)
        t=str(t or r["family_type"]).upper().strip()
        if t not in FAMILY_TYPES:t="VARIEDADES"
        set_family_rule(r["family_key"],"GROUP",normalize_product_name(name),t);self.refresh()

    def duplicate_action(self,r,action):
        msg="Consolidar estes dois registros como o mesmo produto? O histórico bruto não será apagado." if action=="MERGE" else "Ensinar o SR Studio a manter estes produtos separados?"
        if not messagebox.askyesno("Banco de Produtos",msg,parent=self):return
        set_duplicate_rule(r["pair_key"],r["left_key"],r["right_key"],action);self.refresh()

    def open_image_manager(self,r):
        ProductImageManager(self,r,self.p)

    def edit_category(self,r):
        current=get_category(r.get("identity_key")) or guess_category(r.get("canonical_name"))
        cat=simpledialog.askstring("Categoria / Setor","Informe a categoria/setor deste produto:",initialvalue=current,parent=self)
        if cat is None:return
        set_category(r.get("identity_key"),cat)
        self.show_details()
        self.refresh()

    def find_duplicates(self):
        """Reconstrói a camada derivada e abre diretamente a revisão de duplicados."""
        if self.busy:return
        self.busy=True;self.app.busy=True;self.progress_var.set(0);self.status_var.set("Localizando duplicados...")
        def prog(v,t):self.after(0,lambda v=v,t=t:(self.progress_var.set(v),self.status_var.set(t)))
        def worker():
            try:
                c=rebuild_catalog(prog)
                self.after(0,lambda:self.finish_find_duplicates(c))
            except Exception as e:self.after(0,lambda msg=str(e):self.fail_rebuild(msg))
        threading.Thread(target=worker,daemon=True).start()

    def finish_find_duplicates(self,c):
        self.busy=False;self.app.busy=False;self.progress_var.set(100)
        self.view_var.set("DUPLICIDADES");self.filter_var.set("REVISAR");self.view_changed()
        n=int(c.get("duplicates") or 0)
        self.status_var.set(f"{n} possível(is) duplicidade(s) para revisar.")
        if n:
            messagebox.showinfo("Duplicados",f"Foram encontrados {n} possível(is) duplicidade(s).\n\nSelecione os pares e use REVISAR para confirmar se são o mesmo produto.",parent=self)
        else:
            messagebox.showinfo("Duplicados","Nenhuma duplicidade pendente foi encontrada.",parent=self)

    def rebuild(self):
        if self.busy:return
        self.busy=True;self.app.busy=True;self.progress_var.set(0);self.status_var.set("Analisando histórico...")
        def prog(v,t):self.after(0,lambda v=v,t=t:(self.progress_var.set(v),self.status_var.set(t)))
        def worker():
            try:
                c=rebuild_catalog(prog)
                self.after(0,lambda:self.finish_rebuild(c))
            except Exception as e:self.after(0,lambda msg=str(e):self.fail_rebuild(msg))
        threading.Thread(target=worker,daemon=True).start()

    def finish_rebuild(self,c):
        self.busy=False;self.app.busy=False;self.progress_var.set(100);self.refresh();self.status_var.set(f"Organizado • {c['unique']} únicos • {c['families']} famílias • {c['review']} para revisar")
        messagebox.showinfo("Banco de Produtos",f"Organização concluída.\n\n{c['records']} registros históricos preservados\n{c['unique']} produtos únicos\n{c['families']} famílias identificadas\n{c['variants']} produtos/variações agrupados\n{c['review']} item(ns) para revisão",parent=self)

    def fail_rebuild(self,msg):
        self.busy=False;self.app.busy=False;self.progress_var.set(0);self.status_var.set(msg);messagebox.showerror("Banco de Produtos",msg,parent=self)
