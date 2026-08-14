# -*- coding: utf-8 -*-
"""Montador de Promoções do SR Studio 4.0.4.

Cria campanhas sem depender de uma planilha externa e reaproveita o Banco de Produtos,
histórico, famílias, categorias e imagens oficiais.
"""
import os, sqlite3, json, threading, re
from pathlib import Path
from datetime import datetime, timedelta
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog

from SRStudio21 import PRODUCT_DB, LOCAL_DATA, norm, money, dec, product_history, normalize_product_name
from ProductImages import get_image_info, get_category, guess_category, ProductImageManager
from PromoExcelTemplates import export_campaign_xlsx, profile_choices, detect_profile, PROFILE_LABELS
from CISSProductSync import current_product_snapshot
from ui_v2 import add_tooltip, center_toplevel

DB_PATH = LOCAL_DATA / "promotion_builder.db"
STATUSES = ("RASCUNHO", "EM REVISÃO", "APROVADA", "CARTAZES GERADOS", "FINALIZADA")
UNIT_OPTIONS = ("UN", "KG", "À LATA", "À GARRAFA")


def _conn():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def _prod_conn():
    con = sqlite3.connect(PRODUCT_DB)
    con.row_factory = sqlite3.Row
    return con


def _now(): return datetime.now().isoformat(timespec="seconds")


# Cache completo do Banco usado pelo Montador. É aquecido na inicialização para
# evitar milhares de consultas pequenas ao SQLite quando a tela é aberta.
_BUILDER_PRODUCTS_CACHE=None
_BUILDER_FAMILIES_CACHE=None
_BUILDER_CATEGORIES_CACHE=None
_BUILDER_CACHE_LOCK=threading.RLock()

def invalidate_builder_catalog_cache():
    global _BUILDER_PRODUCTS_CACHE,_BUILDER_FAMILIES_CACHE,_BUILDER_CATEGORIES_CACHE
    with _BUILDER_CACHE_LOCK:
        _BUILDER_PRODUCTS_CACHE=None;_BUILDER_FAMILIES_CACHE=None;_BUILDER_CATEGORIES_CACHE=None

def preload_builder_catalog(force=False):
    global _BUILDER_PRODUCTS_CACHE,_BUILDER_FAMILIES_CACHE,_BUILDER_CATEGORIES_CACHE
    with _BUILDER_CACHE_LOCK:
        if _BUILDER_PRODUCTS_CACHE is not None and not force:
            return len(_BUILDER_PRODUCTS_CACHE)
        products=[];families=[];image_map={}
        try:
            with _prod_conn() as con:
                products=[dict(r) for r in con.execute("SELECT * FROM catalog_products WHERE active=1 ORDER BY canonical_name COLLATE NOCASE").fetchall()]
                families=[dict(r) for r in con.execute("SELECT * FROM catalog_families WHERE decision!='SEPARATE' ORDER BY canonical_name COLLATE NOCASE").fetchall()]
                try:
                    imgs=con.execute("SELECT identity_key,official_path,official_url,source_name,confidence,category FROM catalog_images").fetchall()
                    image_map={str(r['identity_key']):dict(r) for r in imgs}
                except Exception:
                    image_map={}
        except Exception:
            products=[];families=[]
        cats={"SEM CATEGORIA"}
        for x in products:
            cat=str(x.get("categoria") or (image_map.get(str(x.get("identity_key"))) or {}).get("category") or guess_category(x.get("canonical_name")) or "SEM CATEGORIA").upper()
            x["categoria"]=cat;cats.add(cat)
            x["image_info"]=image_map.get(str(x.get("identity_key"))) or {}
            x["_search_norm"]=norm(" ".join(str(x.get(k) or "") for k in ("canonical_name","codigo","codigo_ciss","canonical_norm")))
        fam_out=[]
        for x in families:
            x=dict(x);x["identity_key"]="FAMILY:"+str(x.get("family_key") or "");x["codigo"]=""
            x["canonical_name"]=x.get("canonical_name") or x.get("family_key");x["categoria"]=guess_category(x["canonical_name"]) or "SEM CATEGORIA"
            x["unidade"]="UN";x["image_info"]={};x["_search_norm"]=norm(x["canonical_name"]);fam_out.append(x)
        cats.update(("MERCEARIA","BEBIDAS","HORTIFRUTI","AÇOUGUE","PADARIA","LIMPEZA","HIGIENE","PET","BAZAR","CONGELADOS","LATICÍNIOS"))
        _BUILDER_PRODUCTS_CACHE=products;_BUILDER_FAMILIES_CACHE=fam_out;_BUILDER_CATEGORIES_CACHE=["TODOS"]+sorted(cats)
        return len(products)


