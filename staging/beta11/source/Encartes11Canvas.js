(() => {
'use strict';
const A=window.SR11,E=A.E;
const pos=(node,b)=>{node.style.left=b.x+'px';node.style.top=b.y+'px';node.style.width=b.w+'px';node.style.height=b.h+'px'};
const value=(role,p)=>{const price=A.priceParts(p.price);if(role==='NOME')return p.name||'';if(role==='PRECO_RS')return'R$';if(role==='PRECO_REAIS')return price.reais;if(role==='PRECO_CENTAVOS')return price.centavos;if(role==='UNIDADE')return p.unit||'UN';if(role==='LIMITE')return p.limit?('LIMITE DE '+p.limit+' POR CPF'):'';if(role==='PRECO_APP')return p.app?('R$ '+p.app):'';return''};
const textStyle=(node,s={})=>{node.style.fontFamily=s.font||'Segoe UI';node.style.fontSize=Number(s.fontSize||20)+'px';node.style.fontWeight=s.bold?'900':'600';node.style.fontStyle=s.italic?'italic':'normal';node.style.color=s.color||'#172033';node.style.textAlign=s.align||'left';node.style.justifyContent=s.align==='center'?'center':s.align==='right'?'flex-end':'flex-start'};
function template(pg,filled){
  for(const t of pg.templateElements||[]){
    if(t.placeholder){const slot=(pg.templateSlots||[]).find(s=>Object.values(s.fields||{}).some(f=>f.sourceId===t.id));if(slot&&filled.has(slot.id))continue}
    if(t.type==='image'){const img=E('img','tpl-img'+(t.placeholder?' tpl-placeholder':''));img.src=t.url||'';img.style.objectFit=t.style?.fit||'contain';pos(img,t);A.pageNode.appendChild(img)}
    else{const d=E('div','tpl-text'+(t.placeholder?' tpl-placeholder':''),t.text||'');textStyle(d,t.style);pos(d,t);A.pageNode.appendChild(d)}
  }
}
function slotProduct(pg,e,p,slot){
  for(const [role,f] of Object.entries(slot.fields||{})){
    if(role==='IMAGEM'){if(!p.image)continue;const img=E('img','slot-field image');img.src=p.image;img.alt=p.name||'Produto';pos(img,f);A.pageNode.appendChild(img)}
    else{const d=E('div','slot-field text',value(role,p));textStyle(d,f.style);pos(d,f);A.pageNode.appendChild(d)}
  }
  const outline=E('div','slot-outline'+(A.state.selected===e.id?' selected':''));pos(outline,slot);outline.dataset.elementId=e.id;outline.addEventListener('click',ev=>{ev.stopPropagation();A.state.selected=e.id;A.emit()});A.pageNode.appendChild(outline);
}
function genericCard(pg,e,p){
  const card=E('div','prod-card'+(A.state.selected===e.id?' selected':'')+(e.highlight===1?' highlight1':e.highlight>=2?' highlight2':''));card.dataset.elementId=e.id;pos(card,e);
  const imageBox=E('div','card-img');if(p.image){const img=E('img');img.src=p.image;img.alt=p.name||'Produto';imageBox.appendChild(img)}else imageBox.appendChild(E('div','missing','SEM IMAGEM OFICIAL'));
  imageBox.appendChild(E('span','badge',e.highlight>=2?'DESTAQUE PRINCIPAL':e.highlight===1?'DESTAQUE':'OFERTA'));
  const body=E('div','card-body');body.style.fontFamily=e.fontFamily||'Segoe UI';body.appendChild(E('div','card-name',p.name||'PRODUTO SEM NOME'));
  const line=E('div','price'),parts=A.priceParts(p.price);line.append(E('span','price-rs','R$'),E('span','price-real',parts.reais),E('span','price-cents',parts.centavos),E('span','price-unit','/'+(p.unit||'UN')));body.appendChild(line);
  if(p.app)body.appendChild(E('div','app-price','NO APP R$ '+p.app));if(p.limit)body.appendChild(E('div','limit','LIMITE DE '+p.limit+' POR CPF'));card.append(imageBox,body);A.pageNode.appendChild(card);bindMove(card,e,pg);
}
function bindMove(card,e,pg){
  let moving=false,moved=false,sx=0,sy=0,ox=0,oy=0;
  card.addEventListener('pointerdown',ev=>{if(ev.button!==0)return;A.state.selected=e.id;A.renderInspector();A.snapshot();if(ev.offsetX>card.clientWidth-20&&ev.offsetY>card.clientHeight-20)return;moving=true;moved=false;sx=ev.clientX;sy=ev.clientY;ox=e.x;oy=e.y;card.setPointerCapture(ev.pointerId)});
  card.addEventListener('pointermove',ev=>{if(!moving)return;const scale=Number(A.state.zoom)||1;let x=ox+(ev.clientX-sx)/scale,y=oy+(ev.clientY-sy)/scale;if(A.state.snap){x=Math.round(x/10)*10;y=Math.round(y/10)*10}x=Math.max(0,Math.min(pg.width-card.offsetWidth,x));y=Math.max(0,Math.min(pg.height-card.offsetHeight,y));e.x=x;e.y=y;card.style.left=x+'px';card.style.top=y+'px';moved=true});
  card.addEventListener('pointerup',()=>{if(moving&&moved)A.save();moving=false});
  const observer=new ResizeObserver(entries=>{for(const item of entries){const r=item.contentRect;if(Math.abs(e.w-r.width)>1||Math.abs(e.h-r.height)>1){e.w=Math.round(r.width);e.h=Math.round(r.height);A.save()}}});observer.observe(card);
}
A.renderCanvas=()=>{
  const pg=A.page();A.pageNode.replaceChildren();A.pageNode.classList.toggle('grid',A.state.grid);A.pageNode.style.width=pg.width+'px';A.pageNode.style.height=pg.height+'px';A.zoomNode.style.transform='scale('+A.state.zoom+')';A.zoomNode.style.marginBottom='-'+(pg.height*(1-A.state.zoom))+'px';
  const filled=new Map((pg.elements||[]).filter(e=>e.slotId).map(e=>[e.slotId,e]));template(pg,filled);
  for(const slot of pg.templateSlots||[])if(!filled.has(slot.id)){const empty=E('div','slot-empty','PRODUTO '+slot.index);pos(empty,slot);A.pageNode.appendChild(empty)}
  for(const e of pg.elements||[]){const p=A.state.products.find(x=>x.id===e.productId);if(!p)continue;if(e.slotId){const slot=(pg.templateSlots||[]).find(s=>s.id===e.slotId);if(slot)slotProduct(pg,e,p,slot)}else genericCard(pg,e,p)}
};
A.pageNode.addEventListener('click',ev=>{if(ev.target===A.pageNode){A.state.selected=null;A.emit()}});
A.centerNode.addEventListener('dragover',ev=>ev.preventDefault());
A.centerNode.addEventListener('drop',ev=>{ev.preventDefault();const id=ev.dataTransfer.getData('application/x-sr-product');if(!id)return;const r=A.pageNode.getBoundingClientRect(),scale=Number(A.state.zoom)||1;A.placeProduct(id,{x:(ev.clientX-r.left)/scale,y:(ev.clientY-r.top)/scale})});
})();
