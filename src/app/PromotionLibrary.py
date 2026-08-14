# -*- coding: utf-8 -*-
"""Biblioteca histórica de planilhas promocionais do SR Studio."""
import os, re, json, shutil, sqlite3, hashlib, threading, unicodedata
from pathlib import Path
from datetime import datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

from SRStudio21 import record_product_jobs, enable_drop
from ProductOrganizer import catalog_counts, rebuild_catalog

APP_DIR=Path(__file__).resolve().parent
LOCAL_ROOT=Path(os.environ.get("LOCALAPPDATA",str(APP_DIR)))
LOCAL_DATA=LOCAL_ROOT/"SR_Studio_2.0"
LOCAL_DATA.mkdir(parents=True,exist_ok=True)
DB_PATH=LOCAL_DATA/"promotion_library.db"


def _documents_root():
    home=Path.home()
    docs=home/"Documents"
    if not docs.exists(): docs=home/"Documentos"
    if not docs.exists(): docs=home
    root=docs/"SR Studio"/"Lista de Promocoes"
    try:
        root.mkdir(parents=True,exist_ok=True)
    except Exception:
        root=LOCAL_DATA/"Lista_de_Promocoes";root.mkdir(parents=True,exist_ok=True)
    return root

LIB_ROOT=_documents_root()


def norm(v):
    s="" if v is None else str(v)
    s=unicodedata.normalize("NFD",s)
    s="".join(c for c in s if unicodedata.category(c)!="Mn")
    return re.sub(r"[^A-Z0-9]+"," ",s.upper()).strip()


def safe_folder_name(name):
    s=str(name or "").strip()
    s=re.sub(r'[<>:"/\\|?*]+',' ',s)
    s=re.sub(r'\s+',' ',s).strip().rstrip('.')
    return s[:80] or "Nova pasta"


def sha256_file(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):h.update(chunk)
    return h.hexdigest()


def connect():
    con=sqlite3.connect(DB_PATH)
    con.row_factory=sqlite3.Row
    return con


