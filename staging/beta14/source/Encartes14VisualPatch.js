(() => {
'use strict';
const A=window.SR11,E=A.E;
if(!A||A.__BETA14_VISUAL__)return;A.__BETA14_VISUAL__=true;
A.VERSION='4.0.13 • Beta 14';
const ver=document.querySelector('.ver');if(ver)ver.textContent=A.VERSION;
const oldRender=A.renderCanvas;
const pos=(node,b)=>{node.style.left=b.x+'px';node.style.top=b.y+'px';node.style.width=b.w+'px';node.style.height=b.h+'px'};
const priceValue=(role,p)=>{const q=A.priceParts(p.price);if(role==='NOME')return p.name||'';if(role==='PRECO_RS')return'R$';if(role==='PRECO_REAIS')return q.reais;if(role==='PRECO_CENTAVOS')return q.centavos;if(role==='UNIDADE')return p.unit||'UN';if(role==='LIMITE')return p.limit?('LIMITE DE '+p.limit+' POR CPF'):'';if(role==='PRECO_APP')return p.app?('R$ '+p.app):'';return''};
const intersect=(a,b)=>Math.max(0,Math.min(a.x+a.w,b.x+b.w)-Math.max(a.x,b.x))*Math.max(0,Math.min(a.y+a.h,b.y+b.h)-Math.max(a.y,b.y));
function imageSafeBox(slot,f){
  const px=Math.max(3,f.w*.045),py=Math.max(3,f.h*.045),gap=Math.max(3,Math.min(f.w,f.h)*.025);
  let b={x:f.x+px,y:f.y+py,w:Math.max(20,f.w-px*2),h:Math.max(20,f.h-py*2)};
  const blockers=['PRECO_REAIS','PRECO_CENTAVOS','PRECO_RS','UNIDADE','PRECO_APP'];
  for(const role of blockers){const q=slot.fields?.[role];if(!q||!intersect(b,q))continue;
    const bc={x:b.x+b.w/2,y:b.y+b.h/2},qc={x:q.x+q.w/2,y:q.y+q.h/2};
    if(Math.abs(qc.x-bc.x)>=Math.abs(qc.y-bc.y)){
      if(qc.x>=bc.x){const edge=q.x-gap;if(edge>b.x+b.w*.38)b.w=edge-b.x;}
      else{const edge=q.x+q.w+gap,old=b.x+b.w;if(edge<old-b.w*.38){b.x=edge;b.w=old-edge;}}
    }else{
      if(qc.y>=bc.y){const edge=q.y-gap;if(edge>b.y+b.h*.38)b.h=edge-b.y;}
      else{const edge=q.y+q.h+gap,old=b.y+b.h;if(edge<old-b.h*.38){b.y=edge;b.h=old-edge;}}
    }
  }
  return b;
}
function applyTextStyle(node,s={},role=''){
  node.style.fontFamily=s.font||'Segoe UI';node.style.fontWeight=s.bold?'900':'700';node.style.fontStyle=s.italic?'italic':'normal';node.style.color=s.color||'#172033';
  const align=s.align||((role==='NOME'||role.startsWith('PRECO_')||role==='UNIDADE')?'center':'left');node.style.textAlign=align;node.style.justifyContent=align==='center'?'center':align==='right'?'flex-end':'flex-start';
  const va=s.vAlign||'center';node.style.alignItems=va==='bottom'?'flex-end':va==='top'?'flex-start':'center';node.style.lineHeight=role==='NOME'?'1.02':'1';node.style.padding=role==='NOME'?'1px 3px':'1px';node.style.boxSizing='border-box';
}
function fitText(node,role,f){
  const s=f.style||{},base=Number(s.fontSize||20);let min,max;
  if(role==='NOME'){min=Math.max(7,base*.42);max=Math.max(base,Math.min(base*1.18,f.h*.9));node.style.whiteSpace='normal';node.style.overflowWrap='break-word';node.style.wordBreak='normal';}
  else{min=Math.max(6,base*.48);max=Math.max(base,Math.min(base*1.3,f.h*1.08));node.style.whiteSpace='nowrap';}
  node.style.overflow='hidden';
  let lo=min,hi=max,best=min;
  for(let i=0;i<14;i++){const m=(lo+hi)/2;node.style.fontSize=m+'px';const ok=node.scrollWidth<=node.clientWidth+1&&node.scrollHeight<=node.clientHeight+1;if(ok){best=m;lo=m}else hi=m;}
  node.style.fontSize=best+'px';
  if(role==='NOME'&&node.scrollHeight>node.clientHeight+1){node.style.lineHeight='.94';}
}
function addText(role,f,p){const d=E('div','slot-field text',priceValue(role,p));d.dataset.role=role;d.style.zIndex='45';applyTextStyle(d,f.style||{},role);pos(d,f);A.pageNode.appendChild(d);fitText(d,role,f);if(document.fonts?.ready)document.fonts.ready.then(()=>fitText(d,role,f));return d;}
function addImage(slot,f,p){if(!p.image)return;const b=imageSafeBox(slot,f),wrap=E('div','slot-image-clip');wrap.style.position='absolute';wrap.style.overflow='hidden';wrap.style.zIndex='8';wrap.style.pointerEvents='none';wrap.style.borderRadius=f.autoDetected?Math.min(24,Math.max(8,Math.min(b.w,b.h)*.12))+'px':'0';pos(wrap,b);const img=E('img','slot-field image');img.src=p.image;img.alt=p.name||'Produto';img.style.position='absolute';img.style.inset='0';img.style.width='100%';img.style.height='100%';img.style.objectFit=f.fit||f.style?.fit||'contain';img.style.objectPosition='center';img.style.padding='2%';img.style.boxSizing='border-box';wrap.appendChild(img);A.pageNode.appendChild(wrap);}
function renderTemplate(pg){const bg=E('img','tpl-img');bg.src=pg.backgroundUrl;bg.alt='Design original do Canva';bg.style.objectFit='fill';bg.style.pointerEvents='none';bg.style.userSelect='none';bg.style.zIndex='1';pos(bg,{x:0,y:0,w:pg.width,h:pg.height});A.pageNode.appendChild(bg);}
function renderSlot(pg,e,p,slot){
  const image=slot.fields?.IMAGEM;if(image)addImage(slot,image,p);
  const order=['NOME','PRECO_RS','PRECO_REAIS','PRECO_CENTAVOS','UNIDADE','LIMITE','PRECO_APP'];for(const role of order){const f=slot.fields?.[role];if(f)addText(role,f,p);}
  const outline=E('div','slot-outline'+(A.state.selected===e.id?' selected':''));outline.style.zIndex='80';pos(outline,slot);outline.dataset.elementId=e.id;outline.addEventListener('click',ev=>{ev.stopPropagation();A.state.selected=e.id;A.emit()});A.pageNode.appendChild(outline);
}
A.renderCanvas=()=>{
  const pg=A.page();if(!pg?.backgroundUrl){return oldRender();}
  A.pageNode.replaceChildren();A.pageNode.classList.remove('grid');A.pageNode.style.width=pg.width+'px';A.pageNode.style.height=pg.height+'px';A.zoomNode.style.transform='scale('+A.state.zoom+')';A.zoomNode.style.marginBottom='-'+(pg.height*(1-A.state.zoom))+'px';renderTemplate(pg);
  const filled=new Map((pg.elements||[]).filter(e=>e.slotId).map(e=>[e.slotId,e]));
  for(const slot of pg.templateSlots||[])if(!filled.has(slot.id)){const empty=E('div','slot-empty','PRODUTO '+slot.index);empty.style.zIndex='70';pos(empty,slot);A.pageNode.appendChild(empty)}
  for(const e of pg.elements||[]){const p=A.state.products.find(x=>x.id===e.productId);if(!p)continue;if(e.slotId){const slot=(pg.templateSlots||[]).find(s=>s.id===e.slotId);if(slot)renderSlot(pg,e,p,slot)}else{oldRender();return}}
};
A.renderAll?.();
console.info('[SR Studio] Beta 14 visual patch ativo');
})();
