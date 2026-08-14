# -*- coding: utf-8 -*-
import os, sys, json, hashlib, subprocess, shutil, time
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

APP_VERSION = "4.0.4"

LIGHT = {
    "APP_BG":"#F5F7FB","SIDEBAR":"#071F45","SIDEBAR_HOVER":"#103E83","CARD":"#FFFFFF",
    "TEXT":"#142033","MUTED":"#718096","LINE":"#E3E9F2","BLUE":"#0A49A7","BLUE2":"#2F6DD0",
    "GREEN":"#EAF8EF","GREEN_TXT":"#1F7A43","ORANGE":"#FFF3E3","ORANGE_TXT":"#A65D00",
    "LIGHT_BLUE":"#EAF2FF","LIGHT_BLUE_TXT":"#255EAF","RED":"#FDEDEE","RED_TXT":"#B33E47",
    "YELLOW":"#FFF8DE","YELLOW_TXT":"#8A6A00","PURPLE":"#F0ECFF","PURPLE_TXT":"#6247B5",
    "ROW_ALT":"#F7F9FC","SELECT":"#DCEAFF","TOPBAR":"#FFFFFF",
}
DARK = {
    "APP_BG":"#0E141D","SIDEBAR":"#06172F","SIDEBAR_HOVER":"#103E83","CARD":"#17212D",
    "TEXT":"#F3F6FA","MUTED":"#9EABBC","LINE":"#2A3647","BLUE":"#78A9FF","BLUE2":"#82B0FF",
    "GREEN":"#183729","GREEN_TXT":"#90E3AE","ORANGE":"#3D2B17","ORANGE_TXT":"#FFC36A",
    "LIGHT_BLUE":"#182E50","LIGHT_BLUE_TXT":"#A3C6FF","RED":"#3D2024","RED_TXT":"#FFA0A7",
    "YELLOW":"#3B3117","YELLOW_TXT":"#ECD675","PURPLE":"#2D2545","PURPLE_TXT":"#C8B8FF",
    "ROW_ALT":"#131C27","SELECT":"#244B78","TOPBAR":"#17212D",
}

def windows_dark_mode():
    if os.name != "nt": return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            val,_=winreg.QueryValueEx(k,"AppsUseLightTheme")
            return int(val)==0
    except Exception:
        return False

def choose_palette(mode="Automático"):
    m=(mode or "Automático").lower()
    if m.startswith("esc"): return DARK.copy()
    if m.startswith("cla"): return LIGHT.copy()
    return DARK.copy() if windows_dark_mode() else LIGHT.copy()

def center_toplevel(win, parent=None, width=None, height=None):
    try:
        win.update_idletasks()
        parent = parent or win.master or tk._default_root
        if width is None: width=max(win.winfo_reqwidth(), win.winfo_width())
        if height is None: height=max(win.winfo_reqheight(), win.winfo_height())
        if parent and parent.winfo_exists():
            parent.update_idletasks()
            x=parent.winfo_rootx()+(parent.winfo_width()-width)//2
            y=parent.winfo_rooty()+(parent.winfo_height()-height)//2
        else:
            sw=win.winfo_screenwidth(); sh=win.winfo_screenheight(); x=(sw-width)//2; y=(sh-height)//2
        win.geometry(f"{int(width)}x{int(height)}+{max(0,int(x))}+{max(0,int(y))}")
    except Exception:
        pass

def add_hover(widget, normal_bg, hover_bg=None, normal_fg=None, hover_fg=None):
    """Resposta visual discreta para cards/botões sem alterar a lógica do widget."""
    hover_bg = hover_bg or normal_bg
    def enter(_=None):
        try:
            widget.configure(bg=hover_bg)
            if hover_fg is not None: widget.configure(fg=hover_fg)
        except Exception: pass
    def leave(_=None):
        try:
            widget.configure(bg=normal_bg)
            if normal_fg is not None: widget.configure(fg=normal_fg)
        except Exception: pass
    widget.bind("<Enter>",enter,add="+")
    widget.bind("<Leave>",leave,add="+")
    return widget

