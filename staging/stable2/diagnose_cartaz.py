from pathlib import Path
import re
root=Path('work/files')
patterns=[r'cartaz',r'ger[aã]o',r'promo',r'manual',r'nome[_ ]?item',r'produto',r'pdf',r'render']
rows=[]
for p in root.rglob('*'):
    if not p.is_file() or p.suffix.lower() not in {'.py','.js','.html','.json','.txt'}: continue
    try: text=p.read_text(encoding='utf-8',errors='ignore')
    except: continue
    low=text.lower()
    score=sum(1 for pat in patterns if re.search(pat,low,re.I))
    if score>=3:
        hits=[]
        for i,line in enumerate(text.splitlines(),1):
            if any(re.search(pat,line,re.I) for pat in patterns):
                hits.append(f'{i}: {line[:220]}')
                if len(hits)>=35: break
        rows.append((score,str(p.relative_to(root)),hits))
rows.sort(key=lambda x:(-x[0],x[1]))
out=[]
for score,name,hits in rows[:60]:
    out.append(f'### {name} score={score}')
    out.extend(hits);out.append('')
Path('staging/stable2/diagnostic.txt').write_text('\n'.join(out),encoding='utf-8')
print('arquivos candidatos',len(rows))
