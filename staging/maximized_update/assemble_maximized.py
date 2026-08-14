from pathlib import Path
import json, re, sys

root=Path(sys.argv[2] if len(sys.argv)>2 else 'work')
R=root/'files'
channel=(sys.argv[1] if len(sys.argv)>1 else 'stable').lower()

p=R/'SR_Studio_Gerador.py'
text=p.read_text(encoding='utf-8')

# Faz a janela principal abrir maximizada em toda inicialização.
# state('zoomed') no Windows respeita a área útil (barra de tarefas continua visível).
old='''        self.build_layout()\n        try: preload_sria_data()\n'''
new='''        self.build_layout()\n        # Sempre inicia maximizado. Repetimos após o idle/120 ms para garantir\n        # o estado mesmo em máquinas onde o Windows demora a materializar a janela.\n        self.after_idle(self._open_maximized)\n        self.after(120, self._open_maximized)\n        try: preload_sria_data()\n'''
if old not in text:
    raise SystemExit('Ponto de inicialização da janela não localizado')
text=text.replace(old,new,1)

anchor='''    def build_layout(self):\n'''
method='''    def _open_maximized(self):\n        \"\"\"Abre o SR Studio maximizado, preservando a barra de tarefas do sistema.\"\"\"\n        try:\n            self.state("zoomed")\n            return\n        except Exception:\n            pass\n        try:\n            self.attributes("-zoomed", True)\n            return\n        except Exception:\n            pass\n        # Fallback para ambientes sem suporte ao estado zoomed.\n        try:\n            self.update_idletasks()\n            self.geometry(f"{self.winfo_screenwidth()}x{self.winfo_screenheight()}+0+0")\n        except Exception:\n            pass\n\n    def build_layout(self):\n'''
if 'def _open_maximized(self):' not in text:
    if anchor not in text:
        raise SystemExit('Método build_layout não localizado')
    text=text.replace(anchor,method,1)

p.write_text(text,encoding='utf-8')

# Atualiza somente a identificação de distribuição; a base funcional continua 4.0.16.
vpath=R/'version.json'
v=json.loads(vpath.read_text(encoding='utf-8'))
if channel=='stable':
    v.update(distribution_version='4.0.16-hybrid.stable4',product_version='4.0.16',channel='stable',release_label='Stable 4',updated_at='2026-08-14T11:39:00-03:00')
    display='4.0.16 • Stable 4'
    versao='SR Studio 4.0.16 • Stable 4\nJanela principal abre sempre maximizada, ajustada à área útil da tela.\n'
else:
    v.update(distribution_version='4.0.16-hybrid.beta19',product_version='4.0.16',channel='beta',release_label='Beta 19',updated_at='2026-08-14T11:39:00-03:00')
    display='4.0.16 • Beta 19'
    versao='SR Studio 4.0.16 • Beta 19\nSincronizada com Stable 4: janela principal abre sempre maximizada.\n'
vpath.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(R/'VERSAO.txt').write_text(versao,encoding='utf-8')

# Mantém o Encartes Studio com a mesma identificação do canal instalado.
js=R/'Encartes10_beta16.js'
if js.exists():
    s=js.read_text(encoding='utf-8')
    s,n=re.subn(r"A\.VERSION='4\.0\.16 • [^']+'",f"A.VERSION='{display}'",s,count=1)
    if n==0:
        raise SystemExit('Versão do Encartes não localizada')
    js.write_text(s,encoding='utf-8')

print('Abertura maximizada aplicada para',channel)