class Tooltip:
    def __init__(self, widget, text, delay=450):
        self.widget=widget; self.text=text; self.delay=delay; self.after_id=None; self.tip=None
        widget.bind("<Enter>",self._enter,add="+")
        widget.bind("<Leave>",self._leave,add="+")
        widget.bind("<ButtonPress>",self._leave,add="+")
    def _enter(self,e=None):
        self._leave(); self.after_id=self.widget.after(self.delay,self._show)
    def _leave(self,e=None):
        if self.after_id:
            try:self.widget.after_cancel(self.after_id)
            except Exception:pass
            self.after_id=None
        if self.tip:
            try:self.tip.destroy()
            except Exception:pass
            self.tip=None
    def _show(self):
        if not self.text:return
        self.tip=tk.Toplevel(self.widget); self.tip.wm_overrideredirect(True); self.tip.attributes("-topmost",True)
        pal=choose_palette(getattr(tk._default_root,"theme_mode",tk.StringVar(value="Automático")).get() if tk._default_root else "Automático")
        lab=tk.Label(self.tip,text=self.text,bg="#202630",fg="white",font=("Segoe UI",8),justify="left",wraplength=320,padx=9,pady=6)
        lab.pack()
        x=self.widget.winfo_rootx()+12; y=self.widget.winfo_rooty()+self.widget.winfo_height()+6
        self.tip.geometry(f"+{x}+{y}")

def add_tooltip(widget,text):
    return Tooltip(widget,text)

class SRDialog(tk.Toplevel):
    def __init__(self,parent,title,message,kind="info",buttons=("OK",)):
        super().__init__(parent or tk._default_root)
        self.result=None; self.transient(parent or tk._default_root); self.grab_set(); self.resizable(False,False)
        root=parent or tk._default_root
        pal=getattr(root,"palette",LIGHT)
        self.configure(bg=pal["CARD"]); self.title(title)
        icon={"info":"●","warning":"!","error":"×","question":"?"}.get(kind,"●")
        fg={"info":pal["BLUE2"],"warning":pal["ORANGE_TXT"],"error":pal["RED_TXT"],"question":pal["BLUE2"]}.get(kind,pal["BLUE2"])
        body=tk.Frame(self,bg=pal["CARD"]); body.pack(fill="both",expand=True,padx=22,pady=18)
        tk.Label(body,text=icon,bg=pal["CARD"],fg=fg,font=("Segoe UI",25,"bold"),width=2).grid(row=0,column=0,sticky="n",padx=(0,12))
        text=tk.Frame(body,bg=pal["CARD"]); text.grid(row=0,column=1,sticky="nsew")
        tk.Label(text,text=title,bg=pal["CARD"],fg=pal["TEXT"],font=("Segoe UI",12,"bold"),anchor="w").pack(fill="x")
        tk.Label(text,text=message,bg=pal["CARD"],fg=pal["MUTED"],font=("Segoe UI",9),justify="left",wraplength=430,anchor="w").pack(fill="x",pady=(5,0))
        actions=tk.Frame(body,bg=pal["CARD"]); actions.grid(row=1,column=0,columnspan=2,sticky="e",pady=(18,0))
        for i,b in enumerate(buttons):
            primary=i==len(buttons)-1
            btn=tk.Button(actions,text=b,command=lambda v=b:self._done(v),relief="flat",bd=0,
                          bg=pal["BLUE"] if primary else pal["LIGHT_BLUE"],fg="white" if primary else pal["LIGHT_BLUE_TXT"],
                          activebackground=pal["SIDEBAR_HOVER"],font=("Segoe UI",9,"bold"),padx=16,pady=7)
            btn.pack(side="left",padx=(6,0))
        self.protocol("WM_DELETE_WINDOW",lambda:self._done(buttons[0]))
        self.update_idletasks(); center_toplevel(self,parent,max(520,self.winfo_reqwidth()),max(185,self.winfo_reqheight()))
        self.wait_window(self)
    def _done(self,v): self.result=v; self.destroy()


