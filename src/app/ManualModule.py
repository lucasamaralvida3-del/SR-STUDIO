# -*- coding: utf-8 -*-
import os, tempfile, threading, time, math, sqlite3
from pathlib import Path
from decimal import Decimal, InvalidOperation
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from ui_v2 import choose_palette, add_tooltip, print_pdf, default_printer_name, center_toplevel
from AtacadoModule import run_engine as atacado_run_engine, generate_preview as atacado_preview, latest_atacado_posters
from SRStudio21 import dated_output_dir, smart_pdf_name, unique_path, record_reprint, record_product_jobs, PRODUCT_DB, norm, apply_learned_correction
from SRSpellCheck import correct_campaign_text

PAL=choose_palette("Automático")
APP_BG=PAL["APP_BG"]; CARD=PAL["CARD"]; TEXT=PAL["TEXT"]; MUTED=PAL["MUTED"]; LINE=PAL["LINE"]
BLUE=PAL["BLUE"]; BLUE2=PAL["BLUE2"]; GREEN=PAL["GREEN"]; GREEN_TXT=PAL["GREEN_TXT"]
LIGHT_BLUE=PAL["LIGHT_BLUE"]; LIGHT_BLUE_TXT=PAL["LIGHT_BLUE_TXT"]; RED=PAL["RED"]; RED_TXT=PAL["RED_TXT"]
ORANGE=PAL["ORANGE"]; ORANGE_TXT=PAL["ORANGE_TXT"]

UNIT_OPTIONS=["UN","KG","À LATA","À GARRAFA"]
VALIDITY_OPTIONS=["VÁLIDO DE","VÁLIDO SOMENTE"]

# Cache leve usado pelo Cartaz Venda. É carregado durante a abertura do SR Studio
# para que a seleção de produtos não precise consultar/processar o banco ao entrar na tela.
_SALE_CATALOG_CACHE=[]
_SALE_CATALOG_READY=False
_SALE_CATALOG_LOCK=threading.Lock()

def preload_sale_catalog(force=False):
    global _SALE_CATALOG_CACHE,_SALE_CATALOG_READY
    with _SALE_CATALOG_LOCK:
        if _SALE_CATALOG_READY and not force:
            return len(_SALE_CATALOG_CACHE)
        rows=[]
        try:
            con=sqlite3.connect(PRODUCT_DB)
            con.row_factory=sqlite3.Row
            exists=con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='catalog_products'").fetchone()
            if exists:
                cols={r[1] for r in con.execute("PRAGMA table_info(catalog_products)").fetchall()}
                wanted=[
                    'identity_key','codigo','canonical_name','canonical_norm','unidade',
                    'codigo_ciss','preco_varejo_atual','custo_reposicao','categoria','active'
                ]
                selected=[c for c in wanted if c in cols]
                if selected:
                    sql='SELECT '+','.join(selected)+' FROM catalog_products'
                    if 'active' in cols: sql+=' WHERE active=1'
                    sql+=' ORDER BY canonical_name COLLATE NOCASE'
                    rows=[dict(r) for r in con.execute(sql).fetchall()]
            con.close()
        except Exception:
            rows=[]
        for r in rows:
            r.setdefault('canonical_norm',norm(r.get('canonical_name')))
            r['_search_norm']=norm(' '.join(str(r.get(k) or '') for k in ('canonical_name','codigo','codigo_ciss')))
        _SALE_CATALOG_CACHE=rows
        _SALE_CATALOG_READY=True
        return len(rows)

def sale_catalog_products(search='',limit=1000):
    if not _SALE_CATALOG_READY:
        preload_sale_catalog()
    q=norm(search)
    if not q:
        return list(_SALE_CATALOG_CACHE[:limit])
    out=[]
    for r in _SALE_CATALOG_CACHE:
        if q in str(r.get('_search_norm') or ''):
            out.append(r)
            if len(out)>=limit:break
    return out

