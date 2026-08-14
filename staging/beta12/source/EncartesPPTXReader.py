from __future__ import annotations
import io, os, re, uuid, zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import quote
from SRStudio21 import norm
from EncartesAssets import session_dir, safe_name
from EncartesPPTXFields import NS, shape_text, font_info, xfrm, role, make_slots
from EncartesPPTXVisual import render_slide_backgrounds


def _slides(names):
    items=[n for n in names if re.fullmatch(r'ppt/slides/slide\d+\.xml',n)]
    return sorted(items,key=lambda n:int(re.search(r'(\d+)',Path(n).stem).group(1)))


def _rels(z,slide_name):
    path=f'ppt/slides/_rels/{Path(slide_name).name}.rels'
    if path not in z.namelist():return {}
    root=ET.fromstring(z.read(path));out={}
    for rel in root.findall('./pr:Relationship',NS):out[rel.get('Id')]=rel.get('Target') or ''
    return out


def _member(target):
    return os.path.normpath(str(Path('ppt/slides')/target)).replace('\\','/')


def _shape_id(prop):
    try:return int(prop.get('id') or 0) if prop is not None else 0
    except:return 0


def _text_elements(root,index,sx,sy):
    out=[];seq=0
    for sp in root.findall('.//p:sp',NS):
        tr=xfrm(sp)
        if not tr:continue
        seq+=1;x,y,w,h=tr;text=shape_text(sp);style=font_info(sp)
        prop=sp.find('./p:nvSpPr/p:cNvPr',NS);name=prop.get('name') if prop is not None else f'Texto {seq}'
        out.append({'id':f's{index}_t{seq}','pptxId':_shape_id(prop),'type':'text','name':name,'text':text,'x':x*sx,'y':y*sy,'w':w*sx,'h':h*sy,'style':style,'role':role(text,name,style.get('fontSize',0))})
    return out


def _images(z,root,rels,index,sx,sy,asset_dir):
    out=[];seq=0
    for pic in root.findall('.//p:pic',NS):
        tr=xfrm(pic)
        if not tr:continue
        seq+=1;x,y,w,h=tr
        prop=pic.find('./p:nvPicPr/p:cNvPr',NS);name=prop.get('name') if prop is not None else f'Imagem {seq}'
        blip=pic.find('.//a:blip',NS);rid=blip.get('{'+NS['r']+'}embed') if blip is not None else '';target=rels.get(rid,'');url=''
        member=_member(target) if target else ''
        if member and member in z.namelist():
            fn=safe_name(Path(member).name,'imagem.bin');(asset_dir/fn).write_bytes(z.read(member));url=f'/api/encartes/pptx-asset?session={asset_dir.name}&name={quote(fn)}'
        r='IMAGEM' if any(k in norm(name) for k in ('IMAGEM','FOTO','PRODUTO')) else ''
        out.append({'id':f's{index}_i{seq}','pptxId':_shape_id(prop),'type':'image','name':name,'url':url,'x':x*sx,'y':y*sy,'w':w*sx,'h':h*sy,'style':{'fit':'contain'},'role':r})
    return out


def _dynamic_meta(elements):
    ids=[];names=[]
    for e in elements:
        if not e.get('placeholder'):continue
        pid=e.get('pptxId')
        if pid and pid not in ids:ids.append(pid)
        name=str(e.get('name') or '').strip()
        if name and name not in names:names.append(name)
    return ids,names


def parse_pptx(data:bytes,source_name='modelo.pptx'):
    if not data or len(data)>120*1024*1024:raise ValueError('PPTX vazio ou muito grande.')
    session=uuid.uuid4().hex;asset_dir=session_dir(session)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        if 'ppt/presentation.xml' not in z.namelist():raise ValueError('PPTX inválido: presentation.xml ausente.')
        pres=ET.fromstring(z.read('ppt/presentation.xml'));size=pres.find('.//p:sldSz',NS);cx=float(size.get('cx') if size is not None else 9144000);cy=float(size.get('cy') if size is not None else 12927600)
        page_w=794.0;page_h=round(page_w*(cy/cx),2);pages=[]
        for index,slide_name in enumerate(_slides(z.namelist()),1):
            root=ET.fromstring(z.read(slide_name));sx=page_w/cx;sy=page_h/cy;elements=_text_elements(root,index,sx,sy);elements+=_images(z,root,_rels(z,slide_name),index,sx,sy,asset_dir)
            slots=make_slots(elements,page_w,page_h);dynamic_ids,dynamic_names=_dynamic_meta(elements)
            pages.append({'id':f'pptx_{index}','name':f'Página {index}','width':page_w,'height':page_h,'templateElements':elements,'templateSlots':slots,'elements':[],'_dynamicPptxIds':dynamic_ids,'_dynamicPptxNames':dynamic_names})

    visual=render_slide_backgrounds(data,pages,asset_dir,source_name)
    urls=visual.get('urls') or []
    for i,page in enumerate(pages):
        page['backgroundUrl']=urls[i] if i<len(urls) else ''
        page.pop('_dynamicPptxIds',None);page.pop('_dynamicPptxNames',None)

    return {
        'ok':True,'source':source_name,'session':session,'pages':pages,
        'pageCount':len(pages),'slotCount':sum(len(p['templateSlots']) for p in pages),
        'visualMode':visual.get('mode') or 'xml-fallback','visualWarning':visual.get('warning') or ''
    }
