from __future__ import annotations
import argparse, hashlib, importlib.util, json, shutil, sys
from pathlib import Path

AFTER_SHA='2e706558132e8893377c0dd6772d55c6c9d3a739'
PPTX_SHA='12e13842b6d61eba126ae35bb8d81f8f8a6c514024a2750ce8f807751b4bfd19'
PROFILES=('costela','pernil','musculo','moela')


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): h.update(b)
    return h.hexdigest()


def load(path,name):
    s=importlib.util.spec_from_file_location(name,Path(path).resolve()); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


def seg(label,text):
    if len(text)!=3: raise RuntimeError(f'expected 3-char DECIMAL, got {text!r}')
    return [text[:2],text[2:]] if label=='C' else [text[:1],text[1:2],text[2:]]


def row(root,profile,role='decimal'):
    for r in json.loads((Path(root)/'text-variant-metrics.json').read_text(encoding='utf-8')):
        if r.get('VARIANT')=='current' and r.get('PROFILE')==profile and r.get('ROLE')==role: return r
    raise RuntimeError(f'missing {profile}/{role}')


def topology(image):
    import numpy as np
    a=np.asarray(image.convert('RGB'),dtype=np.uint8); h,w=a.shape[:2]
    colors,counts=np.unique(a.reshape(-1,3),axis=0,return_counts=True); bg=colors[int(counts.argmax())].astype(int)
    mask=(a.astype(int)-bg.reshape(1,1,3)).min(axis=2)>=45; seen=np.zeros_like(mask,bool); comps=[]
    for y in range(h):
        for x in range(w):
            if not mask[y,x] or seen[y,x]: continue
            st=[(x,y)]; seen[y,x]=1; pts=[]
            while st:
                cx,cy=st.pop(); pts.append((cx,cy))
                for dy in (-1,0,1):
                    for dx in (-1,0,1):
                        if dx==dy==0: continue
                        nx,ny=cx+dx,cy+dy
                        if 0<=nx<w and 0<=ny<h and mask[ny,nx] and not seen[ny,nx]: seen[ny,nx]=1; st.append((nx,ny))
            xs=[p[0] for p in pts]; ys=[p[1] for p in pts]; box=[min(xs),min(ys),max(xs)+1,max(ys)+1]
            if len(pts)<5 or (box[1]==0 and box[2]-box[0]>=.35*w): continue
            comps.append({'area':len(pts),'bbox':box,'cx':sum(xs)/len(xs),'cy':sum(ys)/len(ys),'base':float(max(ys)),'pts':pts})
    clusters=[]
    for c in sorted(comps,key=lambda z:z['base']):
        best=None
        for i,g in enumerate(clusters):
            if abs(c['base']-max(v['base'] for v in g))<=4: best=i; break
        (clusters.append([c]) if best is None else clusters[best].append(c))
    out=[]
    for g in clusters:
        ar=sum(c['area'] for c in g); out.append({'centroid_y':sum(c['cy']*c['area'] for c in g)/ar,'baseline_y':max(c['base'] for c in g),'bbox':[min(c['bbox'][0] for c in g),min(c['bbox'][1] for c in g),max(c['bbox'][2] for c in g),max(c['bbox'][3] for c in g)],'component_count':len(g)})
    out.sort(key=lambda z:z['baseline_y'])
    ink=None if not comps else [min(c['bbox'][0] for c in comps),min(c['bbox'][1] for c in comps),max(c['bbox'][2] for c in comps),max(c['bbox'][3] for c in comps)]
    kept=np.zeros_like(mask,bool)
    for c in comps:
        for xx,yy in c['pts']: kept[yy,xx]=1
    proj=kept.sum(axis=1).astype(int).tolist()
    active=[i for i,v in enumerate(proj) if v]; runs=[]
    for y in active:
        if not runs or y>runs[-1][1]+1: runs.append([y,y])
        else: runs[-1][1]=y
    valleys=[]
    for l,r in zip(out,out[1:]):
        lo=int(l['baseline_y'])+1; hi=int(r['baseline_y'])-1; vals=proj[lo:hi+1] if hi>=lo else []
        lp=max(proj[l['bbox'][1]:l['bbox'][3]] or [1]); rp=max(proj[r['bbox'][1]:r['bbox'][3]] or [1]); vm=min(vals) if vals else 0
        valleys.append({'min_projection':int(vm),'depth':1.0-float(vm)/max(1,min(lp,rp))})
    overlap=[]
    for i,l in enumerate(out):
        for j in range(i+1,len(out)):
            r=out[j]; ov=max(0,min(l['bbox'][2],r['bbox'][2])-max(l['bbox'][0],r['bbox'][0])); den=max(1,min(l['bbox'][2]-l['bbox'][0],r['bbox'][2]-r['bbox'][0])); overlap.append({'clusters':[i+1,j+1],'x_overlap_ratio':float(ov)/den})
    clean=[{k:v for k,v in c.items() if k!='pts'} for c in comps]
    return {'REFERENCE_LINE_CLUSTER_COUNT':len(out),'REFERENCE_LINE_CLUSTER_Y':[c['centroid_y'] for c in out],'REFERENCE_LINE_CLUSTER_BASELINE_Y':[c['baseline_y'] for c in out],'INK_BBOX':ink,'CONNECTED_COMPONENT_COUNT':len(comps),'COMPONENTS':clean,'Y_PROJECTION':proj,'ACTIVE_ROW_RUNS':runs,'VALLEY_DEPTHS':valleys,'COMPONENT_OVERLAP_X':overlap,'BACKGROUND_RGB':[int(v) for v in bg]}