def init_db():
    with connect() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS folders(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE COLLATE NOCASE,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS files(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            folder_id INTEGER,
            original_name TEXT NOT NULL,
            stored_name TEXT NOT NULL,
            stored_path TEXT NOT NULL UNIQUE,
            sha256 TEXT NOT NULL UNIQUE,
            period TEXT,
            campaigns TEXT,
            products INTEGER DEFAULT 0,
            errors INTEGER DEFAULT 0,
            warnings INTEGER DEFAULT 0,
            status TEXT DEFAULT 'OK',
            added_at TEXT NOT NULL,
            analyzed_at TEXT,
            FOREIGN KEY(folder_id) REFERENCES folders(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_lib_folder ON files(folder_id);
        CREATE INDEX IF NOT EXISTS idx_lib_hash ON files(sha256);
        """)
        count=con.execute("SELECT COUNT(*) FROM folders").fetchone()[0]
        if count==0:
            defaults=["Segunda da Limpeza","Terça Verde","Quarta Café","Quinta Filé","Fim de Semana","Clube SR","Aniversário","Outras Promoções"]
            now=datetime.now().isoformat(timespec="seconds")
            for name in defaults:
                try:
                    con.execute("INSERT INTO folders(name,created_at) VALUES(?,?)",(name,now))
                    (LIB_ROOT/safe_folder_name(name)).mkdir(parents=True,exist_ok=True)
                except Exception:pass
init_db()


_LIBRARY_FOLDER_CACHE=None
_LIBRARY_FILES_CACHE=None
_LIBRARY_COUNTS_CACHE=None
_LIBRARY_CACHE_LOCK=threading.RLock()

def invalidate_library_cache():
    global _LIBRARY_FOLDER_CACHE,_LIBRARY_FILES_CACHE,_LIBRARY_COUNTS_CACHE
    with _LIBRARY_CACHE_LOCK:
        _LIBRARY_FOLDER_CACHE=None;_LIBRARY_FILES_CACHE=None;_LIBRARY_COUNTS_CACHE=None

def preload_library_cache(force=False):
    global _LIBRARY_FOLDER_CACHE,_LIBRARY_FILES_CACHE,_LIBRARY_COUNTS_CACHE
    with _LIBRARY_CACHE_LOCK:
        if _LIBRARY_FOLDER_CACHE is not None and not force:
            return len(_LIBRARY_FILES_CACHE or [])
        with connect() as con:
            folders=[dict(x) for x in con.execute("SELECT * FROM folders ORDER BY name COLLATE NOCASE").fetchall()]
            files=[dict(x) for x in con.execute("""SELECT f.*,COALESCE(fd.name,'Sem pasta') AS folder_name FROM files f
                       LEFT JOIN folders fd ON fd.id=f.folder_id ORDER BY f.added_at DESC,f.id DESC""").fetchall()]
        c=catalog_counts()
        _LIBRARY_FOLDER_CACHE=folders;_LIBRARY_FILES_CACHE=files
        _LIBRARY_COUNTS_CACHE={
            'files':len(files),'folders':len(folders),'errors':sum(int(x.get('errors') or 0) for x in files),
            'records':int(c.get('records',0)),'unique':int(c.get('unique',0)),
            'families':int(c.get('families',0)),'review':int(c.get('review',0)),
            'products':sum(int(x.get('products') or 0) for x in files)
        }
        return len(files)


def folder_rows():
    preload_library_cache()
    return [dict(x) for x in (_LIBRARY_FOLDER_CACHE or [])]


def folder_by_id(folder_id):
    if not folder_id:return None
    preload_library_cache()
    for r in (_LIBRARY_FOLDER_CACHE or []):
        if int(r.get("id") or 0)==int(folder_id):return dict(r)
    return None


def create_folder(name):
    name=safe_folder_name(name);path=LIB_ROOT/name;path.mkdir(parents=True,exist_ok=True)
    with connect() as con:
        cur=con.execute("INSERT INTO folders(name,created_at) VALUES(?,?)",(name,datetime.now().isoformat(timespec="seconds")))
        rid=cur.lastrowid
    invalidate_library_cache();preload_library_cache(force=True);return rid


def rename_folder(folder_id,new_name):
    old=folder_by_id(folder_id)
    if not old:raise RuntimeError("Pasta não encontrada.")
    new_name=safe_folder_name(new_name);old_path=LIB_ROOT/safe_folder_name(old["name"]);new_path=LIB_ROOT/new_name
    if new_path.exists() and new_path.resolve()!=old_path.resolve():raise RuntimeError("Já existe uma pasta com esse nome.")
    if old_path.exists():old_path.rename(new_path)
    else:new_path.mkdir(parents=True,exist_ok=True)
    with connect() as con:
        con.execute("UPDATE folders SET name=? WHERE id=?",(new_name,folder_id))
        rows=con.execute("SELECT id,stored_name FROM files WHERE folder_id=?",(folder_id,)).fetchall()
        for r in rows:con.execute("UPDATE files SET stored_path=? WHERE id=?",(str(new_path/r["stored_name"]),r["id"]))
    invalidate_library_cache();preload_library_cache(force=True)


def delete_folder(folder_id,move_to_root=True):
    row=folder_by_id(folder_id)
    if not row:return
    path=LIB_ROOT/safe_folder_name(row["name"])
    with connect() as con:
        files=con.execute("SELECT * FROM files WHERE folder_id=?",(folder_id,)).fetchall()
        if files and move_to_root:
            for f in files:
                src=Path(f["stored_path"]);dst=unique_file(LIB_ROOT/src.name)
                if src.exists():shutil.move(str(src),str(dst))
                con.execute("UPDATE files SET folder_id=NULL,stored_name=?,stored_path=? WHERE id=?",(dst.name,str(dst),f["id"]))
        elif files:raise RuntimeError("A pasta possui planilhas. Mova ou remova as planilhas antes de excluir.")
        con.execute("DELETE FROM folders WHERE id=?",(folder_id,))
    try:path.rmdir()
    except Exception:pass
    invalidate_library_cache();preload_library_cache(force=True)


def unique_file(path):
    path=Path(path)
    if not path.exists():return path
    i=2
    while True:
        p=path.with_name(f"{path.stem}_{i}{path.suffix}")
        if not p.exists():return p
        i+=1


def parse_history_date(text,filename=""):
    joined=f"{text or ''} {filename or ''}"
    pats=[r"\b(\d{1,2})[/-](\d{1,2})[/-](20\d{2})\b",r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2})\b"]
    found=[]
    for pat in pats:
        for m in re.finditer(pat,joined):
            d,mo,y=m.groups();y=int(y);y=2000+y if y<100 else y
            try:found.append(datetime(y,int(mo),int(d)))
            except Exception:pass
        if found:break
    return min(found).isoformat(timespec="seconds") if found else datetime.now().isoformat(timespec="seconds")


def list_files(folder_id=None,query=""):
    preload_library_cache();q=norm(query);out=[]
    for r in (_LIBRARY_FILES_CACHE or []):
        if folder_id not in (None,"all"):
            if folder_id=="root" and r.get("folder_id") is not None:continue
            if folder_id!="root" and int(r.get("folder_id") or 0)!=int(folder_id):continue
        if q and q not in norm(" ".join(str(r.get(k) or "") for k in ("original_name","campaigns","folder_name"))):continue
        out.append(dict(r))
    return out


def library_counts():
    preload_library_cache()
    return dict(_LIBRARY_COUNTS_CACHE or {})


def remove_file(file_id,remove_history=True):
    with connect() as con:
        r=con.execute("SELECT * FROM files WHERE id=?",(file_id,)).fetchone()
        if not r:return
        path=r["stored_path"]
        con.execute("DELETE FROM files WHERE id=?",(file_id,))
    if remove_history:
        try:
            from SRStudio21 import remove_history_source
            remove_history_source(path)
        except Exception:pass
    try:Path(path).unlink()
    except Exception:pass
    invalidate_library_cache();preload_library_cache(force=True)


def import_one(source,folder_id,analyzer):
    source=Path(source)
    if source.suffix.lower() not in {".xlsx",".xlsm"}:raise RuntimeError("Formato não aceito. Use .xlsx ou .xlsm.")
    digest=sha256_file(source)
    with connect() as con:
        old=con.execute("SELECT * FROM files WHERE sha256=?",(digest,)).fetchone()
        if old:return {"duplicate":True,"row":dict(old),"jobs":0}
    folder=folder_by_id(folder_id) if folder_id not in (None,"root","all") else None
    dest_dir=LIB_ROOT/(safe_folder_name(folder["name"]) if folder else "")
    dest_dir.mkdir(parents=True,exist_ok=True)
    dest=unique_file(dest_dir/source.name)
    shutil.copy2(source,dest)
    try:
        analysis=analyzer(dest)
        jobs=list(analysis.get("jobs",[]))
        campaigns=analysis.get("campaigns",[])
        names=[];periods=[]
        for c in campaigns:
            n=str(c.get("name","")).strip();v=str(c.get("validity","")).strip()
            if n and n not in names:names.append(n)
            if v and v not in periods:periods.append(v)
        period=" • ".join(periods[:3])
        camp_text=" • ".join(names[:6])
        errors=len(analysis.get("errors",[]));warnings=len(analysis.get("warnings",[]))
        status="ERRO" if errors else "ATENÇÃO" if warnings else "OK"
        now=datetime.now().isoformat(timespec="seconds")
        with connect() as con:
            cur=con.execute("""INSERT INTO files(folder_id,original_name,stored_name,stored_path,sha256,period,campaigns,products,errors,warnings,status,added_at,analyzed_at)
                               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                            ((folder or {}).get("id"),source.name,dest.name,str(dest),digest,period,camp_text,len(jobs),errors,warnings,status,now,now))
            file_id=cur.lastrowid
        # Cada produto histórico recebe a data da própria campanha/validade quando possível.
        for j in jobs:
            j["_history_date"]=parse_history_date(j.get("validade"),source.name)
        record_product_jobs(jobs,origem=f"Biblioteca • {(folder or {}).get('name','Sem pasta')}",arquivo_saida=str(dest),replace_source=True)
        invalidate_library_cache();preload_library_cache(force=True)
        return {"duplicate":False,"file_id":file_id,"jobs":len(jobs),"errors":errors,"warnings":warnings}
    except Exception:
        try:dest.unlink()
        except Exception:pass
        raise


class PromotionLibraryPanel(tk.Frame):
    def __init__(self,parent,app,analyzer,palette):
        super().__init__(parent,bg=palette["APP_BG"])
        self.app=app;self.analyzer=analyzer;self.p=palette;self.selected_folder="all";self.busy=False
        self.search_var=tk.StringVar();self.status_var=tk.StringVar(value="Biblioteca pronta.")
        self.progress_var=tk.DoubleVar(value=0)
        self._build();self.refresh_all()
        _cc=catalog_counts()
        if _cc.get("records",0) and not _cc.get("unique",0):
            self.after(180,self._rebuild_catalog_async)

    def _build(self):
        p=self.p
        tk.Label(self,text="Lista de Promoções",bg=p["APP_BG"],fg=p["TEXT"],font=("Segoe UI",20,"bold")).pack(anchor="w",padx=24,pady=(16,9))
        stats=tk.Frame(self,bg=p["APP_BG"]);stats.pack(fill="x",padx=24,pady=(0,10));self.stat_labels={}
        stat_defs=[("files","Planilhas"),("folders","Pastas"),("unique","Produtos únicos"),("families","Famílias"),("records","Registros históricos"),("review","Revisar")]
        for i,(k,t) in enumerate(stat_defs):
            stats.grid_columnconfigure(i,weight=1)
            c=tk.Frame(stats,bg=p["CARD"],highlightbackground=p["LINE"],highlightthickness=1)
            c.grid(row=0,column=i,sticky="ew",padx=(0 if i==0 else 3,0 if i==len(stat_defs)-1 else 3))
            rowc=tk.Frame(c,bg=p["CARD"]);rowc.pack(fill="x",padx=8,pady=6)
            v=tk.Label(rowc,text="0",bg=p["CARD"],fg=p["TEXT"],font=("Segoe UI",12,"bold"));v.pack(side="left");self.stat_labels[k]=v
            tk.Label(rowc,text=t,bg=p["CARD"],fg=p["MUTED"],font=("Segoe UI",7,"bold")).pack(side="left",padx=(5,0),pady=(2,0))
        body=tk.Frame(self,bg=p["APP_BG"]);body.pack(fill="both",expand=True,padx=24,pady=(0,10));body.grid_columnconfigure(0,weight=1);body.grid_columnconfigure(1,weight=4);body.grid_rowconfigure(0,weight=1)
        # Pastas
        left=tk.Frame(body,bg=p["CARD"],highlightbackground=p["LINE"],highlightthickness=1);left.grid(row=0,column=0,sticky="nsew",padx=(0,7))
        tk.Label(left,text="Pastas",bg=p["CARD"],fg=p["TEXT"],font=("Segoe UI",11,"bold")).pack(anchor="w",padx=12,pady=(12,6))
        self.folder_tree=ttk.Treeview(left,show="tree",selectmode="browse",height=16);self.folder_tree.pack(fill="both",expand=True,padx=10,pady=(0,8));self.folder_tree.bind("<<TreeviewSelect>>",self.folder_changed)
        fb=tk.Frame(left,bg=p["CARD"]);fb.pack(fill="x",padx=10,pady=(0,10))
        for text,cmd in [("NOVA PASTA",self.new_folder),("RENOMEAR",self.rename_folder),("EXCLUIR",self.delete_folder)]:
            tk.Button(fb,text=text,command=cmd,bg=p["ROW_ALT"],fg=p["TEXT"],relief="flat",font=("Segoe UI",7,"bold"),padx=8,pady=6).pack(fill="x",pady=2)
        tk.Button(fb,text="ABRIR PASTA NO WINDOWS",command=self.open_folder,bg=p["LIGHT_BLUE"],fg=p["LIGHT_BLUE_TXT"],relief="flat",font=("Segoe UI",7,"bold"),padx=8,pady=6).pack(fill="x",pady=2)
        # Arquivos
        right=tk.Frame(body,bg=p["CARD"],highlightbackground=p["LINE"],highlightthickness=1);right.grid(row=0,column=1,sticky="nsew",padx=(7,0))
        tools=tk.Frame(right,bg=p["CARD"]);tools.pack(fill="x",padx=12,pady=12)
        self.search=tk.Entry(tools,textvariable=self.search_var,bg=p["ROW_ALT"],fg=p["TEXT"],insertbackground=p["TEXT"],relief="flat",font=("Segoe UI",9));self.search.pack(side="left",fill="x",expand=True,ipady=6);self.search.bind("<KeyRelease>",lambda e:self.refresh_files())
        tk.Button(tools,text="BANCO",command=lambda:self.app.navigate("products"),bg=p["ORANGE"],fg=p["ORANGE_TXT"],relief="flat",font=("Segoe UI",8,"bold"),padx=10,pady=7).pack(side="right",padx=(8,0))
        tk.Button(tools,text="＋ PLANILHAS",command=self.pick_files,bg=p["BLUE"],fg="white",relief="flat",font=("Segoe UI",8,"bold"),padx=10,pady=7).pack(side="right",padx=(8,0))
        tk.Button(tools,text="＋ PASTA",command=self.pick_directory,bg=p["GREEN"],fg=p["GREEN_TXT"],relief="flat",font=("Segoe UI",8,"bold"),padx=10,pady=7).pack(side="right",padx=(8,0))
        cols=("arquivo","pasta","periodo","campanhas","produtos","status")
        self.tree=ttk.Treeview(right,columns=cols,show="headings",selectmode="browse")
        for c,t,w in [("arquivo","Planilha",250),("pasta","Pasta",135),("periodo","Período",150),("campanhas","Campanhas",250),("produtos","Produtos",70),("status","Status",80)]:self.tree.heading(c,text=t);self.tree.column(c,width=w,anchor="w")
        sb=ttk.Scrollbar(right,orient="vertical",command=self.tree.yview);self.tree.configure(yscrollcommand=sb.set);self.tree.pack(side="left",fill="both",expand=True,padx=(12,0),pady=(0,8));sb.pack(side="right",fill="y",padx=(0,12),pady=(0,8));self.tree.bind("<Double-1>",lambda e:self.open_selected())
        self.records={}
        actions=tk.Frame(right,bg=p["CARD"]);actions.pack(fill="x",padx=12,pady=(0,10))
        for text,cmd,bg,fg in [("ABRIR",self.open_selected,p["LIGHT_BLUE"],p["LIGHT_BLUE_TXT"]),("USAR",self.use_selected,p["BLUE"],"white"),("REPROCESSAR",self.reprocess_selected,p["ORANGE"],p["ORANGE_TXT"]),("REMOVER",self.remove_selected,p["RED"],p["RED_TXT"])]:
            tk.Button(actions,text=text,command=cmd,bg=bg,fg=fg,relief="flat",font=("Segoe UI",7,"bold"),padx=9,pady=7).pack(side="left",padx=(0,5))
        foot=tk.Frame(self,bg=p["CARD"],highlightbackground=p["LINE"],highlightthickness=1);foot.pack(fill="x",padx=24,pady=(0,18))
        ttk.Progressbar(foot,variable=self.progress_var,maximum=100,style="SR.Horizontal.TProgressbar").pack(side="left",fill="x",expand=True,padx=12,pady=9)
        tk.Label(foot,textvariable=self.status_var,bg=p["CARD"],fg=p["MUTED"],font=("Segoe UI",8)).pack(side="right",padx=12)
        enable_drop(self.tree,self._drop_files)

    def refresh_all(self):
        self.refresh_folders();self.refresh_files();c=library_counts()
        for k,w in self.stat_labels.items():w.config(text=str(c.get(k,0)))

    def refresh_folders(self):
        cur=self.selected_folder;self.folder_tree.delete(*self.folder_tree.get_children());self.folder_tree.insert("","end",iid="all",text="▤  Todas as Promoções",open=True);self.folder_tree.insert("","end",iid="root",text="▱  Sem pasta")
        for f in folder_rows():self.folder_tree.insert("","end",iid=f"f{f['id']}",text=f"▱  {f['name']}")
        iid="all" if cur=="all" else "root" if cur=="root" else f"f{cur}"
        if self.folder_tree.exists(iid):self.folder_tree.selection_set(iid)

    def refresh_files(self):
        self.tree.delete(*self.tree.get_children());self.records={}
        rows=list_files(self.selected_folder,self.search_var.get())
        for r in rows:
            iid=str(r["id"]);self.records[iid]=r;status=r["status"] if Path(r["stored_path"]).exists() else "AUSENTE"
            self.tree.insert("","end",iid=iid,values=(r["original_name"],r["folder_name"],r.get("period") or "—",r.get("campaigns") or "—",r.get("products",0),status))

    def folder_changed(self,_=None):
        sel=self.folder_tree.selection();
        if not sel:return
        iid=sel[0];self.selected_folder="all" if iid=="all" else "root" if iid=="root" else int(iid[1:]);self.refresh_files()

    def selected_folder_id(self):return None if self.selected_folder in {"all","root"} else self.selected_folder
    def selected_record(self):
        sel=self.tree.selection();return self.records.get(sel[0]) if sel else None

    def new_folder(self):
        name=simpledialog.askstring("Nova pasta","Nome da pasta/categoria:",parent=self)
        if not name:return
        try:self.selected_folder=create_folder(name);self.refresh_all()
        except Exception as e:messagebox.showerror("Lista de Promoções",str(e),parent=self)

    def rename_folder(self):
        fid=self.selected_folder_id()
        if not fid:messagebox.showinfo("Lista de Promoções","Selecione uma pasta criada por você.",parent=self);return
        row=folder_by_id(fid);name=simpledialog.askstring("Renomear pasta","Novo nome:",initialvalue=row["name"],parent=self)
        if not name:return
        try:rename_folder(fid,name);self.refresh_all()
        except Exception as e:messagebox.showerror("Lista de Promoções",str(e),parent=self)

    def delete_folder(self):
        fid=self.selected_folder_id()
        if not fid:messagebox.showinfo("Lista de Promoções","Selecione uma pasta criada por você.",parent=self);return
        if not messagebox.askyesno("Excluir pasta","Excluir a pasta?\n\nAs planilhas dentro dela serão movidas para 'Sem pasta' e não sairão do banco histórico.",parent=self):return
        try:delete_folder(fid,True);self.selected_folder="all";self.refresh_all()
        except Exception as e:messagebox.showerror("Lista de Promoções",str(e),parent=self)

    def open_folder(self):
        f=folder_by_id(self.selected_folder_id())
        path=LIB_ROOT/(safe_folder_name(f["name"]) if f else "")
        try:os.startfile(str(path))
        except Exception:messagebox.showinfo("Lista de Promoções",str(path),parent=self)

    def pick_files(self):
        files=filedialog.askopenfilenames(title="Adicionar planilhas à Lista de Promoções",filetypes=[("Planilhas Excel","*.xlsx *.xlsm")],parent=self)
        if files:self.import_files(files,self.selected_folder_id())

    def _drop_files(self,paths):
        files=[]
        for p in paths:
            pp=Path(p)
            if pp.is_dir():files.extend(pp.rglob("*.xlsx"))
            elif pp.suffix.lower() in {".xlsx",".xlsm"}:files.append(pp)
        if files:self.import_files(files,self.selected_folder_id())

    def pick_directory(self):
        d=filedialog.askdirectory(title="Importar pasta de promoções",parent=self)
        if not d:return
        base=Path(d);items=[]
        # Planilhas da raiz vão para a pasta atualmente selecionada.
        for x in base.glob("*.xlsx"):items.append((x,self.selected_folder_id()))
        for x in base.glob("*.xlsm"):items.append((x,self.selected_folder_id()))
        # Cada subpasta imediata vira categoria automaticamente.
        known={norm(x["name"]):x["id"] for x in folder_rows()}
        for sub in [x for x in base.iterdir() if x.is_dir()]:
            fid=known.get(norm(sub.name))
            if not fid:
                try:fid=create_folder(sub.name);known[norm(sub.name)]=fid
                except Exception:fid=None
            for x in list(sub.rglob("*.xlsx"))+list(sub.rglob("*.xlsm")):items.append((x,fid))
        if not items:messagebox.showinfo("Lista de Promoções","Nenhuma planilha .xlsx/.xlsm foi encontrada.",parent=self);return
        self.import_mixed(items)

    def import_files(self,files,folder_id):self.import_mixed([(Path(x),folder_id) for x in files])
    def import_mixed(self,items):
        if self.busy:return
        self.busy=True;self.app.busy=True;self.progress_var.set(0);self.status_var.set(f"Importando {len(items)} planilha(s)...")
        def worker():
            ok=dup=err=products=0;messages=[]
            total=len(items)
            for i,(path,fid) in enumerate(items,1):
                try:
                    r=import_one(path,fid,self.analyzer)
                    if r.get("duplicate"):dup+=1
                    else:ok+=1;products+=int(r.get("jobs",0))
                except Exception as e:err+=1;messages.append(f"{Path(path).name}: {e}")
                self.after(0,lambda i=i,total=total,p=Path(path): (self.progress_var.set(i/total*100),self.status_var.set(f"{i}/{total} • {p.name}")))
            self.after(0,lambda:self._finish_import(ok,dup,err,products,messages))
        threading.Thread(target=worker,daemon=True).start()

    def _finish_import(self,ok,dup,err,products,messages):
        self.busy=False
        self.app.busy=False
        self.progress_var.set(100)
        self.refresh_all()
        self.status_var.set(f"{ok} adicionada(s) • {dup} já existente(s) • {err} erro(s) • {products} registros históricos")
        if err:
            messagebox.showwarning(
                "Lista de Promoções",
                "Algumas planilhas não puderam ser importadas:\n\n" + "\n".join(messages[:8]),
                parent=self
            )
        elif ok:
            messagebox.showinfo(
                "Lista de Promoções",
                f"Importação concluída.\n\n{ok} planilha(s) adicionada(s)\n{products} registro(s) incluído(s) no histórico\n{dup} duplicada(s) ignorada(s).\n\nO Banco de Produtos será reorganizado em segundo plano.",
                parent=self
            )
        if ok:
            self._rebuild_catalog_async()

    def _rebuild_catalog_async(self):
        if self.busy:
            return
        self.status_var.set("Organizando produtos únicos e variações...")
        def worker():
            try:
                c=rebuild_catalog()
                self.after(0,lambda c=c:self._finish_catalog_refresh(c))
            except Exception as e:
                self.after(0,lambda msg=str(e):self.status_var.set("Histórico importado • organização pendente: "+msg))
        threading.Thread(target=worker,daemon=True).start()

    def _finish_catalog_refresh(self,c):
        self.refresh_all()
        self.status_var.set(f"Banco organizado • {c['unique']} produtos únicos • {c['families']} famílias • {c['records']} registros históricos")

    def open_selected(self):
        r=self.selected_record()
        if not r:return
        p=Path(r["stored_path"])
        if not p.exists():messagebox.showwarning("Lista de Promoções","O arquivo não existe mais na biblioteca.",parent=self);return
        try:os.startfile(str(p))
        except Exception:messagebox.showinfo("Lista de Promoções",str(p),parent=self)

    def use_selected(self):
        r=self.selected_record()
        if not r:return
        p=Path(r["stored_path"])
        if not p.exists():messagebox.showwarning("Lista de Promoções","O arquivo não foi encontrado.",parent=self);return
        self.app.navigate("promo");self.app.after(150,lambda:self.app.import_file(str(p)))

    def reprocess_selected(self):
        r=self.selected_record()
        if not r:return
        p=Path(r["stored_path"])
        if not p.exists():messagebox.showwarning("Lista de Promoções","O arquivo não foi encontrado.",parent=self);return
        if self.busy:return
        self.busy=True;self.app.busy=True;self.status_var.set("Reprocessando histórico...")
        def worker():
            try:
                a=self.analyzer(p);jobs=a.get("jobs",[])
                for j in jobs:j["_history_date"]=parse_history_date(j.get("validade"),p.name)
                record_product_jobs(jobs,origem=f"Biblioteca • {r.get('folder_name','Sem pasta')}",arquivo_saida=str(p),replace_source=True)
                names=[];periods=[]
                for c in a.get("campaigns",[]):
                    if c.get("name") and c["name"] not in names:names.append(c["name"])
                    if c.get("validity") and c["validity"] not in periods:periods.append(c["validity"])
                with connect() as con:con.execute("UPDATE files SET period=?,campaigns=?,products=?,errors=?,warnings=?,status=?,analyzed_at=? WHERE id=?",(" • ".join(periods[:3])," • ".join(names[:6]),len(jobs),len(a.get("errors",[])),len(a.get("warnings",[])),"ERRO" if a.get("errors") else "ATENÇÃO" if a.get("warnings") else "OK",datetime.now().isoformat(timespec="seconds"),r["id"]))
                self.after(0,lambda:self._finish_reprocess(len(jobs)))
            except Exception as e:self.after(0,lambda e=str(e):self._reprocess_error(e))
        threading.Thread(target=worker,daemon=True).start()
    def _finish_reprocess(self,n):
        self.busy=False;self.app.busy=False;self.refresh_all();self.status_var.set(f"Reprocessado • {n} registros no histórico")
        messagebox.showinfo("Lista de Promoções","Banco histórico atualizado. A organização será recalculada.",parent=self)
        self._rebuild_catalog_async()
    def _reprocess_error(self,e):self.busy=False;self.app.busy=False;self.status_var.set(str(e));messagebox.showerror("Lista de Promoções",str(e),parent=self)

    def remove_selected(self):
        r=self.selected_record()
        if not r:return
        if not messagebox.askyesno("Remover da Lista de Promoções","Remover esta planilha da biblioteca?\n\nEla também será retirada do histórico importado pela Lista de Promoções. PDFs gerados anteriormente não serão apagados.",parent=self):return
        remove_file(r["id"],True);self.refresh_all();self.status_var.set("Planilha removida da biblioteca. Reorganizando banco...");self._rebuild_catalog_async()
