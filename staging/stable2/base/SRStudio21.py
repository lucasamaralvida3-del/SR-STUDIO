# -*- coding: utf-8 -*-
"""Recursos do SR Studio: validações, histórico, fila, impressão e produtividade."""
import os, re, json, time, sqlite3, hashlib, shutil, tempfile, subprocess, unicodedata
from pathlib import Path
from decimal import Decimal, InvalidOperation
from datetime import datetime, timedelta
import tkinter as tk
from tkinter import ttk, messagebox

APP_DIR=Path(__file__).resolve().parent
LOCAL_ROOT=Path(os.environ.get("LOCALAPPDATA",str(APP_DIR)))
LOCAL_DATA=LOCAL_ROOT/"SR_Studio_2.0"
LOCAL_DATA.mkdir(parents=True,exist_ok=True)
CORRECTIONS_FILE=LOCAL_DATA/"correcoes_produtos.json"
QUEUE_FILE=LOCAL_DATA/"generation_queue.json"
REPRINT_FILE=LOCAL_DATA/"reprint_registry.json"
PRINT_PROFILES_FILE=LOCAL_DATA/"print_profiles.json"
PRODUCT_DB=LOCAL_DATA/"product_history.db"
QUEUE_WORK=LOCAL_DATA/"queue_work"
QUEUE_WORK.mkdir(parents=True,exist_ok=True)
MODEL_VERSIONS=APP_DIR/"modelos"/"versoes"
MODEL_VERSIONS.mkdir(parents=True,exist_ok=True)

try:
    from tkinterdnd2 import DND_FILES
    HAS_DND=True
except Exception:
    DND_FILES=None; HAS_DND=False


def load_json(path,default):
    try:
        if Path(path).exists():
            return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except Exception: pass
    return default