def overlay(image,t,output):
    from PIL import ImageDraw
    im=image.convert('RGB').copy(); d=ImageDraw.Draw(im); colors=('lime','cyan','magenta')
    for c in t['COMPONENTS']: d.rectangle(tuple(c['bbox']),outline='orange')
    for i,(y,box) in enumerate(zip(t['REFERENCE_LINE_CLUSTER_BASELINE_Y'],[None]*len(t['REFERENCE_LINE_CLUSTER_BASELINE_Y']))):
        col=colors[i%len(colors)]; yy=int(round(y)); d.line((0,yy,im.width-1,yy),fill=col); d.text((1,max(0,yy-8)),f'L{i+1}',fill=col)
    output.parent.mkdir(parents=True,exist_ok=True); im.resize((im.width*8,im.height*8)).save(output)


def planner_trace(text,rect,style,font,planner,latin,renderer,Core,Gui,production):
    width=max(.1,float(rect.width())); sf=renderer._pptx_source_layout_font(style,font,Gui); fm=Gui.QFontMetricsF(sf)
    measure=lambda v:float(renderer._pptx_source_layout_width(v,style,font,Gui))
    plan=planner.break_plan(text,bool(style.get('diagnostic_latin_ln_brk_office_effective',False)),str(style.get('diagnostic_horz_overflow_office_effective') or 'overflow'),latin,Core)
    allowed=sorted(int(p) for p in plan['OFFICE_FILTERED_BREAK_POSITIONS'] if 0<int(p)<len(text)); ends=allowed+[len(text)]; start=0; pieces=[]; steps=[]
    while start<len(text):
        ev=[{'END':e,'PREFIX':text[start:e],'INK_WIDTH':float(fm.tightBoundingRect(text[start:e]).width()),'SOURCE_WIDTH':measure(text[start:e]),'FITS':measure(text[start:e])<=width+.01} for e in ends if e>start]
        fit=[x for x in ev if x['FITS']]; end=max(fit,key=lambda x:x['END'])['END'] if fit else next(e for e in ends if e>start)
        steps.append({'START':start,'CANDIDATES':ev,'CHOSEN':end}); pieces.append(text[start:end]); start=end
    em=production(text,rect,style,font,Core,Gui)
    return {'TEXT':text,'AVAILABLE_WIDTH':width,'OFFICE_FILTERED_BREAK_POSITIONS':allowed,'PREFIX_STEPS':steps,'FINAL_SEGMENTS':pieces,'CURRENT_EMERGENCY_SEGMENTS':[] if em is None else [str(x[0]) for x in em],'wrap':str(style.get('pptx_wrap') or ''),'spAutoFit':str(style.get('pptx_auto_fit') or '').lower()=='shape','horzOverflow':str(style.get('diagnostic_horz_overflow_office_effective') or 'overflow'),'latinLnBrk':bool(style.get('diagnostic_latin_ln_brk_office_effective',False))}


