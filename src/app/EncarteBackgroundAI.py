# -*- coding: utf-8 -*-
"""SR Studio 4.0.4 - recorte inteligente de produtos.

O motor prioriza qualidade de borda e preservação do produto. Usa OpenCV/GrabCut
quando disponível e cai para um segmentador por cor/fundo baseado em Pillow caso
OpenCV não esteja instalado no computador.

Não depende de serviço em nuvem e não altera o arquivo original.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _pil_fallback(inp: str, out: str, mode: str, feather: float, preserve_shadow: bool):
    from collections import deque
    from PIL import Image, ImageFilter, ImageStat

    im = Image.open(inp).convert("RGBA")
    w, h = im.size
    max_side = 760 if mode == "RAPIDO" else 980
    scale = min(1.0, max_side / max(w, h))
    small = im.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.Resampling.LANCZOS)
    sw, sh = small.size
    rgb = small.convert("RGB")
    px = rgb.load()

    bw = max(2, int(min(sw, sh) * 0.035))
    samples=[]; step=max(1,min(sw,sh)//150)
    for x in range(0,sw,step):
        for y in range(bw): samples.append(px[x,y]); samples.append(px[x,sh-1-y])
    for y in range(0,sh,step):
        for x in range(bw): samples.append(px[x,y]); samples.append(px[sw-1-x,y])
    if not samples: samples=[px[0,0]]
    med=lambda seq: sorted(seq)[len(seq)//2]
    bg=(med([v[0] for v in samples]),med([v[1] for v in samples]),med([v[2] for v in samples]))
    dists=[math.sqrt((r-bg[0])**2+(g-bg[1])**2+(b-bg[2])**2) for r,g,b in samples]
    spread=med(dists)
    threshold={"RAPIDO":38.0,"PRECISO":30.0,"PRODUTO":27.0,"ALIMENTO":34.0}.get(mode,30.0)+min(18.0,spread*.55)

    # Edge map impede o flood-fill de atravessar o contorno de embalagem clara.
    edges=rgb.convert('L').filter(ImageFilter.FIND_EDGES).filter(ImageFilter.GaussianBlur(.55))
    ep=edges.load(); edge_limit=38 if mode=="RAPIDO" else 28
    bgmask=bytearray(sw*sh); q=deque()
    def idx(x,y): return y*sw+x
    def color_dist(x,y):
        r,g,b=px[x,y]; return math.sqrt((r-bg[0])**2+(g-bg[1])**2+(b-bg[2])**2)
    def add_seed(x,y):
        k=idx(x,y)
        if not bgmask[k]: bgmask[k]=1;q.append((x,y))
    for x in range(sw): add_seed(x,0);add_seed(x,sh-1)
    for y in range(sh): add_seed(0,y);add_seed(sw-1,y)
    while q:
        x,y=q.popleft()
        for nx,ny in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
            if nx<0 or ny<0 or nx>=sw or ny>=sh: continue
            k=idx(nx,ny)
            if bgmask[k]: continue
            d=color_dist(nx,ny)
            # Fundo conectado + baixa energia de borda. Nas bordas externas permitimos um pouco mais.
            if d<=threshold and ep[nx,ny]<=edge_limit:
                bgmask[k]=1;q.append((nx,ny))

    # Converte o complemento do fundo conectado em foreground. Um segundo teste de cor
    # remove ilhas de fundo que ficaram isoladas por ruído, sem invadir o objeto central.
    alpha=Image.new('L',(sw,sh),0); ap=alpha.load(); cx,cy=sw/2,sh/2
    for y in range(sh):
        for x in range(sw):
            isbg=bool(bgmask[idx(x,y)])
            d=color_dist(x,y)
            nx=abs(x-cx)/(sw/2);ny=abs(y-cy)/(sh/2);central=max(0,1-max(nx,ny))
            if isbg:
                a=0
            else:
                # Pixels muito parecidos com o fundo, mas cercados por contorno do produto,
                # recebem alfa suave em vez de serem apagados de imediato.
                t=threshold-(5*central if mode in ('PRODUTO','PRECISO') else 2*central)
                a=int(_clamp((d-(t*.55))/max(12.0,t*.55),0,1)*255)
                if ep[x,y]>edge_limit*1.35: a=max(a,190)
            ap[x,y]=a
    if mode!='RAPIDO':
        alpha=alpha.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.MinFilter(3))
    if preserve_shadow:
        # Sombra natural leve: dilata a máscara e mantém pixels escuros próximos com alfa baixo.
        dil=alpha.filter(ImageFilter.MaxFilter(11)); dp=dil.load(); ap=alpha.load()
        bgv=(bg[0]+bg[1]+bg[2])/3
        for y in range(sh):
            for x in range(sw):
                if ap[x,y]>20 or dp[x,y]<60: continue
                r,g,b=px[x,y];v=(r+g+b)/3;dark=_clamp((bgv-v)/max(40,bgv*.55),0,1)
                if dark>.12 and color_dist(x,y)<threshold*1.7: ap[x,y]=int(dark*92)
    blur=max(.35,float(feather)*scale)
    if blur>0: alpha=alpha.filter(ImageFilter.GaussianBlur(blur))
    if (sw,sh)!=(w,h): alpha=alpha.resize((w,h),Image.Resampling.LANCZOS)
    im.putalpha(alpha)
    Path(out).parent.mkdir(parents=True,exist_ok=True);im.save(out,'PNG')
    stat=ImageStat.Stat(alpha);coverage=float(stat.mean[0]/255.0)
    return {"engine":"PIL-FLOOD+EDGE-MATTE","mode":mode,"coverage":round(coverage,4),"shadow":bool(preserve_shadow),"background_spread":round(spread,2)}


def _opencv_segment(inp: str, out: str, mode: str, feather: float, preserve_shadow: bool):
    import cv2
    import numpy as np
    from PIL import Image

    pil = Image.open(inp).convert("RGBA")
    orig = np.array(pil)
    oh, ow = orig.shape[:2]
    max_side = {"RAPIDO":1000,"PRECISO":1700,"PRODUTO":1800,"ALIMENTO":1700}.get(mode,1700)
    sc = min(1.0, max_side / max(ow, oh))
    if sc < 0.999:
        work = cv2.resize(orig, (max(1,round(ow*sc)), max(1,round(oh*sc))), interpolation=cv2.INTER_AREA)
    else:
        work = orig.copy()
    h,w = work.shape[:2]
    bgr = cv2.cvtColor(work[:,:,:3], cv2.COLOR_RGB2BGR)
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)

    bw = max(2, int(min(w,h)*0.035))
    border = np.concatenate([
        lab[:bw,:,:].reshape(-1,3), lab[-bw:,:,:].reshape(-1,3),
        lab[:, :bw,:].reshape(-1,3), lab[:, -bw:,:].reshape(-1,3)
    ], axis=0)
    bg_lab = np.median(border,axis=0)
    dist = np.linalg.norm(lab-bg_lab.reshape(1,1,3),axis=2)

    # Robustez do fundo: se a borda é muito variável, reduzimos as marcações de "fundo certo".
    border_dist = np.linalg.norm(border-bg_lab.reshape(1,3),axis=1)
    spread = float(np.percentile(border_dist, 75))
    bg_strict = _clamp(8.0 + spread*0.35, 8.0, 24.0)
    bg_prob = _clamp(22.0 + spread*0.55, 18.0, 45.0)

    GC_BGD, GC_FGD, GC_PR_BGD, GC_PR_FGD = 0,1,2,3
    mask = np.full((h,w), GC_PR_BGD, np.uint8)
    edge = max(2,int(min(w,h)*0.018))
    mask[:edge,:]=GC_BGD;mask[-edge:,:]=GC_BGD;mask[:,:edge]=GC_BGD;mask[:,-edge:]=GC_BGD
    mask[dist < bg_strict] = GC_BGD

    # Área provável do produto. Evita perder embalagem clara sobre fundo branco.
    mx = int(w*(0.045 if mode=="ALIMENTO" else 0.065)); my=int(h*(0.04 if mode=="ALIMENTO" else 0.055))
    central = np.zeros((h,w),np.uint8); central[my:max(my+1,h-my),mx:max(mx+1,w-mx)] = 1
    strong = (dist > (bg_prob + (8 if mode=="ALIMENTO" else 5))) & (central>0)
    mask[strong] = GC_PR_FGD

    # Bordas/contornos fechados ajudam em caixas e pacotes quase brancos.
    gray = cv2.cvtColor(bgr,cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray,45 if mode!="RAPIDO" else 65,150 if mode!="RAPIDO" else 180)
    ksz = 5 if mode in ("PRECISO","PRODUTO") else 3
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(ksz,ksz))
    closed = cv2.morphologyEx(edges,cv2.MORPH_CLOSE,kernel,iterations=2 if mode!="RAPIDO" else 1)
    contours,_ = cv2.findContours(closed,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    center=(w/2,h/2)
    for c in sorted(contours,key=cv2.contourArea,reverse=True)[:30]:
        area=cv2.contourArea(c)
        if area < w*h*0.002 or area > w*h*0.88: continue
        x,y,cw,ch=cv2.boundingRect(c); cc=(x+cw/2,y+ch/2)
        nd=math.hypot((cc[0]-center[0])/max(1,w),(cc[1]-center[1])/max(1,h))
        if nd<0.36 and cw>max(8,w*.05) and ch>max(8,h*.05):
            tmp=np.zeros((h,w),np.uint8); cv2.drawContours(tmp,[c],-1,255,-1)
            mask[(tmp>0)&(dist>bg_strict*0.75)] = GC_PR_FGD

    # Em alimentos, saturação/variação cromática costuma ser uma pista útil.
    if mode=="ALIMENTO":
        sat=hsv[:,:,1]
        mask[(sat>42)&(central>0)&(dist>bg_strict*.7)] = GC_PR_FGD

    bgdModel=np.zeros((1,65),np.float64);fgdModel=np.zeros((1,65),np.float64)
    iters={"RAPIDO":2,"PRECISO":7,"PRODUTO":8,"ALIMENTO":7}.get(mode,7)
    try:
        cv2.grabCut(bgr,mask,None,bgdModel,fgdModel,iters,cv2.GC_INIT_WITH_MASK)
        fg=((mask==GC_FGD)|(mask==GC_PR_FGD)).astype(np.uint8)*255
    except Exception:
        fg=((dist>bg_prob)&(central>0)).astype(np.uint8)*255

    # Mantém somente componentes plausíveis. Produto principal costuma tocar a região central.
    n,labels,stats,cents=cv2.connectedComponentsWithStats((fg>0).astype(np.uint8),8)
    keep=np.zeros_like(fg)
    candidates=[]
    for i in range(1,n):
        area=stats[i,cv2.CC_STAT_AREA]
        if area < w*h*0.00045: continue
        cx,cy=cents[i]; nd=math.hypot((cx-w/2)/max(1,w),(cy-h/2)/max(1,h))
        score=area*(1.55 if nd<0.23 else 1.0)*(1.25 if (stats[i,cv2.CC_STAT_WIDTH]>w*.08 and stats[i,cv2.CC_STAT_HEIGHT]>h*.08) else 1.0)
        candidates.append((score,i,area,nd))
    candidates.sort(reverse=True)
    if candidates:
        top_area=candidates[0][2]
        for score,i,area,nd in candidates:
            if i==candidates[0][1] or (area>top_area*.055 and nd<0.38): keep[labels==i]=255
    else:
        keep=fg

    # Caso o GrabCut tenha ficado excessivamente agressivo, usa máscara cromática conservadora.
    coverage=float((keep>0).mean())
    if coverage<0.008 or coverage>0.90:
        keep=((dist>bg_prob)&(central>0)).astype(np.uint8)*255
        coverage=float((keep>0).mean())

    # Fechamento pequeno + preservação de detalhes. Evita erosão forte em alças/folhas.
    if mode!="RAPIDO":
        keep=cv2.morphologyEx(keep,cv2.MORPH_CLOSE,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(3,3)),iterations=1)
        keep=cv2.morphologyEx(keep,cv2.MORPH_OPEN,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(2,2)),iterations=1)

    alpha=keep.astype(np.float32)/255.0
    if preserve_shadow:
        # Sombra natural: pixels escuros próximos do produto ganham alfa parcial, sem manter todo o fundo.
        dil=cv2.dilate((keep>0).astype(np.uint8),cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(15,15)),iterations=2)>0
        ring=dil&(keep==0)
        bg_bgr=cv2.cvtColor(np.uint8([[cv2.cvtColor(np.uint8([[bg_lab.astype(np.uint8)]]),cv2.COLOR_LAB2BGR)[0,0]]]),cv2.COLOR_BGR2BGR)[0,0] if False else None
        value=hsv[:,:,2].astype(np.float32)
        border_v=np.median(np.concatenate([value[:bw,:].ravel(),value[-bw:,:].ravel(),value[:,:bw].ravel(),value[:,-bw:].ravel()]))
        dark=np.clip((border_v-value)/max(35.0,border_v*.5),0,1)
        shadow=(ring&(dark>.10)&(dist<bg_prob*1.55)).astype(np.float32)*dark*.42
        alpha=np.maximum(alpha,shadow)

    # Feather proporcional ao modo; preserva interior 100% opaco.
    sigma=max(0.35,float(feather)*sc)
    if sigma>0:
        soft=cv2.GaussianBlur((alpha*255).astype(np.uint8),(0,0),sigmaX=sigma,sigmaY=sigma).astype(np.float32)/255.0
        # Mantém o miolo opaco e usa o blur só na borda.
        core=cv2.erode((keep>0).astype(np.uint8),np.ones((3,3),np.uint8),iterations=1)>0
        alpha=np.where(core,1.0,np.maximum(alpha,soft))
    alpha=np.clip(alpha,0,1)

    if (w,h)!=(ow,oh):
        alpha=cv2.resize(alpha,(ow,oh),interpolation=cv2.INTER_LINEAR)

    rgba=orig.copy().astype(np.float32)
    # Descontaminação de halo claro nas bordas: remove parte da cor estimada do fundo.
    a=alpha[:,:,None]
    if a.shape[:2] != rgba.shape[:2]:
        a=cv2.resize(alpha,(ow,oh),interpolation=cv2.INTER_LINEAR)[:,:,None]
    # Estima RGB do fundo nas bordas originais.
    rgb=orig[:,:,:3].astype(np.float32)
    eb=max(1,int(min(ow,oh)*.025))
    bord=np.concatenate([rgb[:eb].reshape(-1,3),rgb[-eb:].reshape(-1,3),rgb[:,:eb].reshape(-1,3),rgb[:,-eb:].reshape(-1,3)],axis=0)
    bg_rgb=np.median(bord,axis=0).reshape(1,1,3)
    edge_band=(a>0.03)&(a<0.98)
    safe=np.maximum(a,0.10)
    corrected=(rgb-bg_rgb*(1.0-a))/safe
    corrected=np.clip(corrected,0,255)
    rgb=np.where(edge_band,corrected,rgb)

    final=np.dstack([rgb,np.clip(a[:,:,0]*255,0,255)]).astype(np.uint8)
    Path(out).parent.mkdir(parents=True,exist_ok=True)
    Image.fromarray(final,"RGBA").save(out,"PNG")
    return {
        "engine":"OPENCV-GRABCUT+EDGE-MATTE",
        "mode":mode,
        "coverage":round(float((alpha>.2).mean()),4),
        "background_spread":round(spread,2),
        "shadow":bool(preserve_shadow),
        "feather":float(feather),
    }


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--input",required=True)
    ap.add_argument("--output",required=True)
    ap.add_argument("--mode",default="PRODUTO",choices=["RAPIDO","PRECISO","PRODUTO","ALIMENTO"])
    ap.add_argument("--feather",type=float,default=1.4)
    ap.add_argument("--shadow",action="store_true")
    ns=ap.parse_args()
    if not Path(ns.input).is_file():
        raise SystemExit("Imagem de entrada não encontrada.")
    try:
        meta=_opencv_segment(ns.input,ns.output,ns.mode,ns.feather,ns.shadow)
    except Exception as exc:
        meta=_pil_fallback(ns.input,ns.output,ns.mode,ns.feather,ns.shadow)
        meta["fallback_reason"]=str(exc)[:240]
    print(json.dumps(meta,ensure_ascii=False))

if __name__=="__main__":
    main()