def money(v):
    s=str(v or "").strip().replace("R$","").replace(" ","")
    if not s:return ""
    if "," in s and "." in s:s=s.replace(".","").replace(",",".")
    elif "," in s:s=s.replace(",",".")
    try:d=Decimal(s);return f"{d:.2f}".replace(".",",")
    except InvalidOperation:return str(v).strip()

def sale_unit(v):
    u=str(v or "").strip().upper()
    aliases={
        "CADA":"UN","UNID":"UN","UNIDADE":"UN","UND":"UN",
        "LATA":"À LATA","A LATA":"À LATA","Á LATA":"À LATA",
        "GARRAFA":"À GARRAFA","A GARRAFA":"À GARRAFA","Á GARRAFA":"À GARRAFA",
    }
    u=aliases.get(u,u)
    return u if u in {"KG","UN","À LATA","À GARRAFA"} else "UN"

class ManualPanel(tk.Frame):
    def __init__(self,master,app,promo_generate,promo_preview):
        super().__init__(master,bg=APP_BG)
        self.app=app; self.promo_generate=promo_generate; self.promo_preview=promo_preview
        self.kind=tk.StringVar(value="Promoção - 1 preço")
        self.product=tk.StringVar(); self.headline=tk.StringVar(value="OFERTA"); self.promo=tk.StringVar(); self.club=tk.StringVar(); self.unit=tk.StringVar(value="UN")
        self.validity_label=tk.StringVar(value="VÁLIDO SOMENTE"); self.validity=tk.StringVar(); self.limit=tk.StringVar()
        self.retail=tk.StringVar(); self.qty=tk.StringVar(value="6"); self.wholesale=tk.StringVar(); self.total=tk.StringVar(value="0,00")
        self.atacado_search=tk.StringVar(); self.atacado_selected=None; self.atacado_rows={}
        self.sale_search=tk.StringVar(); self.sale_selected=None; self.sale_rows={}
        self.status=tk.StringVar(value="Preencha os dados para gerar um cartaz manual.")
        self.printer=tk.StringVar(value=default_printer_name())
        self.busy=False; self.build(); self.kind.trace_add("write",lambda *_:self.render_fields())
        for v in [self.qty,self.wholesale]:v.trace_add("write",lambda *_:self.calc_total())
    def build(self):
        canvas=tk.Canvas(self,bg=APP_BG,highlightthickness=0); sb=ttk.Scrollbar(self,orient="vertical",command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set);canvas.pack(side="left",fill="both",expand=True);sb.pack(side="right",fill="y")
        outer=tk.Frame(canvas,bg=APP_BG);win=canvas.create_window((0,0),window=outer,anchor="nw")
        outer.bind("<Configure>",lambda e:canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",lambda e:canvas.itemconfigure(win,width=e.width))
        tk.Label(outer,text="Geração Manual",bg=APP_BG,fg=TEXT,font=("Segoe UI",20,"bold")).pack(anchor="w",padx=26,pady=(18,10))
        select=tk.Frame(outer,bg=CARD,highlightbackground=LINE,highlightthickness=1);select.pack(fill="x",padx=26)
        tk.Label(select,text="Escolha o modelo",bg=CARD,fg=MUTED,font=("Segoe UI",8,"bold")).pack(side="left",padx=(16,8),pady=12)
        combo=ttk.Combobox(select,textvariable=self.kind,state="readonly",values=["Promoção - 1 preço","Promoção - 2 preços","Clube Exclusivo","Atacado","Cartaz Venda"],width=32)
        combo.pack(side="left",padx=(0,16),pady=10); add_tooltip(combo,"Selecione o tipo de cartaz. A tela mostra somente os campos necessários para o modelo escolhido.")
        self.fields=tk.Frame(outer,bg=APP_BG);self.fields.pack(fill="x",padx=26,pady=12)
        self.actions=tk.Frame(outer,bg=CARD,highlightbackground=LINE,highlightthickness=1);self.actions.pack(fill="x",padx=26,pady=(0,24))
        outrow=tk.Frame(self.actions,bg=CARD);outrow.pack(fill="x",padx=16,pady=(10,2))
        tk.Label(outrow,text="Saída",bg=CARD,fg=TEXT,font=("Segoe UI",10,"bold")).pack(side="left")
        pr=tk.Label(outrow,text="● Impressora pronta",bg=GREEN,fg=GREEN_TXT,font=("Segoe UI",7,"bold"),padx=8,pady=3);pr.pack(side="right");add_tooltip(pr,self.printer.get())
        self.progress=ttk.Progressbar(self.actions,maximum=100,style="SR.Horizontal.TProgressbar");self.progress.pack(fill="x",padx=16,pady=(10,4))
        tk.Label(self.actions,textvariable=self.status,bg=CARD,fg=MUTED,font=("Segoe UI",8),wraplength=800,justify="left").pack(fill="x",padx=16,pady=(0,8))
        bar=tk.Frame(self.actions,bg=CARD);bar.pack(fill="x",padx=16,pady=(0,15))
        self.preview_btn=tk.Button(bar,text="PRÉVIA REAL",command=self.preview,bg=LIGHT_BLUE,fg=LIGHT_BLUE_TXT,relief="flat",font=("Segoe UI",8,"bold"),padx=12,pady=8);self.preview_btn.pack(side="left")
        self.save_btn=tk.Button(bar,text="SALVAR PDF",command=lambda:self.generate("save"),bg=BLUE,fg="white",relief="flat",font=("Segoe UI",8,"bold"),padx=14,pady=8);self.save_btn.pack(side="right",padx=(5,0))
        self.print_btn=tk.Button(bar,text="IMPRIMIR",command=lambda:self.generate("print"),bg=GREEN,fg=GREEN_TXT,relief="flat",font=("Segoe UI",8,"bold"),padx=14,pady=8);self.print_btn.pack(side="right",padx=5)
        self.both_btn=tk.Button(bar,text="SALVAR E IMPRIMIR",command=lambda:self.generate("both"),bg=ORANGE,fg=ORANGE_TXT,relief="flat",font=("Segoe UI",8,"bold"),padx=14,pady=8);self.both_btn.pack(side="right",padx=5)
        self.render_fields()
    def field(self,parent,label,var,row,col=0,values=None,width=1):
        f=tk.Frame(parent,bg=CARD);f.grid(row=row,column=col,columnspan=width,sticky="ew",padx=7,pady=6)
        tk.Label(f,text=label,bg=CARD,fg=TEXT,font=("Segoe UI",8,"bold")).pack(anchor="w")
        if values is not None:w=ttk.Combobox(f,textvariable=var,state="readonly",values=values)
        else:w=tk.Entry(f,textvariable=var,bg=PAL["ROW_ALT"],fg=TEXT,insertbackground=TEXT,relief="flat",font=("Segoe UI",9))
        w.pack(fill="x",pady=(4,0),ipady=4 if isinstance(w,tk.Entry) else 0);return w
    def render_fields(self):
        for w in self.fields.winfo_children():w.destroy()
        card=tk.Frame(self.fields,bg=CARD,highlightbackground=LINE,highlightthickness=1);card.pack(fill="x")
        card.grid_columnconfigure(0,weight=1);card.grid_columnconfigure(1,weight=1)
        kind=self.kind.get()
        if kind=="Atacado":
            self.render_atacado_selector(card)
            return
        if kind=="Cartaz Venda":
            self.render_sale_selector(card)
            return
        self.field(card,"Produto",self.product,0,0,width=2)
        row0=1
        if kind in {"Promoção - 1 preço","Promoção - 2 preços"}:
            en=self.field(card,"Enunciado do cartaz",self.headline,1,0,width=2)
            add_tooltip(en,"Texto que aparece no campo de campanha/enunciado do modelo, por exemplo: OFERTA ESPECIAL, TERÇA VERDE ou FIM DE SEMANA.")
            row0=2
        if kind=="Promoção - 2 preços":
            self.field(card,"Preço promoção",self.promo,row0,0);self.field(card,"Preço Clube",self.club,row0,1)
        elif kind=="Clube Exclusivo":
            self.field(card,"Preço Clube",self.club,row0,0);self.field(card,"Unidade visual",self.unit,row0,1,UNIT_OPTIONS)
        else:
            self.field(card,"Preço promoção",self.promo,row0,0);self.field(card,"Unidade",self.unit,row0,1,UNIT_OPTIONS)
        self.field(card,"Tipo de validade",self.validity_label,row0+1,0,VALIDITY_OPTIONS);self.field(card,"Período/data",self.validity,row0+1,1)
        self.field(card,"Limite por CPF (opcional)",self.limit,row0+2,0,width=2)
    def render_atacado_selector(self,card):
        for c in range(2):card.grid_columnconfigure(c,weight=1)
        info=tk.Frame(card,bg=CARD);info.grid(row=0,column=0,columnspan=2,sticky="ew",padx=12,pady=(12,6))
        tk.Label(info,text="Selecione um produto do Atacado",bg=CARD,fg=TEXT,font=("Segoe UI",11,"bold")).pack(anchor="w")
        hint=tk.Label(info,text="ⓘ Dados do último Atacado",bg=CARD,fg=BLUE2,font=("Segoe UI",8,"bold"));hint.pack(anchor="w",pady=(2,0));add_tooltip(hint,"Preço, quantidade mínima, unidade e total vêm do relatório Atacado mais recente.")
        search=tk.Frame(card,bg=CARD);search.grid(row=1,column=0,columnspan=2,sticky="ew",padx=12,pady=6)
        e=tk.Entry(search,textvariable=self.atacado_search,bg=PAL["ROW_ALT"],fg=TEXT,insertbackground=TEXT,relief="flat",font=("Segoe UI",9))
        e.pack(side="left",fill="x",expand=True,ipady=5);e.bind("<KeyRelease>",lambda ev:self.refresh_atacado_catalog())
        tk.Button(search,text="↻",command=self.refresh_atacado_catalog,bg=LIGHT_BLUE,fg=LIGHT_BLUE_TXT,relief="flat",font=("Segoe UI",8,"bold"),padx=10,pady=6).pack(side="left",padx=(6,0))
        holder=tk.Frame(card,bg=CARD);holder.grid(row=2,column=0,columnspan=2,sticky="nsew",padx=12,pady=(0,6));card.grid_rowconfigure(2,weight=1)
        cols=("produto","varejo","qtd","unit","atacado","total","status")
        self.atacado_tree=ttk.Treeview(holder,columns=cols,show="headings",selectmode="browse",height=11)
        specs=(("produto","Produto",330),("varejo","Varejo",80),("qtd","Qtd.",65),("unit","Unid.",55),("atacado","Atacado",80),("total","Total",80),("status","Status",105))
        for c,label,w in specs:self.atacado_tree.heading(c,text=label);self.atacado_tree.column(c,width=w,anchor="w" if c=="produto" else "center")
        sb=ttk.Scrollbar(holder,orient="vertical",command=self.atacado_tree.yview);self.atacado_tree.configure(yscrollcommand=sb.set)
        self.atacado_tree.pack(side="left",fill="both",expand=True);sb.pack(side="right",fill="y")
        self.atacado_tree.bind("<Double-1>",lambda e:self.choose_atacado_product())
        self.atacado_tree.bind("<<TreeviewSelect>>",lambda e:self.choose_atacado_product(silent=True))
        action=tk.Frame(card,bg=CARD);action.grid(row=3,column=0,columnspan=2,sticky="ew",padx=12,pady=(2,8))
        tk.Button(action,text="USAR SELECIONADO",command=self.choose_atacado_product,bg=BLUE,fg="white",relief="flat",font=("Segoe UI",8,"bold"),padx=12,pady=7).pack(side="left")
        self.atacado_summary=tk.Label(action,text="Nenhum produto selecionado.",bg=CARD,fg=MUTED,font=("Segoe UI",8),justify="left",anchor="w",wraplength=570)
        self.atacado_summary.pack(side="left",fill="x",expand=True,padx=10)
        self.refresh_atacado_catalog()

    def render_sale_selector(self,card):
        for c in range(2):card.grid_columnconfigure(c,weight=1)
        info=tk.Frame(card,bg=CARD);info.grid(row=0,column=0,columnspan=2,sticky="ew",padx=12,pady=(12,6))
        tk.Label(info,text="Selecione um produto do Banco de Dados",bg=CARD,fg=TEXT,font=("Segoe UI",11,"bold")).pack(anchor="w")
        hint=tk.Label(info,text="ⓘ Nome + preço de venda + unidade",bg=CARD,fg=BLUE2,font=("Segoe UI",8,"bold"));hint.pack(anchor="w",pady=(2,0));add_tooltip(hint,"O restante do modelo Cartaz Venda permanece fixo. A unidade aceita KG, UN, À LATA e À GARRAFA.")

        search=tk.Frame(card,bg=CARD);search.grid(row=1,column=0,columnspan=2,sticky="ew",padx=12,pady=6)
        e=tk.Entry(search,textvariable=self.sale_search,bg=PAL["ROW_ALT"],fg=TEXT,insertbackground=TEXT,relief="flat",font=("Segoe UI",9))
        e.pack(side="left",fill="x",expand=True,ipady=5);e.bind("<KeyRelease>",lambda ev:self.refresh_sale_catalog())
        tk.Button(search,text="↻",command=lambda:self.refresh_sale_catalog(force=True),bg=LIGHT_BLUE,fg=LIGHT_BLUE_TXT,relief="flat",font=("Segoe UI",8,"bold"),padx=10,pady=6).pack(side="left",padx=(6,0))

        holder=tk.Frame(card,bg=CARD);holder.grid(row=2,column=0,columnspan=2,sticky="nsew",padx=12,pady=(0,6));card.grid_rowconfigure(2,weight=1)
        cols=("produto","unidade","varejo")
        self.sale_tree=ttk.Treeview(holder,columns=cols,show="headings",selectmode="browse",height=13)
        specs=(("produto","Produto",520),("unidade","Unidade",110),("varejo","Preço de Venda",130))
        for c,label,w in specs:self.sale_tree.heading(c,text=label);self.sale_tree.column(c,width=w,anchor="w" if c=="produto" else "center")
        sb=ttk.Scrollbar(holder,orient="vertical",command=self.sale_tree.yview);self.sale_tree.configure(yscrollcommand=sb.set)
        self.sale_tree.pack(side="left",fill="both",expand=True);sb.pack(side="right",fill="y")
        self.sale_tree.bind("<Double-1>",lambda e:self.choose_sale_product())
        self.sale_tree.bind("<<TreeviewSelect>>",lambda e:self.choose_sale_product(silent=True))

        action=tk.Frame(card,bg=CARD);action.grid(row=3,column=0,columnspan=2,sticky="ew",padx=12,pady=(2,12))
        tk.Button(action,text="USAR SELECIONADO",command=self.choose_sale_product,bg=BLUE,fg="white",relief="flat",font=("Segoe UI",8,"bold"),padx=12,pady=7).pack(side="left")
        self.sale_summary=tk.Label(action,text="Nenhum produto selecionado.",bg=CARD,fg=MUTED,font=("Segoe UI",8),justify="left",anchor="w",wraplength=600)
        self.sale_summary.pack(side="left",fill="x",expand=True,padx=10)
        self.refresh_sale_catalog()

    def refresh_sale_catalog(self,force=False):
        if not hasattr(self,"sale_tree"):return
        if force:preload_sale_catalog(force=True)
        rows=sale_catalog_products(self.sale_search.get(),1000)
        self.sale_tree.delete(*self.sale_tree.get_children());self.sale_rows={}
        for i,r in enumerate(rows):
            iid=f"S{i}";self.sale_rows[iid]=r
            self.sale_tree.insert("","end",iid=iid,values=(r.get("canonical_name",""),sale_unit(r.get("unidade")),money(r.get("preco_varejo_atual"))))
        if not rows:
            self.sale_summary.config(text="Nenhum produto encontrado no banco. Atualize o Banco de Produtos pelo CISSPoder/planilhas.")
        else:
            self.sale_summary.config(text=f"{len(rows)} produto(s) encontrados. Selecione um para usar nome, unidade e preço de venda.")

    def choose_sale_product(self,silent=False):
        if not hasattr(self,"sale_tree"):return
        sel=self.sale_tree.selection()
        if not sel:
            if not silent:messagebox.showinfo("Cartaz Venda","Selecione um produto da lista.",parent=self)
            return
        r=self.sale_rows.get(sel[0])
        if not r:return
        self.sale_selected=dict(r)
        self.product.set(str(r.get("canonical_name") or ""))
        self.retail.set(money(r.get("preco_varejo_atual")))
        self.unit.set(sale_unit(r.get("unidade")))
        self.sale_summary.config(text=f"Selecionado: {self.product.get()}  •  {self.unit.get()}  •  R$ {self.retail.get() or '—'}",fg=TEXT)
        self.status.set("Cartaz Venda pronto: nome, preço de venda e unidade serão preenchidos automaticamente.")

    def refresh_atacado_catalog(self):
        if not hasattr(self,"atacado_tree"):return
        rows=latest_atacado_posters(self.atacado_search.get(),1000)
        self.atacado_tree.delete(*self.atacado_tree.get_children());self.atacado_rows={}
        for i,r in enumerate(rows):
            iid=f"A{i}";self.atacado_rows[iid]=r
            self.atacado_tree.insert("","end",iid=iid,values=(r.get("nome",""),r.get("varejo",""),r.get("quantidade",""),r.get("unidade",""),r.get("atacado",""),r.get("total",""),r.get("status","")))
        if not rows:
            self.atacado_summary.config(text="Nenhum produto encontrado. Importe primeiro o relatório 782 no módulo Atacado.")
        else:
            self.atacado_summary.config(text=f"{len(rows)} produto(s) disponíveis no último relatório Atacado. Pesquise e selecione apenas um.")

    def choose_atacado_product(self,silent=False):
        if not hasattr(self,"atacado_tree"):return
        sel=self.atacado_tree.selection()
        if not sel:
            if not silent:messagebox.showinfo("Geração Manual - Atacado","Selecione um produto da lista.",parent=self)
            return
        r=self.atacado_rows.get(sel[0])
        if not r:return
        self.atacado_selected=dict(r)
        self.product.set(str(r.get("nome") or ""));self.retail.set(str(r.get("varejo") or ""));self.qty.set(str(r.get("quantidade") or ""));self.unit.set(str(r.get("unidade") or "UN"));self.wholesale.set(str(r.get("atacado") or ""));self.total.set(str(r.get("total") or ""))
        codes=r.get("codigos") or []
        code_txt=", ".join(str(x) for x in codes[:4]) if codes else "—"
        self.atacado_summary.config(text=f"Selecionado: {r.get('nome','')}  •  Varejo R$ {r.get('varejo','')}  •  mínimo {r.get('quantidade','')} {r.get('unidade','')}  •  Atacado R$ {r.get('atacado','')}  •  códigos {code_txt}",fg=TEXT)
        self.status.set("Produto do Atacado selecionado. Use Prévia, Salvar PDF ou Imprimir.")

    def calc_total(self):
        try:
            q=Decimal(str(self.qty.get()).replace(",","."));w=Decimal(str(self.wholesale.get()).replace(",","."));self.total.set(money(q*w))
        except Exception:self.total.set("0,00")
    def promo_job(self):
        k=self.kind.get(); product=apply_learned_correction(self.product.get().strip())
        if product and product != self.product.get().strip(): self.product.set(product)
        if k=="Cartaz Venda":
            if not self.sale_selected:raise RuntimeError("Selecione um produto do Banco de Dados para o Cartaz Venda.")
            if not product:raise RuntimeError("Selecione um produto do Banco de Dados.")
            price=money(self.retail.get() or self.sale_selected.get("preco_varejo_atual"))
            if not price:raise RuntimeError("O produto selecionado não possui preço de venda atual no banco.")
            unit=sale_unit(self.unit.get() or self.sale_selected.get("unidade"))
            return {"id":"manual","campanha":"CARTAZ VENDA","produto":product,"produto_render":product,
                    "promocao":price,"clube":"","validade":"","tipo":4,
                    "entrada_original":unit,"unidade_exibicao":unit,"unidade_reconhecida":True,"limite":"",
                    "codigo":str(self.sale_selected.get("codigo") or self.sale_selected.get("codigo_ciss") or ""),
                    "custo":"","varejo":price,
                    "selected":True,"issues":[],"status":"OK","layout_status":"","layout_detail":"","layout_font":0,"sheet":"MANUAL","linha":0}
        if not product:raise RuntimeError("Informe o produto.")
        tipo=1 if k=="Promoção - 1 preço" else 2 if k=="Promoção - 2 preços" else 3
        if tipo==1 and not money(self.promo.get()):raise RuntimeError("Informe o preço promocional.")
        if tipo in {2,3} and not money(self.club.get()):raise RuntimeError("Informe o preço Clube.")
        if not self.validity.get().strip():raise RuntimeError("Informe a data/período de validade.")
        headline=correct_campaign_text(self.headline.get()) if tipo in {1,2} else "CLUBE SR"
        if tipo in {1,2} and not headline:raise RuntimeError("Informe o enunciado do cartaz.")
        return {"id":"manual","campanha":headline,"produto":product,"produto_render":product,
                "promocao":money(self.promo.get()),"clube":money(self.club.get()),"validade":self.validity.get().strip(),"tipo":tipo,
                "entrada_original":self.unit.get(),"unidade_exibicao":self.unit.get(),"unidade_reconhecida":True,"limite":self.limit.get().strip().upper(),
                "selected":True,"issues":[],"status":"OK","layout_status":"","layout_detail":"","layout_font":0,"sheet":"MANUAL","linha":0}
    def atacado_poster(self):
        if not self.atacado_selected:
            raise RuntimeError("Selecione um produto do relatório Atacado.")
        p=dict(self.atacado_selected)
        p["cartaz_chave"]="MANUAL_"+str(p.get("cartaz_chave") or p.get("nome") or "ATACADO")
        p["nome"]=apply_learned_correction(str(p.get("nome") or "").strip())
        p["varejo"]=money(p.get("varejo"));p["atacado"]=money(p.get("atacado"));p["total"]=money(p.get("total"))
        p["quantidade"]=str(p.get("quantidade") or "").strip();p["unidade"]=str(p.get("unidade") or "UN").strip().upper()
        p["agrupado"]=bool(p.get("agrupado"));p["status"]="MANUAL";p["selected"]=True;p["copies"]=1
        if not p["nome"] or not p["varejo"] or not p["atacado"] or not p["quantidade"]:
            raise RuntimeError("O produto selecionado está com dados incompletos no relatório Atacado.")
        return p
    def set_busy(self,v,text=None):
        self.busy=v
        for b in [self.preview_btn,self.save_btn,self.print_btn,self.both_btn]:b.config(state="disabled" if v else "normal")
        if text:self.status.set(text)
        self.app.busy=v
    def preview(self):
        if self.busy:return
        try: obj=self.atacado_poster() if self.kind.get()=="Atacado" else self.promo_job()
        except Exception as e:messagebox.showwarning("Geração manual",str(e));return
        self.set_busy(True,"Gerando prévia real no PowerPoint...");self.progress["value"]=20
        def worker():
            try:
                path=atacado_preview(obj) if self.kind.get()=="Atacado" else self.promo_preview(obj,self.validity_label.get())
                self.after(0,lambda:self.show_preview(path))
            except Exception as e:
                msg=str(e)
                self.after(0,lambda msg=msg:messagebox.showerror("Prévia",msg))
            finally:self.after(0,lambda:(self.set_busy(False,"Prévia concluída."),self.progress.config(value=100)))
        threading.Thread(target=worker,daemon=True).start()
    def show_preview(self,path):
        w=tk.Toplevel(self);w.title("Prévia real - Geração Manual");w.configure(bg=APP_BG)
        img=tk.PhotoImage(file=str(path));factor=max(1,math.ceil(max(img.width()/650,img.height()/720)));img=img.subsample(factor,factor);w._img=img
        tk.Label(w,image=img,bg=APP_BG).pack(padx=12,pady=12);center_toplevel(w,self.app,max(420,img.width()+24),max(480,img.height()+24))
    def generate(self,action):
        if self.busy:return
        try: obj=self.atacado_poster() if self.kind.get()=="Atacado" else self.promo_job()
        except Exception as e:messagebox.showwarning("Geração manual",str(e));return
        keep=action in {"save","both"}
        if keep:
            base=dated_output_dir("Manual",getattr(self.app,"ui_settings",{}));name=smart_pdf_name("Manual",self.product.get().strip() or "CARTAZ_MANUAL",self.validity.get())
            out=filedialog.asksaveasfilename(title="Salvar cartaz manual",defaultextension=".pdf",filetypes=[("PDF","*.pdf")],initialdir=str(base),initialfile=name)
            if not out:return
            out=unique_path(Path(out)) if Path(out).exists() else Path(out)
        else:
            out=Path(tempfile.gettempdir())/"SR_STUDIO_IMPRESSAO_MANUAL.pdf"
        self.set_busy(True,"Preparando PowerPoint...");self.progress["value"]=5;started=time.time()
        def prog(a,b,t):
            msg=("PDF criado • finalizando PowerPoint..." if b and a>=b else t)
            self.after(0,lambda:(self.progress.config(value=(a/b*100 if b else 30)),self.status.set(msg)))
        def worker():
            try:
                if self.kind.get()=="Atacado":
                    result=atacado_run_engine([obj],out,prog,threading.Event())
                else:
                    result=self.promo_generate([obj],out,self.validity_label.get(),prog,threading.Event())
                    if not result.get("output_created"):raise RuntimeError("O cartaz não foi criado.")
                if action in {"print","both"}:
                    kind="manual"
                    self.app.print_document(out,kind) if hasattr(self.app,"print_document") else print_pdf(out)
                try:
                    record_product_jobs([obj],"Manual",str(out));record_reprint("Manual",[out],1,self.product.get().strip() or "Cartaz Manual")
                except Exception:pass
                self.after(0,lambda:self.finish(action,out,time.time()-started))
            except Exception as e:
                msg=str(e)
                self.after(0,lambda msg=msg:self.fail(msg))
        threading.Thread(target=worker,daemon=True).start()
    def finish(self,action,out,elapsed):
        # Libera o estado antes de qualquer diálogo. Assim a navegação nunca fica presa
        # caso o PowerPoint tenha demorado para encerrar a sessão COM.
        self.busy=False; self.app.busy=False
        for b in [self.preview_btn,self.save_btn,self.print_btn,self.both_btn]:b.config(state="normal")
        self.status.set(f"✓ Concluído em {elapsed:.1f}s");self.progress["value"]=100
        self.update_idletasks()
        if action=="save":messagebox.showinfo("Geração manual",f"PDF salvo com sucesso.\n\n{out}")
        elif action=="print":messagebox.showinfo("Geração manual","Cartaz enviado para a impressora padrão do Windows.")
        else:messagebox.showinfo("Geração manual",f"PDF salvo e enviado para impressão.\n\n{out}")
    def fail(self,e):
        self.set_busy(False,str(e));self.progress["value"]=0;messagebox.showerror("Geração manual",str(e))
