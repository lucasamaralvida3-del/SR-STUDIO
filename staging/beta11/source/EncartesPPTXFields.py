from __future__ import annotations
import re
import xml.etree.ElementTree as ET
from SRStudio21 import norm
NS={'a':'http://schemas.openxmlformats.org/drawingml/2006/main','p':'http://schemas.openxmlformats.org/presentationml/2006/main','r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships','pr':'http://schemas.openxmlformats.org/package/2006/relationships'}

def shape_text(sp):
    paras=[]
    for p in sp.findall('.//a:p',NS):
        runs=[t.text or '' for t in p.findall('.//a:t',NS)]
        if runs: paras.append(''.join(runs))
    return '\n'.join(paras).strip()

def font_info(sp):
    rpr=sp.find('.//a:rPr',NS)
    if rpr is None:rpr=sp.find('.//a:defRPr',NS)
    out={'font':'Segoe UI','fontSize':28.0,'bold':False,'italic':False,'color':'#172033'}
    if rpr is None:return out
    try:out['fontSize']=max(6.0,float(rpr.get('sz') or 2800)/100.0)
    except:pass
    out['bold']=str(rpr.get('b') or '').lower() in {'1','true'};out['italic']=str(rpr.get('i') or '').lower() in {'1','true'}
    latin=rpr.find('./a:latin',NS)
    if latin is not None and latin.get('typeface'):out['font']=latin.get('typeface')
    c=rpr.find('.//a:solidFill/a:srgbClr',NS)
    if c is not None and c.get('val'):out['color']='#'+c.get('val')[:6]
    return out

def xfrm(node):
    xf=node.find('.//a:xfrm',NS)
    if xf is None:return None
    off=xf.find('./a:off',NS);ext=xf.find('./a:ext',NS)
    if off is None or ext is None:return None
    try:return tuple(float(x) for x in (off.get('x'),off.get('y'),ext.get('cx'),ext.get('cy')))
    except:return None

def role(text,name,font_size=0):
    t=norm((name or '')+' '+(text or ''));raw=str(text or '').strip().upper()
    if any(x in t for x in ('PRECO CENTAV','PRECO_CENTAV','CENTAVOS','CENTAVO')):return 'PRECO_CENTAVOS'
    if any(x in t for x in ('PRECO REAIS','PRECO_REAIS',' REAIS ')) or t.endswith(' REAIS'):return 'PRECO_REAIS'
    if any(x in t for x in ('PRECO APP','PRECO CLUBE','CLUBE PRECO','APP PRECO')):return 'PRECO_APP'
    if t in {'R','RS'} or raw=='R$' or 'PRECO RS' in t:return 'PRECO_RS'
    if any(x in t for x in ('IMAGEM PRODUTO','FOTO PRODUTO','IMAGEM','IMAGE PLACEHOLDER','FOTO')):return 'IMAGEM'
    if any(x in t for x in ('NOME PRODUTO','NOME DO PRODUTO','DESCRICAO PRODUTO','DESCRICAO','PRODUTO NOME')):return 'NOME'
    if 'LIMITE' in t:return 'LIMITE'
    if any(x in t for x in ('UNIDADE','UNID PRODUTO')):return 'UNIDADE'
    if re.fullmatch(r'[,\.]\s*\d{2}',raw) and font_size>=20:return 'PRECO_CENTAVOS'
    if re.fullmatch(r'\d{1,4}',raw) and font_size>=32:return 'PRECO_REAIS'
    if raw in {'UN','KG','CX','PCT','BDJ','DZ','LT','/UN','/KG','/CX','/PCT'}:return 'UNIDADE'
    return ''

def dist(a,b):
    ax,ay=a['x']+a['w']/2,a['y']+a['h']/2;bx,by=b['x']+b['w']/2,b['y']+b['h']/2
    return ((ax-bx)**2+(ay-by)**2)**.5

def make_slots(elements,w,h):
    text=[e for e in elements if e['type']=='text'];imgs=[e for e in elements if e['type']=='image'];anchors=[e for e in text if e.get('role')=='PRECO_REAIS']
    if not anchors:
        anchors=[e for e in text if re.fullmatch(r'\d{1,4}',str(e.get('text') or '').strip()) and float(e.get('style',{}).get('fontSize') or 0)>=32]
        for e in anchors:e['role']='PRECO_REAIS'
    slots=[];used=set();maxd=max(160,min(w,h)*.30)
    for i,a in enumerate(sorted(anchors,key=lambda z:(z['y'],z['x'])),1):
        fields={'PRECO_REAIS':a};used.add(a['id'])
        for r in ('PRECO_CENTAVOS','PRECO_RS','UNIDADE','NOME','LIMITE','PRECO_APP'):
            c=[e for e in text if e['id'] not in used and e.get('role')==r]
            if c:
                b=min(c,key=lambda e:dist(a,e))
                if dist(a,b)<=maxd*1.35:fields[r]=b;used.add(b['id'])
        if 'NOME' not in fields:
            c=[e for e in text if e['id'] not in used and not e.get('role') and re.search(r'[A-ZÀ-Ý]{3}',str(e.get('text') or '').upper()) and e['y']<a['y']+a['h']]
            if c:
                b=min(c,key=lambda e:dist(a,e))
                if dist(a,b)<=maxd*1.6:b['role']='NOME';fields['NOME']=b;used.add(b['id'])
        c=[e for e in imgs if e['id'] not in used]
        if c:
            b=min(c,key=lambda e:dist(a,e))
            if dist(a,b)<=maxd*1.8:b['role']='IMAGEM';fields['IMAGEM']=b;used.add(b['id'])
        if 'PRECO_CENTAVOS' not in fields:
            c=[e for e in text if e['id'] not in used and re.fullmatch(r'[,\.]?\d{2}',str(e.get('text') or '').strip())]
            if c:
                b=min(c,key=lambda e:dist(a,e))
                if dist(a,b)<=maxd:b['role']='PRECO_CENTAVOS';fields['PRECO_CENTAVOS']=b;used.add(b['id'])
        vals=list(fields.values());x=min(e['x'] for e in vals);y=min(e['y'] for e in vals);r=max(e['x']+e['w'] for e in vals);bt=max(e['y']+e['h'] for e in vals)
        slots.append({'id':f'slot_{i}','index':i,'x':x,'y':y,'w':r-x,'h':bt-y,'fields':{k:{'x':e['x'],'y':e['y'],'w':e['w'],'h':e['h'],'style':e.get('style',{}),'sourceId':e['id']} for k,e in fields.items()}})
    for e in elements:e['placeholder']=bool(e.get('role') and e['id'] in used)
    return slots