def ask_string(parent, title, message, initial=""):
    parent = parent or tk._default_root
    pal = getattr(parent, "palette", LIGHT)
    w = tk.Toplevel(parent)
    w.title(title); w.configure(bg=pal["CARD"]); w.transient(parent); w.grab_set(); w.resizable(False, False)
    result = {"value": None}
    body = tk.Frame(w, bg=pal["CARD"]); body.pack(fill="both", expand=True, padx=22, pady=18)
    tk.Label(body,text=title,bg=pal["CARD"],fg=pal["TEXT"],font=("Segoe UI",12,"bold"),anchor="w").pack(fill="x")
    tk.Label(body,text=message,bg=pal["CARD"],fg=pal["MUTED"],font=("Segoe UI",9),justify="left",anchor="w").pack(fill="x",pady=(5,8))
    var=tk.StringVar(value=initial or "")
    entry=tk.Entry(body,textvariable=var,font=("Segoe UI",10),relief="solid",bd=1)
    entry.pack(fill="x",ipady=5); entry.select_range(0,"end"); entry.focus_set()
    actions=tk.Frame(body,bg=pal["CARD"]); actions.pack(fill="x",pady=(16,0))
    def done(ok):
        result["value"]=var.get() if ok else None
        try:w.grab_release()
        except Exception:pass
        w.destroy()
    tk.Button(actions,text="CANCELAR",command=lambda:done(False),bg=pal["LIGHT_BLUE"],fg=pal["LIGHT_BLUE_TXT"],relief="flat",font=("Segoe UI",8,"bold"),padx=14,pady=7).pack(side="right",padx=(6,0))
    tk.Button(actions,text="SALVAR",command=lambda:done(True),bg=pal["BLUE"],fg="white",relief="flat",font=("Segoe UI",8,"bold"),padx=16,pady=7).pack(side="right")
    entry.bind("<Return>",lambda e:done(True)); entry.bind("<Escape>",lambda e:done(False))
    w.protocol("WM_DELETE_WINDOW",lambda:done(False))
    w.update_idletasks(); center_toplevel(w,parent,520,max(190,w.winfo_reqheight()))
    w.wait_window()
    return result["value"]


def _parent_from_kw(kw): return kw.pop("parent",None) or tk._default_root

def install_centered_messageboxes():
    if getattr(messagebox,"_sr_patched",False): return
    def info(title,msg,**kw): SRDialog(_parent_from_kw(kw),title,str(msg),"info",("OK",)); return "ok"
    def warn(title,msg,**kw): SRDialog(_parent_from_kw(kw),title,str(msg),"warning",("OK",)); return "ok"
    def err(title,msg,**kw): SRDialog(_parent_from_kw(kw),title,str(msg),"error",("OK",)); return "ok"
    def yesno(title,msg,**kw): return SRDialog(_parent_from_kw(kw),title,str(msg),"question",("NÃO","SIM")).result=="SIM"
    messagebox.showinfo=info; messagebox.showwarning=warn; messagebox.showerror=err; messagebox.askyesno=yesno
    messagebox._sr_patched=True


def install_parented_filedialogs():
    if getattr(filedialog,"_sr_patched",False): return
    originals={n:getattr(filedialog,n) for n in ["askopenfilename","asksaveasfilename","askdirectory"]}
    for name,orig in originals.items():
        def wrapper(*args,_orig=orig,**kwargs):
            kwargs.setdefault("parent",tk._default_root)
            return _orig(*args,**kwargs)
        setattr(filedialog,name,wrapper)
    filedialog._sr_patched=True

