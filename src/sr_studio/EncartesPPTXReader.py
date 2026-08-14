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
        text=shape_text(sp)
        if not text:continue
        seq+=1;x,y,w,h=tr;style=font_info(sp)
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


def _direct_xfrm(sp):
    xf=sp.find('./p:spPr/a:xfrm',NS)
    if xf is None:return None
    off=xf.find('./a:off',NS);ext=xf.find('./a:ext',NS)
    if off is None or ext is None:return None
    try:return tuple(float(v) for v in (off.get('x'),off.get('y'),ext.get('cx'),ext.get('cy')))
    except:return None


def _group_transform(group,parent=None):
    xf=group.find('./p:grpSpPr/a:xfrm',NS)
    if xf is None:return parent
    def pair(tag,attrs):
        el=xf.find('./'+tag,NS)
        if el is None:return None
        try:return tuple(float(el.get(a)) for a in attrs)
        except:return None
    off=pair('a:off',('x','y'));ext=pair('a:ext',('cx','cy'))
    choff=pair('a:chOff',('x','y'));chext=pair('a:chExt',('cx','cy'))
    if not all((off,ext,choff,chext)) or not chext[0] or not chext[1]:return parent
    scale_x=ext[0]/chext[0];scale_y=ext[1]/chext[1]
    def transform(rect):
        x,y,w,h=rect
        mapped=(off[0]+(x-choff[0])*scale_x,off[1]+(y-choff[1])*scale_y,w*scale_x,h*scale_y)
        return parent(mapped) if parent else mapped
    return transform


def _near_white(sp):
    solid=sp.find('./p:spPr/a:solidFill',NS)
    if solid is None:return False
    rgb=solid.find('./a:srgbClr',NS)
    if rgb is not None:
        value=(rgb.get('val') or '').upper()
        if re.fullmatch(r'[0-9A-F]{6}',value):
            channels=[int(value[i:i+2],16) for i in (0,2,4)]
            return min(channels)>=238
    scheme=solid.find('./a:schemeClr',NS)
    if scheme is not None and (scheme.get('val') or '').lower() in {'lt1','bg1'}:return True
    system=solid.find('./a:sysClr',NS)
    if system is not None:
        value=(system.get('lastClr') or '').upper()
        if re.fullmatch(r'[0-9A-F]{6}',value):
            channels=[int(value[i:i+2],16) for i in (0,2,4)]
            return min(channels)>=238
    return False


def _image_area_candidates(root,index,sx,sy,page_w,page_h):
    """Encontra áreas brancas vazias, inclusive dentro de grupos do Canva.

    O Canva costuma exportar a moldura de foto como Freeform branca. Como as coordenadas
    dentro de p:grpSp são locais, é necessário aplicar chOff/chExt -> off/ext recursivamente.
    """
    out=[];seq=0
    tree=root.find('.//p:spTree',NS)
    if tree is None:return out

    def walk(parent,transform=None):
        nonlocal seq
        for child in list(parent):
            kind=child.tag.rsplit('}',1)[-1]
            if kind=='grpSp':
                walk(child,_group_transform(child,transform))
                continue
            if kind!='sp' or shape_text(child):continue
            rect=_direct_xfrm(child)
            if rect is None or not _near_white(child):continue
            if transform:rect=transform(rect)
            x,y,w,h=rect;x*=sx;y*=sy;w*=sx;h*=sy
            # Ignora detalhes brancos minúsculos; mantém caixas típicas de imagem de produto.
            if w<page_w*.075 or h<page_h*.065 or w*h<page_w*page_h*.008:continue
            if w>page_w*.72 or h>page_h*.72:continue
            seq+=1
            prop=child.find('./p:nvSpPr/p:cNvPr',NS);name=prop.get('name') if prop is not None else f'Área branca {seq}'
            out.append({
                'id':f's{index}_a{seq}','pptxId':_shape_id(prop),'type':'shape','name':name,'text':'',
                'x':x,'y':y,'w':w,'h':h,'style':{'fit':'contain'},'role':'IMAGEM_AREA',
                'imageCandidate':True,'placeholder':False
            })
    walk(tree)
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
        pres=ET.fromstring(z.read('ppt/presentation.xml'));size=pres.find('.//p:sldSz',NS)
        cx=float(size.get('cx') if size is not None else 9144000);cy=float(size.get('cy') if size is not None else 12927600)
        page_w=794.0;page_h=round(page_w*(cy/cx),2);pages=[]
        for index,slide_name in enumerate(_slides(z.namelist()),1):
            root=ET.fromstring(z.read(slide_name));sx=page_w/cx;sy=page_h/cy
            elements=_text_elements(root,index,sx,sy)
            elements+=_images(z,root,_rels(z,slide_name),index,sx,sy,asset_dir)
            elements+=_image_area_candidates(root,index,sx,sy,page_w,page_h)
            slots=make_slots(elements,page_w,page_h);dynamic_ids,dynamic_names=_dynamic_meta(elements)
            auto_images=sum(1 for s in slots if (s.get('fields') or {}).get('IMAGEM',{}).get('autoDetected'))
            pages.append({
                'id':f'pptx_{index}','name':f'Página {index}','width':page_w,'height':page_h,
                'templateElements':elements,'templateSlots':slots,'elements':[],
                'autoImageSlots':auto_images,'_dynamicPptxIds':dynamic_ids,'_dynamicPptxNames':dynamic_names
            })

    visual=render_slide_backgrounds(data,pages,asset_dir,source_name)
    urls=visual.get('urls') or []
    for i,page in enumerate(pages):
        page['backgroundUrl']=urls[i] if i<len(urls) else ''
        page.pop('_dynamicPptxIds',None);page.pop('_dynamicPptxNames',None)

    return {
        'ok':True,'source':source_name,'session':session,'pages':pages,
        'pageCount':len(pages),'slotCount':sum(len(p['templateSlots']) for p in pages),
        'autoImageSlotCount':sum(int(p.get('autoImageSlots') or 0) for p in pages),
        'visualMode':visual.get('mode') or 'xml-fallback','visualWarning':visual.get('warning') or ''
    }