def run_forced(delegate,planner,latin,args,source,label,out,Core,Gui,renderer,traces,layouts,production):
    from srstudio.graphics2.model import BindingRole
    oa=delegate.apply_variant; oh=planner.planner_helper
    def apply(document,slots,semantics,variant):
        oa(document,slots,semantics,variant)
        for p,s in zip(delegate.PROFILE_ORDER,slots):
            n=document.active_page.node(s.node_by_role[BindingRole.PRICE_CENTS.value]); n.style['diagnostic_decimal_profile']=p; n.style['diagnostic_forced_segments']=seg(label,str(n.text or ''))
    def helper(r,l,text,rect,style,font,core,gui):
        p=style.get('diagnostic_decimal_profile'); forced=style.get('diagnostic_forced_segments')
        if p and forced:
            if p not in traces: traces[p]=planner_trace(str(text or ''),rect,style,font,planner,l,r,core,gui,production)
            lay=[l._layout_tuple(x,rect,style,font,gui,r,i) for i,x in enumerate(forced)]; layouts.setdefault(label,{})[p]=[float(x[2]) for x in lay]; return lay
        return oh(r,l,text,rect,style,font,core,gui)
    delegate.apply_variant=apply; planner.planner_helper=helper
    try: planner.run_delegate(delegate,args,out,source,latin,Core,Gui,renderer,True)
    finally: delegate.apply_variant=oa; planner.planner_helper=oh


