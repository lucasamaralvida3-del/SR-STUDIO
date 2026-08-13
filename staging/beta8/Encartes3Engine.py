from __future__ import annotations

import functools
import os
import subprocess
import threading
import urllib.request
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import tkinter as tk

APP_DIR = Path(__file__).resolve().parent
EDITOR_HTML = APP_DIR / 'Encartes3_index.html'
REQUIRED_EDITOR_FILES = (
    APP_DIR / 'Encartes3_index.html',
    APP_DIR / 'Encartes3_style.css',
    APP_DIR / 'Encartes3_app.js',
    APP_DIR / 'Encartes4_beta6.js',
)
_SERVER = None
_SERVER_THREAD = None
_SERVER_LOCK = threading.Lock()


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        return


def _missing_editor_files():
    return [p.name for p in REQUIRED_EDITOR_FILES if not p.is_file()]


def _ensure_local_server():
    global _SERVER, _SERVER_THREAD
    with _SERVER_LOCK:
        if _SERVER is not None and _SERVER_THREAD is not None and _SERVER_THREAD.is_alive():
            return int(_SERVER.server_address[1])
        missing = _missing_editor_files()
        if missing:
            raise RuntimeError('Arquivos do editor ausentes: ' + ', '.join(missing))
        handler = functools.partial(_QuietHandler, directory=str(APP_DIR))
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, name='SRStudioEncartesHTTP', daemon=True)
        thread.start()
        _SERVER = server
        _SERVER_THREAD = thread
        return int(server.server_address[1])


def local_editor_url():
    return f'http://127.0.0.1:{_ensure_local_server()}/Encartes3_index.html'


def cloud_url():
    # Nome mantido por compatibilidade. A partir da Beta 8 o Encartes é local-first.
    return local_editor_url()


def preload_encarte3_data(force=False):
    return 0


def _open_app(url: str):
    candidates = [
        os.path.expandvars(r'%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe'),
        os.path.expandvars(r'%ProgramFiles%\Microsoft\Edge\Application\msedge.exe'),
        os.path.expandvars(r'%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe'),
    ]
    for exe in candidates:
        if exe and os.path.exists(exe):
            try:
                subprocess.Popen([exe, f'--app={url}', '--start-maximized'])
                return True
            except Exception:
                pass
    return bool(webbrowser.open(url))


class Encartes3Panel(tk.Frame):
    def __init__(self, parent, app=None, pal=None):
        self.app = app
        self.pal = pal or {}
        bg = self.pal.get('APP_BG', self.pal.get('BG', '#0E141D'))
        card = self.pal.get('CARD', '#17212D')
        fg = self.pal.get('TEXT', '#F3F6FA')
        muted = self.pal.get('MUTED', '#9EABBC')
        line = self.pal.get('LINE', self.pal.get('BORDER', '#2A3647'))
        blue = self.pal.get('BLUE2', '#82B0FF')
        button_blue = self.pal.get('BLUE', '#78A9FF')
        super().__init__(parent, bg=bg)

        self.status = tk.StringVar(value='Preparando o editor local...')
        self.url = ''

        outer = tk.Frame(self, bg=bg)
        outer.pack(fill='both', expand=True, padx=26, pady=22)

        header = tk.Frame(outer, bg=bg)
        header.pack(fill='x', pady=(0, 14))
        tk.Label(header, text='ENCARTES STUDIO', bg=bg, fg=fg,
                 font=('Segoe UI', 20, 'bold')).pack(side='left')
        tk.Label(header, text='BETA 8 • LOCAL FIRST', bg=self.pal.get('LIGHT_BLUE', card),
                 fg=self.pal.get('LIGHT_BLUE_TXT', blue), font=('Segoe UI', 8, 'bold'),
                 padx=10, pady=5).pack(side='right')

        box = tk.Frame(outer, bg=card, highlightthickness=1, highlightbackground=line)
        box.pack(fill='both', expand=True)
        body = tk.Frame(box, bg=card)
        body.pack(expand=True, fill='both', padx=36, pady=32)

        tk.Label(body, text='NOVO EDITOR DE ENCARTES', bg=card, fg=blue,
                 font=('Segoe UI', 22, 'bold')).pack(pady=(10, 6))
        tk.Label(body,
                 text='O editor agora roda localmente no seu computador.\nNão depende mais do antigo servidor Cloud.',
                 bg=card, fg=fg, font=('Segoe UI', 11), justify='center').pack()

        status_bg = self.pal.get('ROW_ALT', card)
        status_box = tk.Frame(body, bg=status_bg, highlightthickness=1, highlightbackground=line)
        status_box.pack(fill='x', padx=80, pady=(24, 16))
        tk.Label(status_box, textvariable=self.status, bg=status_bg, fg=muted,
                 font=('Segoe UI', 10, 'bold')).pack(padx=14, pady=12)

        tk.Button(body, text='ABRIR NOVO EDITOR', command=self.open_editor,
                  bg=button_blue, fg='white', activebackground=button_blue,
                  activeforeground='white', bd=0, padx=30, pady=13,
                  font=('Segoe UI', 11, 'bold'), cursor='hand2').pack(pady=8)
        tk.Button(body, text='VERIFICAR EDITOR', command=self.check,
                  bg=self.pal.get('SIDEBAR_HOVER', '#103E83'), fg='white',
                  activebackground=self.pal.get('SIDEBAR_HOVER', '#103E83'),
                  activeforeground='white', bd=0, padx=20, pady=8,
                  font=('Segoe UI', 9, 'bold'), cursor='hand2').pack(pady=5)

        tk.Label(body,
                 text='O editor abre em uma janela própria para executar canvas, drag-and-drop, autosave e importação de planilha com desempenho completo.',
                 bg=card, fg=muted, font=('Segoe UI', 9), wraplength=720,
                 justify='center').pack(pady=(22, 4))
        tk.Label(body,
                 text='Banco de Imagens: somente imagens oficiais cadastradas manualmente.',
                 bg=card, fg=muted, font=('Segoe UI', 8, 'bold')).pack(pady=(2, 10))

        self.after(120, self.check)

    def check(self):
        missing = _missing_editor_files()
        if missing:
            self.status.set('● ERRO — arquivos ausentes: ' + ', '.join(missing))
            return False
        try:
            self.url = local_editor_url()
            with urllib.request.urlopen(self.url, timeout=2) as response:
                ok = 200 <= int(getattr(response, 'status', 200)) < 400
            if ok:
                self.status.set('● PRONTO — editor local disponível')
                return True
        except Exception as exc:
            self.status.set('● ERRO — ' + str(exc))
            return False
        self.status.set('● ERRO — editor local indisponível')
        return False

    def open_editor(self):
        if not self.check():
            return
        try:
            _open_app(self.url)
            self.status.set('● ABERTO — editor local iniciado em janela própria')
        except Exception as exc:
            self.status.set('● ERRO AO ABRIR — ' + str(exc))