class ToastManager:
    def __init__(self, root): self.root=root; self.items=[]
    def show(self,text,kind="info",ms=3300):
        pal=getattr(self.root,"palette",LIGHT)
        t=tk.Toplevel(self.root); t.overrideredirect(True); t.attributes("-topmost",True)
        bg={"ok":pal["GREEN"],"warning":pal["ORANGE"],"error":pal["RED"]}.get(kind,pal["LIGHT_BLUE"])
        fg={"ok":pal["GREEN_TXT"],"warning":pal["ORANGE_TXT"],"error":pal["RED_TXT"]}.get(kind,pal["LIGHT_BLUE_TXT"])
        tk.Label(t,text=text,bg=bg,fg=fg,font=("Segoe UI",9,"bold"),padx=14,pady=9,wraplength=330,justify="left").pack()
        self.root.update_idletasks(); t.update_idletasks()
        x=self.root.winfo_rootx()+self.root.winfo_width()-t.winfo_reqwidth()-22
        y=self.root.winfo_rooty()+self.root.winfo_height()-t.winfo_reqheight()-22-len(self.items)*48
        t.geometry(f"+{max(0,x)}+{max(0,y)}"); self.items.append(t)
        def close():
            try:t.destroy()
            except Exception:pass
            if t in self.items:self.items.remove(t)
        t.after(ms,close)

def file_signature(path):
    p=Path(path)
    if not p.exists(): return "missing"
    st=p.stat(); return f"{p.resolve()}|{st.st_size}|{st.st_mtime_ns}"

def cache_key(*parts): return hashlib.sha1("||".join(map(str,parts)).encode("utf-8","ignore")).hexdigest()

_DEFAULT_PRINTER_CACHE = None
_DEFAULT_PRINTER_CACHE_AT = 0.0

def default_printer_name(refresh=False):
    """Retorna a impressora padrão sem bloquear a UI quando já foi pré-carregada."""
    global _DEFAULT_PRINTER_CACHE, _DEFAULT_PRINTER_CACHE_AT
    if not refresh and _DEFAULT_PRINTER_CACHE:
        return _DEFAULT_PRINTER_CACHE
    fallback="Impressora padrão do Windows"
    if os.name!="nt":
        _DEFAULT_PRINTER_CACHE=fallback; _DEFAULT_PRINTER_CACHE_AT=time.time(); return fallback
    try:
        cmd=['powershell','-NoProfile','-Command','(Get-CimInstance Win32_Printer | Where-Object Default -eq $true | Select-Object -First 1 -ExpandProperty Name)']
        r=subprocess.run(cmd,capture_output=True,text=True,timeout=5,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        _DEFAULT_PRINTER_CACHE=r.stdout.strip() or fallback
    except Exception:
        _DEFAULT_PRINTER_CACHE=fallback
    _DEFAULT_PRINTER_CACHE_AT=time.time()
    return _DEFAULT_PRINTER_CACHE

def print_pdf(path):
    """
    Envia o PDF para a impressora padrão sem manter o SR Studio esperando
    o visualizador de PDF terminar. Alguns leitores (Edge/Chrome/Adobe)
    deixam o verbo Print aberto por vários segundos; isso não deve bloquear a interface.
    """
    path=str(Path(path).resolve())
    if os.name!="nt":
        raise RuntimeError("A impressão direta está disponível no Windows.")
    if not Path(path).exists():
        raise RuntimeError("O PDF que seria impresso não foi encontrado.")

    # Primeiro tenta o verbo Print diretamente pelo ShellExecute do Windows.
    try:
        import ctypes
        result=ctypes.windll.shell32.ShellExecuteW(None,"print",path,None,None,0)
        if int(result) > 32:
            return True
    except Exception:
        pass

    # Fallback: dispara o pedido de impressão em outro processo e devolve
    # imediatamente o controle ao SR Studio. Não usamos subprocess.run/timeout.
    try:
        cmd=[
            "powershell","-NoProfile","-WindowStyle","Hidden","-Command",
            "Start-Process -FilePath " + json.dumps(path) + " -Verb Print"
        ]
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0),
        )
        return True
    except Exception as exc:
        raise RuntimeError(
            "Não foi possível enviar o PDF para a impressora padrão do Windows. "
            "Verifique se há um leitor de PDF associado e uma impressora padrão configurada.\n\n"
            + str(exc)
        )

def apply_scaling(root, percent):
    try:
        p=float(str(percent).replace('%',''))/100.0
        root.tk.call('tk','scaling',1.3333333*p)
    except Exception: pass