def save_json(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    tmp.replace(path)

def norm(v):
    s="" if v is None else str(v)
    s=unicodedata.normalize("NFD",s)
    s="".join(c for c in s if unicodedata.category(c)!="Mn")
    return re.sub(r"[^A-Z0-9]+"," ",s.upper()).strip()

def dec(v):
    if v in (None,""): return None
    if isinstance(v,Decimal):return v
    s=str(v).strip().replace("R$","").replace(" ","")
    if not s:return None
    if "," in s and "." in s:s=s.replace(".","").replace(",",".")
    elif "," in s:s=s.replace(",",".")
    try:return Decimal(s)
    except InvalidOperation:return None

def money(v):
    d=dec(v)
    return "" if d is None else f"{d:.2f}".replace(".",",")

# ----------------------------------------------------------------------
# Normalização + memória de correções
# ----------------------------------------------------------------------
def normalize_product_name(name):
    s=str(name or "").strip()
    s=re.sub(r"\s+"," ",s)
    s=re.sub(r"\s+([,.;:])",r"\1",s)
    # apenas normalizações seguras de unidade/medida
    s=re.sub(r"(?i)\b(\d+(?:[.,]\d+)?)\s+(ML|MG|KG|G)\b",r"\1\2",s)
    s=re.sub(r"(?i)\b(\d+(?:[.,]\d+)?)\s+L\b",r"\1L",s)
    return s.upper()

_CORRECTIONS_CACHE = None

def corrections(refresh=False):
    global _CORRECTIONS_CACHE
    if not refresh and isinstance(_CORRECTIONS_CACHE,dict):
        return dict(_CORRECTIONS_CACHE)
    d=load_json(CORRECTIONS_FILE,{})
    _CORRECTIONS_CACHE=d if isinstance(d,dict) else {}
    return dict(_CORRECTIONS_CACHE)

def apply_learned_correction(name):
    raw=normalize_product_name(name)
    rules=corrections()
    return rules.get(norm(raw),raw)

def learn_correction(original,new):
    global _CORRECTIONS_CACHE
    original=normalize_product_name(original);new=normalize_product_name(new)
    if not original or not new or norm(original)==norm(new):return False
    data=corrections();data[norm(original)]=new;save_json(CORRECTIONS_FILE,data);_CORRECTIONS_CACHE=dict(data);return True

def remove_correction(key):
    global _CORRECTIONS_CACHE
    data=corrections();data.pop(key,None);save_json(CORRECTIONS_FILE,data);_CORRECTIONS_CACHE=dict(data)

# ----------------------------------------------------------------------
# Histórico por produto / busca global
# ----------------------------------------------------------------------
def init_product_db():
    with sqlite3.connect(PRODUCT_DB) as con:
        con.execute("""CREATE TABLE IF NOT EXISTS history(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT, produto TEXT NOT NULL, produto_norm TEXT NOT NULL,
            campanha TEXT, tipo TEXT, promocao TEXT, clube TEXT, custo TEXT,
            varejo TEXT, unidade TEXT, limite TEXT, origem TEXT, arquivo_saida TEXT,
            gerado_em TEXT NOT NULL
        )""")
        con.execute("CREATE INDEX IF NOT EXISTS idx_hist_codigo ON history(codigo)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_hist_prod ON history(produto_norm)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_hist_source ON history(arquivo_saida)")
init_product_db()

def record_product_jobs(jobs,origem="Promoções",arquivo_saida="",recorded_at=None,replace_source=False):
    """Registra histórico. A biblioteca pode preservar a data original da promoção."""
    now=recorded_at or datetime.now().isoformat(timespec="seconds")
    rows=[]
    for j in jobs or []:
        prod=str(j.get("produto") or j.get("nome") or "").strip()
        if not prod:continue
        tipo=j.get("tipo")
        tipo_txt="Clube Exclusivo" if tipo==3 else "Promo + Clube" if tipo==2 else "Promoção" if tipo==1 else str(tipo or origem)
        row_date=str(j.get("_history_date") or now)
        rows.append((str(j.get("codigo") or ""),prod,norm(prod),str(j.get("campanha") or ""),tipo_txt,
                     str(j.get("promocao") or ""),str(j.get("clube") or ""),str(j.get("custo") or ""),
                     str(j.get("varejo") or ""),str(j.get("unidade_exibicao") or j.get("unidade") or ""),
                     str(j.get("limite") or ""),origem,str(arquivo_saida or ""),row_date))
    if not rows:return
    with sqlite3.connect(PRODUCT_DB) as con:
        if replace_source and arquivo_saida:
            con.execute("DELETE FROM history WHERE arquivo_saida=? AND origem LIKE 'Biblioteca%'",(str(arquivo_saida),))
        con.executemany("""INSERT INTO history(codigo,produto,produto_norm,campanha,tipo,promocao,clube,custo,varejo,unidade,limite,origem,arquivo_saida,gerado_em)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",rows)

def remove_history_source(arquivo_saida):
    if not arquivo_saida:return
    with sqlite3.connect(PRODUCT_DB) as con:
        con.execute("DELETE FROM history WHERE arquivo_saida=? AND origem LIKE 'Biblioteca%'",(str(arquivo_saida),))

def search_product_history(query,limit=100):
    q=norm(query);raw=str(query or "").strip()
    if not q:return []
    with sqlite3.connect(PRODUCT_DB) as con:
        con.row_factory=sqlite3.Row
        rows=con.execute("""SELECT * FROM history WHERE codigo LIKE ? OR produto_norm LIKE ? OR campanha LIKE ?
                            ORDER BY gerado_em DESC,id DESC LIMIT ?""",(f"%{raw}%",f"%{q}%",f"%{raw}%",limit)).fetchall()
    return [dict(x) for x in rows]

def product_history(codigo="",produto="",limit=50):
    with sqlite3.connect(PRODUCT_DB) as con:
        con.row_factory=sqlite3.Row
        if codigo:
            rows=con.execute("SELECT * FROM history WHERE codigo=? ORDER BY gerado_em DESC,id DESC LIMIT ?",(str(codigo),limit)).fetchall()
        else:
            rows=con.execute("SELECT * FROM history WHERE produto_norm=? ORDER BY gerado_em DESC,id DESC LIMIT ?",(norm(produto),limit)).fetchall()
    return [dict(x) for x in rows]

# ----------------------------------------------------------------------
# Verificações
# ----------------------------------------------------------------------
def _issue(code,severity,message,job,field=""):
    return {"code":code,"severity":severity,"message":message,"job_id":job.get("id"),
            "produto":job.get("produto",""),"codigo":job.get("codigo",""),"field":field}

def unit_warning(job):
    prod=norm(job.get("produto"));unit=str(job.get("unidade_exibicao") or "").upper()
    if "A GRANEL" in prod and unit!="KG":
        return "Produto indica 'A GRANEL', mas a unidade do cartaz não está como KG."
    if unit=="KG" and re.search(r"\b\d+\s*(ML|L)\b",prod):
        return "Produto está marcado como KG, mas a descrição contém medida em ML/L."
    return ""

def validate_promo_jobs(jobs):
    issues=[];seen={}
    for j in jobs or []:
        if not j.get("selected",True):continue
        custo=dec(j.get("custo"));venda=dec(j.get("varejo"))
        prices=[]
        if j.get("promocao"):prices.append(("PROMOÇÃO",dec(j.get("promocao")),"promocao"))
        if j.get("clube"):prices.append(("CLUBE",dec(j.get("clube")),"clube"))
        for label,p,field in prices:
            if p is None:continue
            if p<=0:
                issues.append(_issue("PRECO_INVALIDO","CRÍTICO",f"{label} está zerado ou inválido.",j,field));continue
            if custo is not None and p < custo:
                diff=custo-p
                issues.append(_issue("ABAIXO_CUSTO","CRÍTICO",f"{label} R$ {money(p)} está abaixo do custo R$ {money(custo)} em R$ {money(diff)}.",j,field))
            if venda is not None and venda>0:
                ratio=p/venda
                if ratio < Decimal("0.20") or ratio > Decimal("1.20"):
                    issues.append(_issue("PRECO_FORA_PADRAO","ATENÇÃO",f"{label} R$ {money(p)} está muito distante do preço de venda R$ {money(venda)}.",j,field))
                elif p>venda:
                    issues.append(_issue("PROMO_ACIMA_VENDA","ATENÇÃO",f"{label} R$ {money(p)} está acima do preço de venda R$ {money(venda)}.",j,field))
        promo=dec(j.get("promocao"));club=dec(j.get("clube"))
        if promo is not None and club is not None and club>promo:
            issues.append(_issue("CLUBE_MAIOR_PROMO","ATENÇÃO",f"Preço Clube R$ {money(club)} está maior que a Promoção R$ {money(promo)}.",j,"clube"))
        uw=unit_warning(j)
        if uw:issues.append(_issue("UNIDADE_SUSPEITA","ATENÇÃO",uw,j,"unidade_exibicao"))
        identity=str(j.get("codigo") or "").strip() or norm(j.get("produto"))
        if identity:
            if identity in seen:
                issues.append(_issue("DUPLICADO","ATENÇÃO",f"Produto/código duplicado na geração. Também aparece em '{seen[identity].get('campanha','')}'.",j,"produto"))
            else:seen[identity]=j
        # histórico: detector adicional de preço muito fora do último valor
        hist=product_history(str(j.get("codigo") or ""),j.get("produto",""),1)
        if hist:
            prev=dec(hist[0].get("clube") or hist[0].get("promocao"))
            cur=club or promo
            if prev and cur and prev>0:
                change=abs(cur-prev)/prev
                if change>=Decimal("0.60"):
                    issues.append(_issue("VARIACAO_HISTORICA","ATENÇÃO",f"Preço atual R$ {money(cur)} varia {int(change*100)}% em relação ao último R$ {money(prev)}.",j,"preco"))
    return issues

def verification_counts(issues):
    return {"critical":sum(x["severity"]=="CRÍTICO" for x in issues),
            "attention":sum(x["severity"]=="ATENÇÃO" for x in issues),
            "cost":sum(x["code"]=="ABAIXO_CUSTO" for x in issues),
            "duplicates":sum(x["code"]=="DUPLICADO" for x in issues),
            "unit":sum(x["code"]=="UNIDADE_SUSPEITA" for x in issues),
            "outlier":sum(x["code"] in {"PRECO_FORA_PADRAO","VARIACAO_HISTORICA"} for x in issues)}

class PreGenerationDialog(tk.Toplevel):
    def __init__(self,parent,jobs,issues,on_correct=None,palette=None):
        super().__init__(parent);self.parent=parent;self.jobs=jobs;self.issues=issues;self.on_correct=on_correct;self.result=False
        self.pal=palette or {"APP_BG":"#F4F7FB","CARD":"white","TEXT":"#152033","MUTED":"#6F7F95","LINE":"#DDE5EF","BLUE":"#0B2F6B","GREEN":"#E9F7EE","GREEN_TXT":"#267A43","RED":"#FDECEC","RED_TXT":"#A63C3C","ORANGE":"#FFF2DD","ORANGE_TXT":"#A46200","ROW_ALT":"#F8FAFD"}
        self.title("SR Studio - Verificações antes de gerar");self.configure(bg=self.pal["APP_BG"]);self.transient(parent);self.grab_set();self.minsize(860,560)
        self.protocol("WM_DELETE_WINDOW",self.cancel);self.build();self.center(1040,680)
    def center(self,w,h):
        self.update_idletasks();x=self.parent.winfo_rootx()+(self.parent.winfo_width()-w)//2;y=self.parent.winfo_rooty()+(self.parent.winfo_height()-h)//2;self.geometry(f"{w}x{h}+{max(0,x)}+{max(0,y)}")
    def build(self):
        p=self.pal;c=verification_counts(self.issues);selected=len([j for j in self.jobs if j.get("selected",True)])
        head=tk.Frame(self,bg=p["CARD"],highlightbackground=p["LINE"],highlightthickness=1);head.pack(fill="x")
        tk.Label(head,text="Antes de gerar",bg=p["CARD"],fg=p["TEXT"],font=("Segoe UI",18,"bold")).pack(anchor="w",padx=20,pady=(15,2))
        status="PRONTO PARA GERAR" if not self.issues else "GERAR COM ATENÇÃO" if not c["critical"] else "CONFIRMAÇÃO NECESSÁRIA"
        color=p["GREEN_TXT"] if not self.issues else p["ORANGE_TXT"] if not c["critical"] else p["RED_TXT"]
        tk.Label(head,text=f"{selected} cartazes • {status}",bg=p["CARD"],fg=color,font=("Segoe UI",10,"bold")).pack(anchor="w",padx=20,pady=(0,15))
        stats=tk.Frame(self,bg=p["APP_BG"]);stats.pack(fill="x",padx=18,pady=12)
        vals=[("Cartazes",selected),("Abaixo do custo",c["cost"]),("Preço fora do padrão",c["outlier"]),("Duplicados",c["duplicates"]),("Unidade suspeita",c["unit"])]
        for i,(t,v) in enumerate(vals):
            stats.grid_columnconfigure(i,weight=1);f=tk.Frame(stats,bg=p["CARD"],highlightbackground=p["LINE"],highlightthickness=1);f.grid(row=0,column=i,sticky="ew",padx=3)
            tk.Label(f,text=str(v),bg=p["CARD"],fg=p["TEXT"],font=("Segoe UI",15,"bold")).pack(pady=(8,0));tk.Label(f,text=t,bg=p["CARD"],fg=p["MUTED"],font=("Segoe UI",7,"bold")).pack(pady=(0,8))
        body=tk.Frame(self,bg=p["CARD"],highlightbackground=p["LINE"],highlightthickness=1);body.pack(fill="both",expand=True,padx=18,pady=(0,10))
        cols=("sev","produto","problema");self.tree=ttk.Treeview(body,columns=cols,show="headings",selectmode="browse")
        for col,title,width in [("sev","Nível",90),("produto","Produto",280),("problema","Verificação",570)]:self.tree.heading(col,text=title);self.tree.column(col,width=width,anchor="w")
        sb=ttk.Scrollbar(body,orient="vertical",command=self.tree.yview);self.tree.configure(yscrollcommand=sb.set);self.tree.pack(side="left",fill="both",expand=True,padx=(10,0),pady=10);sb.pack(side="right",fill="y",padx=(0,10),pady=10)
        for i,x in enumerate(self.issues):self.tree.insert("","end",iid=str(i),values=(x["severity"],x["produto"],x["message"]))
        if not self.issues:self.tree.insert("","end",values=("✓","Todas as verificações","Nenhum alerta encontrado."))
        bar=tk.Frame(self,bg=p["CARD"],highlightbackground=p["LINE"],highlightthickness=1);bar.pack(fill="x")
        tk.Button(bar,text="VOLTAR E CORRIGIR",command=self.correct,bg=p["RED"],fg=p["RED_TXT"],relief="flat",font=("Segoe UI",8,"bold"),padx=12,pady=8).pack(side="left",padx=18,pady=10)
        text="CONTINUAR MESMO ASSIM" if self.issues else "GERAR AGORA"
        tk.Button(bar,text=text,command=self.accept,bg=p["BLUE"],fg="white",relief="flat",font=("Segoe UI",9,"bold"),padx=16,pady=8).pack(side="right",padx=18,pady=10)
    def selected_issue(self):
        sel=self.tree.selection();return self.issues[int(sel[0])] if sel and sel[0].isdigit() and int(sel[0])<len(self.issues) else (self.issues[0] if self.issues else None)
    def correct(self):
        issue=self.selected_issue();self.result=False;self.destroy()
        if self.on_correct and issue:self.on_correct(issue)
    def accept(self):self.result=True;self.destroy()
    def cancel(self):self.result=False;self.destroy()
    def show(self):self.wait_window();return self.result

# ----------------------------------------------------------------------
# Fila recuperável
# ----------------------------------------------------------------------
def queue_load():
    d=load_json(QUEUE_FILE,{"tasks":[]})
    if not isinstance(d,dict):d={"tasks":[]}
    d.setdefault("tasks",[]);return d

def queue_save(data):save_json(QUEUE_FILE,data)
def queue_add(task):
    data=queue_load();task=dict(task);task.setdefault("id",datetime.now().strftime("%Y%m%d%H%M%S%f"));task.setdefault("status","PENDENTE");task.setdefault("checkpoint",0);task.setdefault("created_at",datetime.now().isoformat(timespec="seconds"));data["tasks"].append(task);queue_save(data);return task

def queue_update(task_id,**changes):
    d=queue_load()
    for t in d["tasks"]:
        if t.get("id")==task_id:t.update(changes);break
    queue_save(d)
def queue_remove(task_id):
    d=queue_load();d["tasks"]=[t for t in d["tasks"] if t.get("id")!=task_id];queue_save(d)
    shutil.rmtree(QUEUE_WORK/str(task_id),ignore_errors=True)
def queue_pending():return [t for t in queue_load()["tasks"] if t.get("status") in {"PENDENTE","PROCESSANDO","INTERROMPIDA"}]
def queue_clear_done():
    d=queue_load();done=[t for t in d["tasks"] if t.get("status") in {"CONCLUÍDA","CANCELADA"}]
    d["tasks"]=[t for t in d["tasks"] if t.get("status") not in {"CONCLUÍDA","CANCELADA"}];queue_save(d)
    for t in done:shutil.rmtree(QUEUE_WORK/str(t.get("id")),ignore_errors=True)

def model_sort_key(job):
    typ=int(job.get("tipo") or 0);limit=1 if str(job.get("limite") or "").strip() else 0
    return (typ,limit,str(job.get("campanha") or ""),int(job.get("id") or 0) if str(job.get("id") or "").isdigit() else 0)
def smart_queue_jobs(jobs):return sorted(list(jobs or []),key=model_sort_key)

# ----------------------------------------------------------------------
# Reimpressão + saída
# ----------------------------------------------------------------------
def record_reprint(kind,files,count=0,title="",meta=None):
    data=load_json(REPRINT_FILE,[]);data=data if isinstance(data,list) else []
    for f in files or []:
        data.append({"id":datetime.now().strftime("%Y%m%d%H%M%S%f"),"kind":kind,"file":str(f),"count":int(count or 0),"title":title,"date":datetime.now().strftime("%d/%m/%Y %H:%M"),"meta":meta or {}})
    save_json(REPRINT_FILE,data[-500:])
def reprint_items():return list(reversed(load_json(REPRINT_FILE,[]) if isinstance(load_json(REPRINT_FILE,[]),list) else []))

def sanitize_filename(s):
    s=re.sub(r'[<>:"/\\|?*]+','_',str(s or ""));s=re.sub(r"\s+"," ",s).strip();return s[:100] or "CARTAZ"
def default_output_root(settings=None):
    settings=settings or load_json(LOCAL_DATA/"ui_settings.json",{})
    p=str(settings.get("output_folder") or "").strip()
    if p:return Path(p)
    base=Path.home()/"Documents"/"SR Studio"/"Cartazes"
    return base
def dated_output_dir(kind,settings=None):
    root=default_output_root(settings);now=datetime.now();month=f"{now.month:02d} {['','Janeiro','Fevereiro','Março','Abril','Maio','Junho','Julho','Agosto','Setembro','Outubro','Novembro','Dezembro'][now.month]}"
    dest=root/str(now.year)/month/kind;dest.mkdir(parents=True,exist_ok=True);return dest
def smart_pdf_name(kind,campaign="",date_text=""):
    stamp=datetime.now().strftime("%d-%m-%Y")
    if date_text:
        m=re.search(r"\d{2}[-/]\d{2}(?:[-/]\d{2,4})?",str(date_text));
        if m:stamp=m.group(0).replace("/","-")
    base="SR_"+(sanitize_filename(campaign).upper().replace(" ","_") if campaign else sanitize_filename(kind).upper().replace(" ","_"))
    return f"{base}_{stamp}.pdf"

def unique_path(path):
    p=Path(path)
    if not p.exists():return p
    for i in range(2,1000):
        x=p.with_name(f"{p.stem}_{i:02d}{p.suffix}")
        if not x.exists():return x
    return p.with_name(f"{p.stem}_{int(time.time())}{p.suffix}")

# ----------------------------------------------------------------------
# Perfis de impressão
# ----------------------------------------------------------------------
_PRINTERS_CACHE = None
_PRINT_PROFILES_CACHE = None

def list_printers(refresh=False):
    global _PRINTERS_CACHE
    if not refresh and isinstance(_PRINTERS_CACHE,list):return list(_PRINTERS_CACHE)
    if os.name!="nt":_PRINTERS_CACHE=[];return []
    try:
        cmd=["powershell","-NoProfile","-Command","Get-CimInstance Win32_Printer | Select-Object -ExpandProperty Name"]
        r=subprocess.run(cmd,capture_output=True,text=True,timeout=7,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        _PRINTERS_CACHE=[x.strip() for x in r.stdout.splitlines() if x.strip()]
    except Exception:_PRINTERS_CACHE=[]
    return list(_PRINTERS_CACHE)
def default_profiles():return {"promo":{"printer":"","copies":1},"atacado":{"printer":"","copies":1},"manual":{"printer":"","copies":1}}
def load_print_profiles(refresh=False):
    global _PRINT_PROFILES_CACHE
    if not refresh and isinstance(_PRINT_PROFILES_CACHE,dict):
        return {k:dict(v) for k,v in _PRINT_PROFILES_CACHE.items()}
    d=load_json(PRINT_PROFILES_FILE,default_profiles());base=default_profiles()
    if isinstance(d,dict):
        for k in base:
            if isinstance(d.get(k),dict):base[k].update(d[k])
    _PRINT_PROFILES_CACHE={k:dict(v) for k,v in base.items()}
    return {k:dict(v) for k,v in base.items()}
def save_print_profiles(d):
    global _PRINT_PROFILES_CACHE
    save_json(PRINT_PROFILES_FILE,d);_PRINT_PROFILES_CACHE={k:dict(v) for k,v in d.items() if isinstance(v,dict)}
def print_with_profile(path,kind="promo",copies_override=None):
    from ui_v2 import print_pdf
    prof=load_print_profiles().get(kind,{})
    printer=str(prof.get("printer") or "").strip();copies=max(1,int(copies_override or prof.get("copies") or 1))
    old=""
    if os.name=="nt" and printer:
        try:
            r=subprocess.run(["powershell","-NoProfile","-Command","(Get-CimInstance Win32_Printer | Where-Object Default -eq $true | Select-Object -First 1 -ExpandProperty Name)"],capture_output=True,text=True,timeout=5,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0));old=r.stdout.strip()
            subprocess.run(["powershell","-NoProfile","-Command",f"(New-Object -ComObject WScript.Network).SetDefaultPrinter({json.dumps(printer)})"],capture_output=True,timeout=5,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
            time.sleep(.35)
        except Exception:old=""
    try:
        for i in range(copies):
            print_pdf(path)
            if i<copies-1:time.sleep(.25)
    finally:
        if old and old!=printer:
            try:
                time.sleep(.8);subprocess.Popen(["powershell","-NoProfile","-WindowStyle","Hidden","-Command",f"Start-Sleep -Milliseconds 800; (New-Object -ComObject WScript.Network).SetDefaultPrinter({json.dumps(old)})"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
            except Exception:pass

def pdf_with_copies(source,jobs,dest):
    copies=[max(1,int(j.get("copies") or 1)) for j in jobs]
    if all(x==1 for x in copies):return Path(source)
    from pypdf import PdfReader,PdfWriter
    reader=PdfReader(str(source));writer=PdfWriter()
    for i,page in enumerate(reader.pages):
        n=copies[i] if i<len(copies) else 1
        for _ in range(n):writer.add_page(page)
    dest=Path(dest);dest.parent.mkdir(parents=True,exist_ok=True)
    with open(dest,"wb") as f:writer.write(f)
    return dest

# ----------------------------------------------------------------------
# Versões dos modelos
# ----------------------------------------------------------------------
def backup_model_version(model_path,reason="substituição"):
    p=Path(model_path)
    if not p.exists():return None
    folder=MODEL_VERSIONS/p.stem;folder.mkdir(parents=True,exist_ok=True)
    out=folder/(datetime.now().strftime("%Y%m%d_%H%M%S")+"_"+sanitize_filename(reason)+p.suffix)
    shutil.copy2(p,out);return out
def model_versions(model_path):
    p=Path(model_path);folder=MODEL_VERSIONS/p.stem
    return sorted(folder.glob("*.pptx"),key=lambda x:x.stat().st_mtime,reverse=True) if folder.exists() else []
def restore_model_version(model_path,version_path):
    p=Path(model_path);v=Path(version_path)
    if not v.exists():raise RuntimeError("Versão selecionada não foi encontrada.")
    backup_model_version(p,"antes_restaurar");shutil.copy2(v,p);return p

# ----------------------------------------------------------------------
# Temporários / arrastar e soltar
# ----------------------------------------------------------------------
def cleanup_temp(days=3):
    cutoff=time.time()-days*86400;removed=0
    for folder in [LOCAL_DATA/"preview",LOCAL_DATA/"temp"]:
        if not folder.exists():continue
        for p in folder.rglob("*"):
            try:
                if p.is_file() and p.stat().st_mtime<cutoff:p.unlink();removed+=1
            except Exception:pass
    temp=Path(tempfile.gettempdir())
    for p in temp.glob("srstudio_*"):
        try:
            if p.is_dir() and p.stat().st_mtime<cutoff:shutil.rmtree(p,ignore_errors=True);removed+=1
        except Exception:pass
    return removed

def enable_drop(widget,callback,extensions=None):
    if not HAS_DND or not hasattr(widget,"drop_target_register"):return False
    try:
        widget.drop_target_register(DND_FILES)
        def ondrop(event):
            data=event.data
            try:files=widget.tk.splitlist(data)
            except Exception:files=[data.strip("{}")]
            for f in files:
                p=Path(str(f))
                if extensions and p.suffix.lower() not in {x.lower() for x in extensions}:continue
                callback(str(p));break
        widget.dnd_bind("<<Drop>>",ondrop);return True
    except Exception:return False
