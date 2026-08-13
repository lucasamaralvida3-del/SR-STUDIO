from pathlib import Path
import functools,json,re,threading,urllib.request
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer

p=Path('work/files')
v=json.loads((p/'version.json').read_text(encoding='utf-8'))
assert v['distribution_version']=='4.0.7-hybrid.beta8'
assert v['release_label']=='Beta 8'

h=(p/'Encartes3_index.html').read_text(encoding='utf-8')
assert 'href="Encartes3_style.css"' in h
assert 'src="Encartes3_app.js"' in h
assert 'src="Encartes4_beta6.js"' in h
refs=re.findall(r'(?:href|src)="([^"]+)"',h)
missing=[x for x in refs if not x.startswith(('http:','https:','data:','#')) and not (p/x).exists()]
assert not missing, missing

engine=(p/'Encartes3Engine.py').read_text(encoding='utf-8')
assert 'pad=28' not in engine
assert 'padx=26' in engine and 'pady=22' in engine
assert "ThreadingHTTPServer(('127.0.0.1', 0)" in engine
assert 'local_editor_url' in engine

class Quiet(SimpleHTTPRequestHandler):
    def log_message(self,*args):
        pass

handler=functools.partial(Quiet,directory=str(p))
server=ThreadingHTTPServer(('127.0.0.1',0),handler)
thread=threading.Thread(target=server.serve_forever,daemon=True)
thread.start()
try:
    url=f'http://127.0.0.1:{server.server_address[1]}/Encartes3_index.html'
    body=urllib.request.urlopen(url,timeout=3).read().decode('utf-8','replace')
    assert 'Encartes3_app.js' in body
    assert 'Encartes4_beta6.js' in body
    print('Editor local validado:',url)
finally:
    server.shutdown()
    server.server_close()