def main():
    ap=argparse.ArgumentParser();
    for name in ('planner-module','delegate','latin-module','pptx','source-root','reference','baseline-planner','out'): ap.add_argument('--'+name,required=True,type=Path)
    a=ap.parse_args(); a.out.mkdir(parents=True,exist_ok=True)
    if sha(a.pptx)!=PPTX_SHA: raise RuntimeError('exact PPTX SHA mismatch')
    sys.path.insert(0,str(a.source_root.resolve()/'src'))
    from PIL import Image
    from PySide6 import QtCore,QtGui
    from srstudio.graphics2 import qt_renderer as renderer
    from srstudio.graphics2.fonts import ensure_qgui_application
    app=ensure_qgui_application(); app.processEvents()
    delegate=load(a.delegate,'top_delegate'); planner=load(a.planner_module,'top_planner'); latin=load(a.latin_module,'top_latin'); source=latin.extract_source(a.pptx.resolve(),delegate.ROLE_IDS,QtCore); production=renderer._pptx_shape_autofit_wrapped_layout
    traces={}; layouts={}; roots={}
    for label in ('C','D'):
        r1=a.out/'variants'/f'{label}-run1'; r2=a.out/'variants'/f'{label}-run2'; run_forced(delegate,planner,latin,a,source,label,r1,QtCore,QtGui,renderer,traces,layouts,production); run_forced(delegate,planner,latin,a,source,label,r2,QtCore,QtGui,renderer,traces,layouts,production); roots[label]=(r1,r2)
    ref=Image.open(a.reference).convert('RGB'); topo={}; matrix={}; deterministic=True
    for p in delegate.PROFILE_ORDER:
        matrix[p]={}
        for label in ('C','D'):
            r1,r2=roots[label]; rr=row(r1,p); crop=r1/'crops'/f'current-{p}-decimal.png'; crop2=r2/'crops'/f'current-{p}-decimal.png'; out=a.out/'decimal-crops'/f'{p}-{label}.png'; out.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(crop,out)
            bas=layouts[label][p]; rt=topology(Image.open(crop)); matrix[p][label]={'SEGMENTS':seg(label,str(rr.get('TEXT') or rr.get('DIAG_TEXT') or '')),'SEMANTIC_LINE_COUNT':len(bas),'BASELINE_COUNT':len(bas),'BASELINES':bas,'LINE_CLUSTER_Y':[v-bas[0] for v in bas] if bas else [],'MAE':float(rr.get('MAE') or 0),'CHANGED_RATIO':float(rr.get('CHANGED_RATIO') or 0),'CROP_BOX':rr['CROP_BOX'],'RASTER_CLUSTER_COUNT':rt['REFERENCE_LINE_CLUSTER_COUNT'],'RASTER_INK_BBOX':rt['INK_BBOX']}; deterministic &= sha(crop)==sha(crop2) and sha(r1/'_page-current.png')==sha(r2/'_page-current.png')
        box=tuple(int(v) for v in matrix[p]['C']['CROP_BOX']); ri=ref.crop(box); t=topology(ri); ov=a.out/'reference-topology'/f'{p}-reference-overlay.png'; overlay(ri,t,ov); topo[p]=t
        for label in ('C','D'):
            x=matrix[p][label]; x['TOPOLOGY_MATCH']=x['SEMANTIC_LINE_COUNT']==t['REFERENCE_LINE_CLUSTER_COUNT']
            rb=t['REFERENCE_LINE_CLUSTER_BASELINE_Y']; cb=x['BASELINES']; x['REFERENCE_CLUSTER_DISTANCE']=None if len(rb)!=len(cb) else sum(abs((u-rb[0])-(v-cb[0])) for u,v in zip(rb,cb))/len(rb)
            x['BBOX_DISTANCE']=None if t['INK_BBOX'] is None or x['RASTER_INK_BBOX'] is None else float(sum(abs(int(u)-int(v)) for u,v in zip(t['INK_BBOX'],x['RASTER_INK_BBOX'])))
    cseg={p:matrix[p]['C']['SEGMENTS'] for p in delegate.PROFILE_ORDER}; generic={p:traces[p]['FINAL_SEGMENTS'] for p in delegate.PROFILE_ORDER}; emergency={p:traces[p]['CURRENT_EMERGENCY_SEGMENTS'] for p in delegate.PROFILE_ORDER}
    greedy=True
    for p in delegate.PROFILE_ORDER:
        s=traces[p]['PREFIX_STEPS'][0]; by={x['END']:x for x in s['CANDIDATES']}; greedy &= traces[p]['OFFICE_FILTERED_BREAK_POSITIONS']==[1,2] and by[1]['FITS'] and by[2]['FITS'] and not by[3]['FITS'] and s['CHOSEN']==2 and generic[p]==cseg[p]
    src_ok=all(traces[p]['wrap']=='square' and traces[p]['spAutoFit'] and traces[p]['horzOverflow']=='overflow' and not traces[p]['latinLnBrk'] for p in delegate.PROFILE_ORDER)
    controls=planner.current_rows(roots['C'][0]); currency=all(int(controls[(p,'currency')].get('LINE_COUNT') or 0)==2 and planner.probe_sha(a.baseline_planner,p,'currency')==planner.probe_sha(roots['C'][0],p,'currency') for p in delegate.PROFILE_ORDER); unit=all(int(controls[(p,'unit')].get('LINE_COUNT') or 0)==1 and planner.probe_sha(a.baseline_planner,p,'unit')==planner.probe_sha(roots['C'][0],p,'unit') for p in delegate.PROFILE_ORDER); integer=all(planner.probe_sha(a.baseline_planner,p,'integer')==planner.probe_sha(roots['C'][0],p,'integer') for p in delegate.PROFILE_ORDER); name=all(planner.probe_sha(a.baseline_planner,p,'name')==planner.probe_sha(roots['C'][0],p,'name') for p in delegate.PROFILE_ORDER)
    ref2=all(topo[p]['REFERENCE_LINE_CLUSTER_COUNT']==2 for p in delegate.PROFILE_ORDER); cmatch=all(matrix[p]['C']['TOPOLOGY_MATCH'] for p in delegate.PROFILE_ORDER); eqc=all(generic[p]==cseg[p] and emergency[p]==cseg[p] for p in delegate.PROFILE_ORDER); latin_keep=not bool(planner.break_plan('KG',False,'overflow',latin,QtCore)['OFFICE_FILTERED_BREAK_POSITIONS'])
    confirmed=bool(deterministic and ref2 and cmatch and greedy and eqc and src_ok and latin_keep and currency and unit and integer and name)
    pd=matrix['pernil']['D']; pc=matrix['pernil']['C']; classification='PIXEL METRIC OVERFIT' if pc['TOPOLOGY_MATCH'] and not pd['TOPOLOGY_MATCH'] and pd['MAE']<pc['MAE'] else None
    summary={'AFTER_SHA':AFTER_SHA,'PPTX_SHA256':PPTX_SHA,'REFERENCE_LINE_CLUSTER_COUNT':{p:topo[p]['REFERENCE_LINE_CLUSTER_COUNT'] for p in delegate.PROFILE_ORDER},'REFERENCE_LINE_CLUSTER_Y':{p:topo[p]['REFERENCE_LINE_CLUSTER_Y'] for p in delegate.PROFILE_ORDER},'C_TOPOLOGY_MATCH':{p:matrix[p]['C']['TOPOLOGY_MATCH'] for p in delegate.PROFILE_ORDER},'PERNIL_REFERENCE_CLUSTERS':topo['pernil']['REFERENCE_LINE_CLUSTER_COUNT'],'PERNIL_C_CLUSTERS':pc['SEMANTIC_LINE_COUNT'],'PERNIL_D_CLUSTERS':pd['SEMANTIC_LINE_COUNT'],'PERNIL_C_MAE':pc['MAE'],'PERNIL_D_MAE':pd['MAE'],'PERNIL_D_TOPOLOGY_MATCH':pd['TOPOLOGY_MATCH'],'PERNIL_D_LOWER_MAE_CLASSIFICATION':classification,'LONGEST_FITTING_PREFIX_RULE':greedy,'CURRENT_EMERGENCY_SEGMENTS':emergency,'GENERIC_PLANNER_SEGMENTS':generic,'SOURCE_SEMANTICS_PRESERVED':src_ok,'LATIN_WORD_INDIVISIBLE':latin_keep,'CURRENCY_PRESERVED':currency,'UNIT_PRESERVED':unit,'INTEGER_PRESERVED':integer,'NAME_PRESERVED':name,'ALL_VARIANTS_DETERMINISTIC':deterministic,'GENERIC_RULE_CONFIRMED':confirmed,'PRODUCTION_FILES_CHANGED':0,'READY_TO_MODIFY_PR_111':confirmed}
    (a.out/'decimal-reference-topology.json').write_text(json.dumps(topo,indent=2),encoding='utf-8'); (a.out/'decimal-segmentation-matrix.json').write_text(json.dumps(matrix,indent=2),encoding='utf-8'); (a.out/'planner-decision-trace.json').write_text(json.dumps(traces,indent=2),encoding='utf-8'); (a.out/'decimal-planner-final-summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8'); print(json.dumps(summary,indent=2)); return 0

if __name__=='__main__': raise SystemExit(main())