def ensure_schema():
    with _conn() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS builder_campaigns(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            validity TEXT,
            status TEXT NOT NULL DEFAULT 'RASCUNHO',
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_builder_campaign_name ON builder_campaigns(name);
        CREATE TABLE IF NOT EXISTS builder_items(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id INTEGER NOT NULL,
            identity_key TEXT,
            codigo TEXT,
            produto TEXT NOT NULL,
            categoria TEXT,
            custo TEXT,
            varejo TEXT,
            promocao TEXT,
            clube TEXT,
            unidade TEXT,
            limite TEXT,
            copies INTEGER DEFAULT 1,
            image_path TEXT,
            tags TEXT,
            sort_order INTEGER DEFAULT 0,
            FOREIGN KEY(campaign_id) REFERENCES builder_campaigns(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_builder_items_campaign ON builder_items(campaign_id);
        """)
ensure_schema()


def catalog_products(search="", category="TODOS", limit=1000):
    preload_builder_catalog();q=norm(search);cat=str(category or "TODOS").upper();rows=[]
    for r in (_BUILDER_PRODUCTS_CACHE or []):
        if q and q not in r.get("_search_norm",""):continue
        if cat!="TODOS" and str(r.get("categoria") or "").upper()!=cat:continue
        rows.append(dict(r))
        if len(rows)>=int(limit):break
    return rows


def catalog_families(search="", limit=500):
    preload_builder_catalog();q=norm(search);rows=[]
    for r in (_BUILDER_FAMILIES_CACHE or []):
        if q and q not in r.get("_search_norm",""):continue
        rows.append(dict(r))
        if len(rows)>=int(limit):break
    return rows


def categories():
    preload_builder_catalog()
    return list(_BUILDER_CATEGORIES_CACHE or ["TODOS"])


def refresh_ciss_values(items):
    """Força Custo de Reposição e Preço de Venda atuais do relatório 208 no Montador.

    A promoção/Clube continuam sendo definidos pelo usuário; apenas custo/varejo são
    tratados como dados mestres do CISSPoder quando existe vínculo.
    """
    preload_builder_catalog()
    by_identity={str(r.get("identity_key") or ""):r for r in (_BUILDER_PRODUCTS_CACHE or []) if r.get("identity_key")}
    by_code={str(r.get("codigo") or ""):r for r in (_BUILDER_PRODUCTS_CACHE or []) if r.get("codigo")}
    by_norm={str(r.get("canonical_norm") or ""):r for r in (_BUILDER_PRODUCTS_CACHE or []) if r.get("canonical_norm")}
    updated=0
    for x in items or []:
        r=by_identity.get(str(x.get("identity_key") or ""))
        if not r and x.get("codigo"):r=by_code.get(str(x.get("codigo") or ""))
        if not r:r=by_norm.get(norm(x.get("produto") or x.get("canonical_name") or ""))
        if not r:continue
        changed=False
        if str(r.get("custo_reposicao") or "").strip():
            val=str(r.get("custo_reposicao") or "").strip()
            if str(x.get("custo") or "")!=val:x["custo"]=val;changed=True
        if str(r.get("preco_varejo_atual") or "").strip():
            val=str(r.get("preco_varejo_atual") or "").strip()
            if str(x.get("varejo") or "")!=val:x["varejo"]=val;changed=True
        if r.get("codigo_ciss"):x["codigo_ciss"]=str(r.get("codigo_ciss") or "")
        if r.get("ciss_updated_at"):x["ciss_updated_at"]=str(r.get("ciss_updated_at") or "")
        x["fonte_custo_varejo"]="CISSPODER 208" if (r.get("custo_reposicao") or r.get("preco_varejo_atual")) else x.get("fonte_custo_varejo","")
        if changed:updated+=1
    return updated


def history_snapshot(code, product, identity_key=""):
    hist = product_history(str(code or ""), str(product or ""), limit=30)
    current = current_product_snapshot(str(code or ""), str(product or ""), identity_key=str(identity_key or ""))
    r = hist[0] if hist else {}
    return {
        "last_promo": r.get("promocao") or "",
        "last_club": r.get("clube") or "",
        # O relatório 208 vira a fonte atual de custo/varejo; histórico promocional é fallback.
        "last_cost": current.get("custo_reposicao") or r.get("custo") or "",
        "last_varejo": current.get("preco_varejo") or r.get("varejo") or "",
        "last_atacado": current.get("preco_atacado") or "",
        "codigo_ciss": current.get("codigo_ciss") or "",
        "ciss_updated_at": current.get("updated_at") or "",
        "last_date": r.get("gerado_em") or "",
        "count": len(hist),
    }


def smart_tags(item):
    tags = []
    info = get_image_info(item.get("identity_key")) or {}
    if info.get("official_path"): tags.append("IMAGEM OK")
    else: tags.append("SEM IMAGEM")
    if item.get("fonte_custo_varejo")=="CISSPODER 208" or item.get("ciss_updated_at"): tags.append("CISS ATUAL")
    if not item.get("custo"): tags.append("SEM CUSTO")
    promo = dec(item.get("promocao")); club = dec(item.get("clube")); cost = dec(item.get("custo")); varejo = dec(item.get("varejo"))
    chosen = club if club is not None else promo
    if chosen is not None and cost is not None:
        if chosen < cost: tags.append("ABAIXO CUSTO")
        elif cost > 0 and ((chosen-cost)/cost*100) < 10: tags.append("MARGEM BAIXA")
    if chosen is not None and varejo is not None and chosen >= varejo: tags.append("CONFIRMAR PREÇO")
    snap = history_snapshot(item.get("codigo"), item.get("produto"), item.get("identity_key"))
    if snap["count"] >= 3: tags.append("RECORRENTE")
    try:
        if snap["last_date"]:
            d = datetime.fromisoformat(str(snap["last_date"])[:19])
            if datetime.now()-d < timedelta(days=21): tags.append("PROMO RECENTE")
    except Exception: pass
    return tags


def campaign_rows():
    with _conn() as con:
        return [dict(r) for r in con.execute("SELECT * FROM builder_campaigns ORDER BY updated_at DESC,id DESC").fetchall()]


def save_campaign(campaign_id, name, validity, status, items, notes=""):
    refresh_ciss_values(items)
    name = str(name or "NOVA PROMOÇÃO").strip().upper()
    validity = str(validity or "").strip()
    status = status if status in STATUSES else "RASCUNHO"
    with _conn() as con:
        if campaign_id:
            con.execute("UPDATE builder_campaigns SET name=?,validity=?,status=?,notes=?,updated_at=? WHERE id=?",
                        (name,validity,status,notes,_now(),campaign_id))
            cid = campaign_id
            con.execute("DELETE FROM builder_items WHERE campaign_id=?", (cid,))
        else:
            cur = con.execute("INSERT INTO builder_campaigns(name,validity,status,notes,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                              (name,validity,status,notes,_now(),_now()))
            cid = cur.lastrowid
        rows = []
        for i,x in enumerate(items):
            tags = ", ".join(smart_tags(x))
            info = get_image_info(x.get("identity_key")) or {}
            rows.append((cid,x.get("identity_key",""),x.get("codigo",""),x.get("produto",""),x.get("categoria",""),x.get("custo",""),x.get("varejo",""),x.get("promocao",""),x.get("clube",""),x.get("unidade","UN"),x.get("limite",""),int(x.get("copies") or 1),info.get("official_path",x.get("image_path","")),tags,i))
        if rows:
            con.executemany("""INSERT INTO builder_items(campaign_id,identity_key,codigo,produto,categoria,custo,varejo,promocao,clube,unidade,limite,copies,image_path,tags,sort_order)
                               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", rows)
    try:
        from EncarteModule import invalidate_encarte_cache
        invalidate_encarte_cache()
    except Exception:
        pass
    return cid


def load_campaign(cid):
    with _conn() as con:
        c = con.execute("SELECT * FROM builder_campaigns WHERE id=?", (cid,)).fetchone()
        items = con.execute("SELECT * FROM builder_items WHERE campaign_id=? ORDER BY sort_order,id", (cid,)).fetchall()
    out=[dict(r) for r in items]
    refresh_ciss_values(out)
    return (dict(c) if c else None, out)


def set_campaign_status(cid, status):
    if not cid or status not in STATUSES:return
    with _conn() as con:
        con.execute("UPDATE builder_campaigns SET status=?,updated_at=? WHERE id=?", (status,_now(),cid))


def mark_campaign_status_from_jobs(jobs, status="CARTAZES GERADOS"):
    ids = {j.get("_builder_campaign_id") for j in jobs or [] if j.get("_builder_campaign_id")}
    for cid in ids: set_campaign_status(cid,status)


def suggested_products(campaign_name, limit=30):
    q = norm(campaign_name)
    if not q:return []
    with _prod_conn() as con:
        hist = [dict(r) for r in con.execute("SELECT codigo,produto,produto_norm,campanha,gerado_em FROM history WHERE TRIM(campanha)<>'' ORDER BY gerado_em DESC").fetchall()]
        catalogs = [dict(r) for r in con.execute("SELECT * FROM catalog_products WHERE active=1").fetchall()]
    stats={}
    for r in hist:
        if q not in norm(r.get("campanha")):
            continue
        key=str(r.get("codigo") or "") or str(r.get("produto_norm") or "")
        if not key:continue
        s=stats.setdefault(key,{"vezes":0,"ultima":"","codigo":r.get("codigo","") or "","produto_norm":r.get("produto_norm","") or ""})
        s["vezes"]+=1
        if str(r.get("gerado_em") or "")>s["ultima"]:s["ultima"]=str(r.get("gerado_em") or "")
    bycode={str(r.get("codigo") or ""):r for r in catalogs if r.get("codigo")}
    byname={str(r.get("canonical_norm") or ""):r for r in catalogs}
    ranked=sorted(stats.values(),key=lambda x:(x["vezes"],x["ultima"]),reverse=True)[:limit]
    out=[]
    for s in ranked:
        p=bycode.get(s["codigo"]) if s["codigo"] else byname.get(s["produto_norm"])
        if not p:continue
        p=dict(p);p["vezes"]=s["vezes"];p["ultima"]=s["ultima"]
        p["categoria"]=p.get("categoria") or get_category(p.get("identity_key")) or guess_category(p.get("canonical_name")) or "SEM CATEGORIA"
        out.append(p)
    return out


def historical_campaign_names(limit=100):
    with _prod_conn() as con:
        rows = con.execute("SELECT campanha,COUNT(*) n,MAX(gerado_em) dt FROM history WHERE TRIM(campanha)<>'' GROUP BY campanha ORDER BY dt DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


def historical_campaign_items(campaign):
    with _prod_conn() as con:
        rows = con.execute("SELECT * FROM history WHERE campanha=? ORDER BY gerado_em DESC,id DESC", (campaign,)).fetchall()
    seen=set();out=[]
    for r in rows:
        r=dict(r); key=str(r.get("codigo") or "") or r.get("produto_norm")
        if key in seen:continue
        seen.add(key)
        identity=""
        with _prod_conn() as con:
            if r.get("codigo"):
                c=con.execute("SELECT * FROM catalog_products WHERE codigo=? LIMIT 1",(r["codigo"],)).fetchone()
            else:
                c=con.execute("SELECT * FROM catalog_products WHERE canonical_norm=? LIMIT 1",(r["produto_norm"],)).fetchone()
        c=dict(c) if c else {}
        out.append({
            "identity_key":c.get("identity_key",""),"codigo":r.get("codigo",""),"produto":c.get("canonical_name") or r.get("produto",""),
            "categoria":c.get("categoria") or guess_category(r.get("produto")) or "SEM CATEGORIA","custo":r.get("custo",""),"varejo":r.get("varejo",""),
            "promocao":r.get("promocao",""),"clube":r.get("clube",""),"unidade":r.get("unidade") or "UN","limite":r.get("limite","") or "","copies":1,
        })
    refresh_ciss_values(out)
    return out


def build_jobs(items, campaign, validity, campaign_id=None):
    refresh_ciss_values(items)
    jobs=[]
    for idx,x in enumerate(items,1):
        promo=str(x.get("promocao") or "").strip(); club=str(x.get("clube") or "").strip()
        if not promo and not club: continue
        if promo and club:
            tipo=1 if dec(promo)==dec(club) else 2
        elif club:
            tipo=3
        else: tipo=1
        jobs.append({
            "id":idx,"campanha":str(campaign or "PROMOÇÃO").strip().upper(),"codigo":str(x.get("codigo") or ""),
            "produto_original":x.get("produto",""),"produto":normalize_product_name(x.get("produto","")),"produto_render":normalize_product_name(x.get("produto","")),
            "custo":str(x.get("custo") or ""),"varejo":str(x.get("varejo") or ""),"promocao":promo,"clube":club,"validade":str(validity or ""),"tipo":tipo,
            "entrada_original":x.get("unidade","UN"),"unidade_exibicao":x.get("unidade","UN"),"unidade_reconhecida":True,"limite":str(x.get("limite") or ""),
            "copies":max(1,int(x.get("copies") or 1)),"selected":True,"issues":[],"status":"OK","layout_status":"","layout_detail":"","layout_font":0,
            "sheet":"MONTADOR","linha":idx+3,"manual_edit":True,"_builder_campaign_id":campaign_id,"_builder_identity_key":x.get("identity_key","")
        })
    return jobs




class PromotionBuilderPanel(tk.Frame):
    def __init__(self,parent,app,palette):
        super().__init__(parent,bg=palette["APP_BG"])
        self.app=app;self.p=palette;self.campaign_id=None;self.items=[];self.catalog_records={};self._busy=False
        self.campaign_var=tk.StringVar(value="");self.validity_var=tk.StringVar(value=datetime.now().strftime("%d/%m/%Y"));self.status_var=tk.StringVar(value="RASCUNHO")
        self.excel_profile_var=tk.StringVar(value="AUTOMÁTICO")
        self.search_var=tk.StringVar();self.category_var=tk.StringVar(value="TODOS");self.catalog_mode=tk.StringVar(value="PRODUTOS")
        self.info_var=tk.StringVar(value="Montador pronto.")
        self._build();self.refresh_catalog();self.refresh_items()

    def _build(self):
        p=self.p
        head=tk.Frame(self,bg=p["APP_BG"]);head.pack(fill="x",padx=22,pady=(16,8))
        rowh=tk.Frame(head,bg=p["APP_BG"]);rowh.pack(fill="x")
        tk.Label(rowh,text="Montador",bg=p["APP_BG"],fg=p["TEXT"],font=("Segoe UI",20,"bold")).pack(side="left")
        tip=tk.Label(rowh,text="ⓘ",bg=p["APP_BG"],fg=p["BLUE2"],font=("Segoe UI",10,"bold"));tip.pack(side="left",padx=8)
        add_tooltip(tip,"Crie promoções usando o Banco de Produtos. Custo e preço de venda vêm prioritariamente do relatório 208 do CISSPoder; Promoção e Clube continuam sob seu controle.")
        tk.Label(rowh,textvariable=self.status_var,bg=p["LIGHT_BLUE"],fg=p["LIGHT_BLUE_TXT"],font=("Segoe UI",7,"bold"),padx=9,pady=4).pack(side="right")

        # Barra da campanha: somente os dados essenciais ficam sempre visíveis.
        top=tk.Frame(self,bg=p["CARD"],highlightbackground=p["LINE"],highlightthickness=1);top.pack(fill="x",padx=22,pady=(0,9))
        row=tk.Frame(top,bg=p["CARD"]);row.pack(fill="x",padx=12,pady=9)
        tk.Label(row,text="Campanha",bg=p["CARD"],fg=p["MUTED"],font=("Segoe UI",7,"bold")).pack(side="left")
        tk.Entry(row,textvariable=self.campaign_var,bg=p["ROW_ALT"],fg=p["TEXT"],insertbackground=p["TEXT"],relief="flat",font=("Segoe UI",9),width=28).pack(side="left",padx=(6,12),ipady=5)
        tk.Label(row,text="Validade",bg=p["CARD"],fg=p["MUTED"],font=("Segoe UI",7,"bold")).pack(side="left")
        tk.Entry(row,textvariable=self.validity_var,bg=p["ROW_ALT"],fg=p["TEXT"],insertbackground=p["TEXT"],relief="flat",font=("Segoe UI",9),width=13).pack(side="left",padx=(6,12),ipady=5)
        ttk.Combobox(row,textvariable=self.status_var,values=STATUSES,state="readonly",width=15).pack(side="left",padx=(0,8))
        tk.Button(row,text="SALVAR",command=self.save_draft,bg=p["BLUE"],fg="white",relief="flat",font=("Segoe UI",8,"bold"),padx=12,pady=6).pack(side="right")
        tk.Button(row,text="ABRIR",command=self.open_campaign_dialog,bg=p["ROW_ALT"],fg=p["TEXT"],relief="flat",font=("Segoe UI",8,"bold"),padx=11,pady=6).pack(side="right",padx=5)
        self.excel_profile_btn=tk.Button(row,text="EXCEL ⚙",command=self.choose_excel_profile,bg=p["ROW_ALT"],fg=p["MUTED"],relief="flat",font=("Segoe UI",7,"bold"),padx=9,pady=6)
        self.excel_profile_btn.pack(side="right",padx=5);add_tooltip(self.excel_profile_btn,"Escolher a estrutura usada quando a campanha for exportada para Excel.")

        # Duas áreas principais. O editor detalhado fica recolhido até ser solicitado.
        body=tk.PanedWindow(self,orient="horizontal",sashwidth=7,bg=p["APP_BG"],bd=0);body.pack(fill="both",expand=True,padx=22,pady=(0,9))
        self.body_pane=body
        left=tk.Frame(body,bg=p["CARD"],highlightbackground=p["LINE"],highlightthickness=1)
        mid=tk.Frame(body,bg=p["CARD"],highlightbackground=p["LINE"],highlightthickness=1)
        right=tk.Frame(body,bg=p["CARD"],highlightbackground=p["LINE"],highlightthickness=1)
        self.editor_panel=right;self.editor_visible=False
        body.add(left,minsize=300,width=390);body.add(mid,minsize=520,width=760)

        # Banco de produtos
        lh=tk.Frame(left,bg=p["CARD"]);lh.pack(fill="x",padx=10,pady=(10,6))
        tk.Label(lh,text="Banco de Produtos",bg=p["CARD"],fg=p["TEXT"],font=("Segoe UI",10,"bold")).pack(side="left")
        tk.Label(lh,text="Ctrl+A seleciona todos",bg=p["CARD"],fg=p["MUTED"],font=("Segoe UI",7)).pack(side="right")
        search=tk.Entry(left,textvariable=self.search_var,bg=p["ROW_ALT"],fg=p["TEXT"],insertbackground=p["TEXT"],relief="flat",font=("Segoe UI",9));search.pack(fill="x",padx=10,ipady=5);search.bind("<KeyRelease>",lambda e:self.refresh_catalog())
        filt=tk.Frame(left,bg=p["CARD"]);filt.pack(fill="x",padx=10,pady=6)
        ttk.Combobox(filt,textvariable=self.catalog_mode,values=("PRODUTOS","FAMÍLIAS"),state="readonly",width=11).pack(side="left");self.catalog_mode.trace_add("write",lambda *_:self.refresh_catalog())
        self.cat_combo=ttk.Combobox(filt,textvariable=self.category_var,values=categories(),state="readonly",width=16);self.cat_combo.pack(side="left",padx=5);self.category_var.trace_add("write",lambda *_:self.refresh_catalog())
        cols=("codigo","nome","img")
        self.catalog_tree=ttk.Treeview(left,columns=cols,show="headings",selectmode="extended")
        for c,t,w in (("codigo","Código",82),("nome","Produto",245),("img","Img",38)):
            self.catalog_tree.heading(c,text=t);self.catalog_tree.column(c,width=w,anchor="w")
        self.catalog_tree.pack(fill="both",expand=True,padx=10,pady=(0,6))
        self.catalog_tree.bind("<Control-a>",lambda e:(self.catalog_tree.selection_set(self.catalog_tree.get_children()),"break")[1])
        btn=tk.Frame(left,bg=p["CARD"]);btn.pack(fill="x",padx=10,pady=(0,10))
        tk.Button(btn,text="＋ ADICIONAR",command=self.add_selected,bg=p["GREEN"],fg=p["GREEN_TXT"],relief="flat",font=("Segoe UI",8,"bold"),pady=7).pack(side="left",fill="x",expand=True,padx=(0,3))
        tk.Button(btn,text="✦ SUGESTÕES",command=self.suggest,bg=p["ORANGE"],fg=p["ORANGE_TXT"],relief="flat",font=("Segoe UI",8,"bold"),pady=7).pack(side="left",fill="x",expand=True,padx=(3,0))

        # Produtos da campanha - tabela mais limpa.
        mh=tk.Frame(mid,bg=p["CARD"]);mh.pack(fill="x",padx=10,pady=(10,6))
        tk.Label(mh,text="Campanha",bg=p["CARD"],fg=p["TEXT"],font=("Segoe UI",10,"bold")).pack(side="left")
        self.count_label=tk.Label(mh,text="0 itens",bg=p["CARD"],fg=p["MUTED"],font=("Segoe UI",8));self.count_label.pack(side="left",padx=7)
        self.editor_btn=tk.Button(mh,text="EDITAR PRODUTO",command=self.open_editor,bg=p["ROW_ALT"],fg=p["TEXT"],relief="flat",font=("Segoe UI",7,"bold"),padx=9,pady=5)
        self.editor_btn.pack(side="right")
        cols=("produto","promo","clube","unit","status")
        self.items_tree=ttk.Treeview(mid,columns=cols,show="headings",selectmode="extended")
        specs=(("produto","Produto",330),("promo","Promo",75),("clube","Clube",75),("unit","Unid.",62),("status","Status",135))
        for c,t,w in specs:self.items_tree.heading(c,text=t);self.items_tree.column(c,width=w,anchor="w" if c in {"produto","status"} else "center")
        self.items_tree.pack(fill="both",expand=True,padx=10,pady=(0,6));self.items_tree.bind("<<TreeviewSelect>>",lambda e:self.show_item());self.items_tree.bind("<Double-1>",lambda e:self.open_editor())
        mbtn=tk.Frame(mid,bg=p["CARD"]);mbtn.pack(fill="x",padx=10,pady=(0,10))
        tk.Button(mbtn,text="REMOVER",command=self.remove_selected,bg=p["RED"],fg=p["RED_TXT"],relief="flat",font=("Segoe UI",7,"bold"),padx=9,pady=6).pack(side="left")
        tk.Button(mbtn,text="ÚLTIMO PREÇO",command=self.use_last_price_selected,bg=p["LIGHT_BLUE"],fg=p["LIGHT_BLUE_TXT"],relief="flat",font=("Segoe UI",7,"bold"),padx=9,pady=6).pack(side="left",padx=4)
        tk.Button(mbtn,text="EDIÇÃO EM MASSA",command=self.bulk_edit,bg=p["PURPLE"],fg=p["PURPLE_TXT"],relief="flat",font=("Segoe UI",7,"bold"),padx=9,pady=6).pack(side="left",padx=4)

        # Editor lateral - existe, mas começa fechado.
        rh=tk.Frame(right,bg=p["CARD"]);rh.pack(fill="x",padx=12,pady=(10,5))
        tk.Label(rh,text="Editar produto",bg=p["CARD"],fg=p["TEXT"],font=("Segoe UI",10,"bold")).pack(side="left")
        tk.Button(rh,text="×",command=self.close_editor,bg=p["CARD"],fg=p["MUTED"],relief="flat",font=("Segoe UI",12,"bold")).pack(side="right")
        self.detail_title=tk.Label(right,text="Selecione um item",bg=p["CARD"],fg=p["TEXT"],wraplength=270,justify="left",font=("Segoe UI",9,"bold"));self.detail_title.pack(anchor="w",padx=12,pady=(0,8))
        self.fields={}
        for key,label in (("custo","Custo"),("varejo","Varejo"),("promocao","Promoção"),("clube","Clube"),("limite","Limite")):
            tk.Label(right,text=label,bg=p["CARD"],fg=p["MUTED"],font=("Segoe UI",7,"bold")).pack(anchor="w",padx=12)
            v=tk.StringVar();self.fields[key]=v;tk.Entry(right,textvariable=v,bg=p["ROW_ALT"],fg=p["TEXT"],insertbackground=p["TEXT"],relief="flat",font=("Segoe UI",9)).pack(fill="x",padx=12,pady=(2,5),ipady=4)
        tk.Label(right,text="Unidade",bg=p["CARD"],fg=p["MUTED"],font=("Segoe UI",7,"bold")).pack(anchor="w",padx=12)
        self.unit_var=tk.StringVar(value="UN");ttk.Combobox(right,textvariable=self.unit_var,values=UNIT_OPTIONS,state="readonly").pack(fill="x",padx=12,pady=(2,7))
        tk.Button(right,text="SALVAR",command=self.save_item_edits,bg=p["BLUE"],fg="white",relief="flat",font=("Segoe UI",8,"bold"),pady=7).pack(fill="x",padx=12,pady=2)
        actions=tk.Frame(right,bg=p["CARD"]);actions.pack(fill="x",padx=12,pady=2)
        tk.Button(actions,text="HISTÓRICO",command=self.open_history,bg=p["LIGHT_BLUE"],fg=p["LIGHT_BLUE_TXT"],relief="flat",font=("Segoe UI",7,"bold"),pady=6).pack(side="left",fill="x",expand=True,padx=(0,2))
        tk.Button(actions,text="IMAGEM",command=self.open_image,bg=p["GREEN"],fg=p["GREEN_TXT"],relief="flat",font=("Segoe UI",7,"bold"),pady=6).pack(side="left",fill="x",expand=True,padx=(2,0))
        self.margin_label=tk.Label(right,text="Margem: —",bg=p["ROW_ALT"],fg=p["MUTED"],justify="left",anchor="w",wraplength=270,padx=9,pady=7,font=("Segoe UI",7,"bold"));self.margin_label.pack(fill="x",padx=12,pady=(7,0))

        # Barra inferior fixa com ação principal.
        foot=tk.Frame(self,bg=p["CARD"],highlightbackground=p["LINE"],highlightthickness=1);foot.pack(fill="x",padx=22,pady=(0,16))
        tk.Label(foot,textvariable=self.info_var,bg=p["CARD"],fg=p["MUTED"],font=("Segoe UI",7)).pack(side="left",padx=12,pady=9)
        tk.Button(foot,text="EXPORTAR",command=self.export_excel,bg=p["ROW_ALT"],fg=p["TEXT"],relief="flat",font=("Segoe UI",7,"bold"),padx=10,pady=7).pack(side="right",padx=(4,10))
        tk.Button(foot,text="REVISAR E GERAR →",command=self.send_to_review,bg=p["BLUE"],fg="white",relief="flat",font=("Segoe UI",9,"bold"),padx=14,pady=8).pack(side="right",padx=4)
        tk.Button(foot,text="APROVAR",command=lambda:self.change_status("APROVADA"),bg=p["GREEN"],fg=p["GREEN_TXT"],relief="flat",font=("Segoe UI",7,"bold"),padx=10,pady=7).pack(side="right",padx=4)

    def choose_excel_profile(self):
        w=tk.Toplevel(self);w.title("Estrutura do Excel");w.configure(bg=self.p["CARD"]);w.transient(self);w.grab_set();w.resizable(False,False)
        body=tk.Frame(w,bg=self.p["CARD"]);body.pack(fill="both",expand=True,padx=18,pady=16)
        tk.Label(body,text="Estrutura ao exportar",bg=self.p["CARD"],fg=self.p["TEXT"],font=("Segoe UI",11,"bold")).pack(anchor="w")
        tk.Label(body,text="Automático usa o modelo correspondente ao nome da campanha.",bg=self.p["CARD"],fg=self.p["MUTED"],font=("Segoe UI",8)).pack(anchor="w",pady=(3,8))
        combo=ttk.Combobox(body,textvariable=self.excel_profile_var,values=profile_choices(),state="readonly",width=38);combo.pack(fill="x")
        tk.Button(body,text="OK",command=w.destroy,bg=self.p["BLUE"],fg="white",relief="flat",font=("Segoe UI",8,"bold"),pady=7).pack(fill="x",pady=(12,0))
        center_toplevel(w,self,470,180)

    def open_editor(self):
        if self.current_index() is None:
            messagebox.showinfo("Montador","Selecione um produto da campanha para editar.",parent=self);return
        if not self.editor_visible:
            self.body_pane.add(self.editor_panel,minsize=245,width=285);self.editor_visible=True
        self.show_item()

    def close_editor(self):
        if self.editor_visible:
            try:self.body_pane.forget(self.editor_panel)
            except Exception:pass
            self.editor_visible=False

    def refresh_catalog(self):
        if not hasattr(self,"catalog_tree"):return
        self.catalog_tree.delete(*self.catalog_tree.get_children());self.catalog_records={}
        mode=self.catalog_mode.get();q=self.search_var.get();cat=self.category_var.get()
        rows=catalog_families(q) if mode=="FAMÍLIAS" else catalog_products(q,cat)
        for i,r in enumerate(rows):
            iid=f"C{i}";self.catalog_records[iid]=r
            img="✓" if (r.get("image_info") or {}).get("official_path") else "—"
            self.catalog_tree.insert("","end",iid=iid,values=(r.get("codigo","") or r.get("codigo_ciss","") or "",r.get("canonical_name",""),img))

    def _item_key(self,x):return str(x.get("identity_key") or x.get("codigo") or norm(x.get("produto")))

    def add_selected(self):
        sels=self.catalog_tree.selection()
        if not sels:return
        existing={self._item_key(x) for x in self.items}
        added=0
        for iid in sels:
            r=self.catalog_records.get(iid)
            if not r:continue
            key=self._item_key(r)
            if key in existing:continue
            snap=history_snapshot(r.get("codigo"),r.get("canonical_name"),r.get("identity_key"))
            self.items.append({"identity_key":r.get("identity_key",""),"codigo":r.get("codigo","") or "","produto":r.get("canonical_name","") or "","categoria":r.get("categoria") or guess_category(r.get("canonical_name")) or "SEM CATEGORIA","custo":snap["last_cost"],"varejo":snap["last_varejo"],"promocao":"","clube":"","unidade":r.get("unidade") or "UN","limite":"","copies":1})
            existing.add(key);added+=1
        self.refresh_items();self.info_var.set(f"{added} produto(s) adicionado(s).")

    def refresh_items(self):
        if not hasattr(self,"items_tree"):return
        self.items_tree.delete(*self.items_tree.get_children())
        for i,x in enumerate(self.items):
            tags=smart_tags(x);x["tags"]=tags
            self.items_tree.insert("","end",iid=str(i),values=(x.get("produto",""),x.get("promocao",""),x.get("clube",""),x.get("unidade","UN"),", ".join(tags[:2]) or "OK"))
        self.count_label.config(text=f"{len(self.items)} itens")

    def selected_indices(self):return [int(x) for x in self.items_tree.selection() if str(x).isdigit() and int(x)<len(self.items)]
    def current_index(self):
        a=self.selected_indices();return a[0] if a else None

    def show_item(self):
        idx=self.current_index()
        if idx is None:return
        x=self.items[idx];self.detail_title.config(text=x.get("produto",""))
        for k,v in self.fields.items():v.set(str(x.get(k) or ""))
        self.unit_var.set(x.get("unidade") or "UN");self.update_margin(x)

    def update_margin(self,x):
        cost=dec(x.get("custo"));price=dec(x.get("clube")) or dec(x.get("promocao"));varejo=dec(x.get("varejo"))
        lines=[]
        if cost is not None and price is not None:
            diff=price-cost;pct=(diff/cost*100) if cost else 0
            lines.append(f"Margem sobre custo: R$ {money(diff)} • {pct:.1f}%")
        if varejo is not None and price is not None:
            lines.append(f"Diferença para varejo: R$ {money(varejo-price)}")
        self.margin_label.config(text="\n".join(lines) if lines else "Margem: informe custo e preço promocional.")

    def save_item_edits(self):
        idx=self.current_index()
        if idx is None:return
        x=self.items[idx]
        for k,v in self.fields.items():x[k]=v.get().strip()
        x["unidade"]=self.unit_var.get();self.refresh_items();self.items_tree.selection_set(str(idx));self.show_item()

    def remove_selected(self):
        idxs=set(self.selected_indices())
        if not idxs:return
        self.items=[x for i,x in enumerate(self.items) if i not in idxs];self.refresh_items()

    def use_last_price_selected(self):
        idxs=self.selected_indices()
        if not idxs:return
        for i in idxs:
            x=self.items[i];snap=history_snapshot(x.get("codigo"),x.get("produto"),x.get("identity_key"))
            if snap["last_promo"]:x["promocao"]=snap["last_promo"]
            if snap["last_club"]:x["clube"]=snap["last_club"]
            if snap["last_cost"]:x["custo"]=snap["last_cost"]
            if snap["last_varejo"]:x["varejo"]=snap["last_varejo"]
        self.refresh_items();self.info_var.set("Últimos preços aplicados aos itens selecionados.")

    def bulk_edit(self):
        idxs=self.selected_indices()
        if not idxs:
            messagebox.showinfo("Edição em massa","Selecione os produtos que deseja alterar.",parent=self);return
        w=tk.Toplevel(self);w.title("Montador • Edição em Massa");w.configure(bg=self.p["APP_BG"]);w.transient(self);w.grab_set();w.geometry("470x390")
        vars={k:tk.StringVar() for k in ("custo","varejo","promocao","clube","limite")};unit=tk.StringVar(value="NÃO ALTERAR")
        tk.Label(w,text=f"Editar {len(idxs)} produto(s)",bg=self.p["APP_BG"],fg=self.p["TEXT"],font=("Segoe UI",14,"bold")).pack(anchor="w",padx=16,pady=(14,10))
        for k,l in (("custo","Custo"),("varejo","Varejo"),("promocao","Promoção"),("clube","Clube"),("limite","Limite")):
            row=tk.Frame(w,bg=self.p["APP_BG"]);row.pack(fill="x",padx=16,pady=3);tk.Label(row,text=l,bg=self.p["APP_BG"],fg=self.p["MUTED"],width=12,anchor="w").pack(side="left");tk.Entry(row,textvariable=vars[k],bg=self.p["ROW_ALT"],fg=self.p["TEXT"],insertbackground=self.p["TEXT"],relief="flat").pack(side="left",fill="x",expand=True,ipady=5)
        row=tk.Frame(w,bg=self.p["APP_BG"]);row.pack(fill="x",padx=16,pady=3);tk.Label(row,text="Unidade",bg=self.p["APP_BG"],fg=self.p["MUTED"],width=12,anchor="w").pack(side="left");ttk.Combobox(row,textvariable=unit,values=("NÃO ALTERAR",)+UNIT_OPTIONS,state="readonly").pack(side="left",fill="x",expand=True)
        tk.Label(w,text="Campos vazios não serão alterados.",bg=self.p["APP_BG"],fg=self.p["MUTED"],font=("Segoe UI",8)).pack(anchor="w",padx=16,pady=8)
        def apply():
            for i in idxs:
                for k,v in vars.items():
                    if v.get().strip():self.items[i][k]=v.get().strip()
                if unit.get()!="NÃO ALTERAR":self.items[i]["unidade"]=unit.get()
            w.destroy();self.refresh_items();self.info_var.set(f"Edição em massa aplicada em {len(idxs)} item(ns).")
        tk.Button(w,text="APLICAR",command=apply,bg=self.p["BLUE"],fg="white",relief="flat",font=("Segoe UI",8,"bold"),pady=7).pack(fill="x",padx=16,pady=8)

    def suggest(self):
        camp=self.campaign_var.get().strip()
        if not camp:
            messagebox.showinfo("Sugestões","Informe primeiro o nome da campanha, por exemplo TERÇA VERDE.",parent=self);return
        rows=suggested_products(camp,30)
        if not rows:
            messagebox.showinfo("Sugestões","Ainda não existe histórico suficiente para sugerir produtos para esta campanha.",parent=self);return
        w=tk.Toplevel(self);w.title("Sugestões Automáticas");w.configure(bg=self.p["APP_BG"]);w.transient(self);w.grab_set();w.geometry("760x560")
        tk.Label(w,text=f"Sugestões para {camp.upper()}",bg=self.p["APP_BG"],fg=self.p["TEXT"],font=("Segoe UI",15,"bold")).pack(anchor="w",padx=16,pady=(14,5))
        tree=ttk.Treeview(w,columns=("codigo","prod","vezes","ultima"),show="headings",selectmode="extended")
        for c,t,ww in (("codigo","Código",90),("prod","Produto",390),("vezes","Vezes",60),("ultima","Última promoção",140)):tree.heading(c,text=t);tree.column(c,width=ww,anchor="w")
        tree.pack(fill="both",expand=True,padx=16,pady=8)
        for i,r in enumerate(rows):tree.insert("","end",iid=str(i),values=(r.get("codigo",""),r.get("canonical_name",""),r.get("vezes",0),str(r.get("ultima","") or "")[:10]))
        tree.selection_set(tree.get_children())
        def add():
            existing={self._item_key(x) for x in self.items};n=0
            for iid in tree.selection():
                r=rows[int(iid)];key=self._item_key(r)
                if key in existing:continue
                snap=history_snapshot(r.get("codigo"),r.get("canonical_name"),r.get("identity_key"))
                self.items.append({"identity_key":r.get("identity_key",""),"codigo":r.get("codigo","") or "","produto":r.get("canonical_name","") or "","categoria":r.get("categoria") or "SEM CATEGORIA","custo":snap["last_cost"],"varejo":snap["last_varejo"],"promocao":snap["last_promo"],"clube":snap["last_club"],"unidade":r.get("unidade") or "UN","limite":"","copies":1});existing.add(key);n+=1
            w.destroy();self.refresh_items();self.info_var.set(f"{n} sugestão(ões) adicionada(s) com os últimos preços disponíveis.")
        tk.Button(w,text="ADICIONAR SELECIONADOS",command=add,bg=self.p["GREEN"],fg=self.p["GREEN_TXT"],relief="flat",font=("Segoe UI",8,"bold"),pady=7).pack(fill="x",padx=16,pady=(0,14))

    def save_draft(self):
        if not self.campaign_var.get().strip():
            messagebox.showinfo("Montador","Informe o nome da campanha.",parent=self);return False
        self.campaign_id=save_campaign(self.campaign_id,self.campaign_var.get(),self.validity_var.get(),self.status_var.get(),self.items)
        self.info_var.set(f"Campanha salva • ID {self.campaign_id} • {len(self.items)} produtos.");return True

    def change_status(self,status):
        self.status_var.set(status)
        if self.save_draft():self.info_var.set(f"Campanha marcada como {status}.")

    def open_campaign_dialog(self):
        built=campaign_rows();hist=historical_campaign_names()
        w=tk.Toplevel(self);w.title("Abrir / Duplicar Promoção");w.configure(bg=self.p["APP_BG"]);w.transient(self);w.grab_set();w.geometry("880x580")
        tabs=ttk.Notebook(w);tabs.pack(fill="both",expand=True,padx=14,pady=14)
        a=tk.Frame(tabs,bg=self.p["APP_BG"]);b=tk.Frame(tabs,bg=self.p["APP_BG"]);tabs.add(a,text="Campanhas do Montador");tabs.add(b,text="Histórico")
        ta=ttk.Treeview(a,columns=("name","valid","status","date"),show="headings",selectmode="browse")
        for c,t,ww in (("name","Campanha",350),("valid","Validade",120),("status","Status",140),("date","Atualizada",160)):ta.heading(c,text=t);ta.column(c,width=ww,anchor="w")
        ta.pack(fill="both",expand=True,padx=10,pady=10)
        for r in built:ta.insert("","end",iid=str(r["id"]),values=(r["name"],r["validity"],r["status"],r["updated_at"][:16].replace("T"," ")))
        def open_saved(duplicate=False):
            sel=ta.selection();
            if not sel:return
            c,items=load_campaign(int(sel[0]));w.destroy();self.campaign_id=None if duplicate else c["id"];self.campaign_var.set(("CÓPIA - "+c["name"]) if duplicate else c["name"]);self.validity_var.set(c["validity"] or "");self.status_var.set("RASCUNHO" if duplicate else c["status"]);self.items=items;self.refresh_items();self.info_var.set("Campanha duplicada como rascunho." if duplicate else "Campanha carregada.")
        row=tk.Frame(a,bg=self.p["APP_BG"]);row.pack(fill="x",padx=10,pady=(0,10));tk.Button(row,text="ABRIR",command=lambda:open_saved(False),bg=self.p["BLUE"],fg="white",relief="flat",padx=12,pady=6).pack(side="left");tk.Button(row,text="DUPLICAR",command=lambda:open_saved(True),bg=self.p["PURPLE"],fg=self.p["PURPLE_TXT"],relief="flat",padx=12,pady=6).pack(side="left",padx=6)
        tb=ttk.Treeview(b,columns=("name","n","date"),show="headings",selectmode="browse");tb.heading("name",text="Campanha");tb.heading("n",text="Registros");tb.heading("date",text="Última ocorrência");tb.column("name",width=470);tb.column("n",width=80);tb.column("date",width=180);tb.pack(fill="both",expand=True,padx=10,pady=10)
        for i,r in enumerate(hist):tb.insert("","end",iid=str(i),values=(r["campanha"],r["n"],r["dt"][:16].replace("T"," ")))
        def duplicate_hist():
            sel=tb.selection();
            if not sel:return
            name=hist[int(sel[0])]["campanha"];items=historical_campaign_items(name);w.destroy();self.campaign_id=None;self.campaign_var.set(name);self.status_var.set("RASCUNHO");self.items=items;self.refresh_items();self.info_var.set(f"Promoção histórica duplicada • {len(items)} produtos. Atualize preços e validade.")
        tk.Button(b,text="USAR COMO NOVA PROMOÇÃO",command=duplicate_hist,bg=self.p["GREEN"],fg=self.p["GREEN_TXT"],relief="flat",pady=7).pack(fill="x",padx=10,pady=(0,10))

    def open_history(self):
        idx=self.current_index()
        if idx is None:return
        x=self.items[idx];self.app.show_product_history_dialog(x.get("codigo"),x.get("produto"))

    def open_image(self):
        idx=self.current_index()
        if idx is None:return
        x=self.items[idx]
        row={"identity_key":x.get("identity_key"),"codigo":x.get("codigo"),"canonical_name":x.get("produto"),"occurrence_count":history_snapshot(x.get("codigo"),x.get("produto"),x.get("identity_key"))["count"]}
        ProductImageManager(self,row,self.p)

    def export_excel(self):
        if not self.items:
            messagebox.showinfo("Exportar","Adicione produtos antes de exportar.",parent=self);return
        path=filedialog.asksaveasfilename(title="Exportar promoção",defaultextension=".xlsx",filetypes=[("Excel","*.xlsx")],initialfile=re.sub(r'[^A-Za-z0-9 _-]+','',self.campaign_var.get())[:60] or "Promocao",parent=self)
        if not path:return
        try:
            n=refresh_ciss_values(self.items);self.refresh_items()
            _,modelo=export_campaign_xlsx(path,self.campaign_var.get(),self.validity_var.get(),self.items,self.excel_profile_var.get())
            extra=f" • {n} custo/varejo atualizado(s) pelo CISS" if n else " • custo/varejo conferidos no CISS"
            self.info_var.set(f"Excel exportado no modelo {modelo}: {Path(path).name}{extra}")
        except Exception as e:
            messagebox.showerror("Exportar Excel",str(e),parent=self)

    def send_to_review(self):
        if not self.items:
            messagebox.showinfo("Montador","Adicione produtos à promoção.",parent=self);return
        n=refresh_ciss_values(self.items);self.refresh_items()
        if n:self.info_var.set(f"{n} item(ns) tiveram custo/varejo atualizados pelo relatório 208 antes da revisão.")
        missing=[x["produto"] for x in self.items if not str(x.get("promocao") or "").strip() and not str(x.get("clube") or "").strip()]
        if missing and not messagebox.askyesno("Produtos sem preço",f"{len(missing)} produto(s) estão sem preço de Promoção/Clube e serão ignorados.\n\nContinuar?",parent=self):return
        self.status_var.set("EM REVISÃO");self.save_draft()
        jobs=build_jobs(self.items,self.campaign_var.get(),self.validity_var.get(),self.campaign_id)
        if not jobs:
            messagebox.showwarning("Montador","Nenhum produto com preço promocional foi encontrado.",parent=self);return
        self.app.load_builder_jobs(jobs,self.campaign_var.get(),self.validity_var.get(),self.campaign_id)
