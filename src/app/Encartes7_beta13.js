(() => {
'use strict';
const A=window.SR11=window.SR11||{};
A.VERSION='4.0.12 • Beta 13';
A.STORE='srstudio_encartes_beta11_project_v2';
A.uid=(p='id')=>p+'_'+Date.now().toString(36)+'_'+Math.random().toString(36).slice(2,8);
A.copy=o=>JSON.parse(JSON.stringify(o));
A.norm=s=>String(s??'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').trim().toUpperCase();
A.money=v=>{if(v===null||v===undefined||v==='')return'';let s=String(v).trim().replace(/\s/g,'').replace(/\.(?=\d{3}(\D|$))/g,'').replace(',','.');const n=Number(s.replace(/[^0-9.-]/g,''));return Number.isFinite(n)?n.toFixed(2).replace('.',','):String(v)};
A.priceParts=v=>{const x=(A.money(v)||'--,--').split(',');return{reais:x[0]||'--',centavos:','+(x[1]||'00').padEnd(2,'0').slice(0,2)}};
A.newPage=(name='Página')=>({id:A.uid('pg'),name,width:794,height:1123,elements:[],templateElements:[],templateSlots:[],category:''});
const empty=()=>({products:[],pages:[A.newPage('Página 1')],pageIndex:0,selected:null,grid:true,snap:true,zoom:.75,categoryFilter:'TODAS',fonts:[],projectName:'Novo Encarte'});
try{A.state=JSON.parse(localStorage.getItem(A.STORE)||'null')||empty()}catch{A.state=empty()}
if(!Array.isArray(A.state.pages)||!A.state.pages.length)A.state=empty();
A.past=[];A.future=[];A.listeners=new Set();
A.page=()=>A.state.pages[A.state.pageIndex]||A.state.pages[0];
A.emit=()=>A.listeners.forEach(fn=>{try{fn()}catch(e){console.error(e)}});
A.onChange=fn=>A.listeners.add(fn);
A.save=()=>{try{localStorage.setItem(A.STORE,JSON.stringify(A.state))}catch{}};
A.snapshot=()=>{A.past.push(JSON.stringify(A.state));if(A.past.length>60)A.past.shift();A.future=[]};
A.commit=()=>{A.save();A.emit()};
A.undo=()=>{if(!A.past.length)return;A.future.push(JSON.stringify(A.state));A.state=JSON.parse(A.past.pop());A.commit()};
A.redo=()=>{if(!A.future.length)return;A.past.push(JSON.stringify(A.state));A.state=JSON.parse(A.future.pop());A.commit()};
A.usedIds=()=>new Set(A.state.pages.flatMap(p=>p.elements||[]).map(e=>e.productId));
A.categories=()=>['TODAS',...new Set(A.state.products.map(p=>p.category||'SEM CATEGORIA').sort((a,b)=>a.localeCompare(b,'pt-BR')))];
A.emptySlot=(pg,pos)=>{const used=new Set((pg.elements||[]).map(e=>e.slotId).filter(Boolean));let slots=(pg.templateSlots||[]).filter(s=>!used.has(s.id));if(!slots.length)return null;if(!pos)return slots[0];return slots.sort((a,b)=>Math.hypot(a.x+a.w/2-pos.x,a.y+a.h/2-pos.y)-Math.hypot(b.x+b.w/2-pos.x,b.y+b.h/2-pos.y))[0]};
A.placeProduct=(pid,pos)=>{if(!A.state.products.some(p=>p.id===pid))return;A.snapshot();const pg=A.page(),slot=A.emptySlot(pg,pos);let e;if(slot)e={id:A.uid('e'),productId:pid,slotId:slot.id,highlight:0};else{const n=pg.elements.filter(x=>!x.slotId).length;e={id:A.uid('e'),productId:pid,slotId:null,x:pos?.x??30+(n%3)*245,y:pos?.y??30+Math.floor(n/3)*275,w:220,h:250,highlight:0,fontFamily:'Segoe UI'}}pg.elements.push(e);A.state.selected=e.id;A.commit()};
A.addPage=()=>{A.snapshot();A.state.pages.push(A.newPage('Página '+(A.state.pages.length+1)));A.state.pageIndex=A.state.pages.length-1;A.state.selected=null;A.commit()};
A.duplicatePage=()=>{A.snapshot();const p=A.copy(A.page());p.id=A.uid('pg');p.name=(p.name||'Página')+' - cópia';p.elements=(p.elements||[]).map(e=>({...e,id:A.uid('e')}));A.state.pages.splice(A.state.pageIndex+1,0,p);A.state.pageIndex++;A.state.selected=null;A.commit()};
A.deletePage=()=>{if(A.state.pages.length<2)return false;A.snapshot();A.state.pages.splice(A.state.pageIndex,1);A.state.pageIndex=Math.min(A.state.pageIndex,A.state.pages.length-1);A.state.selected=null;A.commit();return true};
A.deleteSelected=()=>{const pg=A.page();if(!pg.elements.some(e=>e.id===A.state.selected))return;A.snapshot();pg.elements=pg.elements.filter(e=>e.id!==A.state.selected);A.state.selected=null;A.commit()};
A.duplicateSelected=()=>{const pg=A.page(),e=pg.elements.find(x=>x.id===A.state.selected);if(!e)return false;const n={...A.copy(e),id:A.uid('e')};if(n.slotId){const s=A.emptySlot(pg);if(!s)return false;n.slotId=s.id}else{n.x+=18;n.y+=18}A.snapshot();pg.elements.push(n);A.state.selected=n.id;A.commit();return true};
A.autoLayout=()=>{
  A.snapshot();
  if(A.state.pages.some(p=>(p.templateSlots||[]).length)){
    const used=A.usedIds();
    for(const pg of A.state.pages)for(const slot of pg.templateSlots||[]){if(pg.elements.some(e=>e.slotId===slot.id))continue;const p=A.state.products.find(x=>!used.has(x.id));if(!p)break;pg.elements.push({id:A.uid('e'),productId:p.id,slotId:slot.id,highlight:0});used.add(p.id)}
    A.state.pageIndex=0;A.state.selected=null;A.commit();return'template';
  }
  const levels=new Map();for(const pg of A.state.pages)for(const e of pg.elements||[])levels.set(e.productId,Math.max(levels.get(e.productId)||0,+e.highlight||0));
  const groups=new Map();for(const p of A.state.products){const c=p.category||'SEM CATEGORIA';if(!groups.has(c))groups.set(c,[]);groups.get(c).push(p)}
  A.state.pages=[];
  for(const [cat,list0] of groups){
    const list=[...list0].sort((a,b)=>(levels.get(b.id)||0)-(levels.get(a.id)||0));let pg=A.newPage(cat);pg.category=cat;A.state.pages.push(pg);let cell=0;
    for(const p of list){
      let lv=levels.get(p.id)||0;
      if(cell>=12){pg=A.newPage(cat+' '+(A.state.pages.filter(x=>x.category===cat).length+1));pg.category=cat;A.state.pages.push(pg);cell=0}
      let col=cell%3,row=Math.floor(cell/3),wide=lv>=2&&col<2;
      if(lv>=2&&col===2){cell++;if(cell>=12){pg=A.newPage(cat+' '+(A.state.pages.filter(x=>x.category===cat).length+1));pg.category=cat;A.state.pages.push(pg);cell=0}col=cell%3;row=Math.floor(cell/3);wide=true}
      pg.elements.push({id:A.uid('e'),productId:p.id,x:28+col*246,y:35+row*265,w:wide?466:220,h:wide?250:240,highlight:lv,fontFamily:'Segoe UI'});
      cell+=wide?2:1;
    }
  }
  if(!A.state.pages.length)A.state.pages=[A.newPage('Página 1')];A.state.pageIndex=0;A.state.selected=null;A.commit();return'category';
};
})();

(() => {
'use strict';
const A=window.SR11;
A.pick=(row,names)=>{const m={};Object.keys(row||{}).forEach(k=>m[A.norm(k)]=row[k]);for(const n of names){const v=m[A.norm(n)];if(v!==undefined&&v!==null&&String(v).trim()!=='')return v}return''};
A.detectUnit=row=>{let u=A.pick(row,['UNIDADE','UN','UND','UN VENDA']);if(u)return A.norm(u).slice(0,6);const e=A.pick(row,['ENTRADA']);if(typeof e==='string'){const x=A.norm(e);if(x.includes('KG'))return'KG';if(x.includes('UN'))return'UN'}if(typeof e==='number'&&!Number.isInteger(e))return'KG';return''};
A.rowProduct=row=>{const name=A.pick(row,['PRODUTO','PRODUTOS','NOME','DESCRICAO','DESCRIÇÃO','ITEM','DESCRICAO PRODUTO']);const code=A.pick(row,['EAN','CODIGO','CÓDIGO','COD','COD BARRAS','CODIGO DE BARRAS']);const price=A.pick(row,['PRECO PROMOCAO','PREÇO PROMOÇÃO','PROMOCAO','PROMOÇÃO','PRECO','PREÇO','VAREJO']);const app=A.pick(row,['PRECO APP','PREÇO APP','APP','CLUBE','PRECO CLUBE']);const limit=A.pick(row,['LIMITE','LIMITE CPF','LIMITE POR CPF']);if(!name&&!code&&!price)return null;return{id:A.uid('p'),name:String(name||'').trim(),code:String(code||'').trim(),price:A.money(price),app:A.money(app),limit:String(limit||'').trim(),unit:A.detectUnit(row),image:'',category:'SEM CATEGORIA',bankFound:false,matchMethod:''}};
A.headerIndex=rows=>{let best=0,score=-1;for(let i=0;i<Math.min(rows.length,20);i++){let s=0;for(const x of rows[i]||[]){const v=A.norm(x);if(/EAN|CODIGO|COD\b|PRODUTO|DESCRICAO|ITEM|PROMOCAO|PRECO|VENDA|LIMITE|ENTRADA/.test(v))s+=2;if(v)s+=.05}if(s>score){score=s;best=i}}return best};
A.rowsFromSheet=ws=>{const m=XLSX.utils.sheet_to_json(ws,{header:1,defval:''});if(!m.length)return[];const hi=A.headerIndex(m),heads=m[hi].map(x=>String(x||'').trim());return m.slice(hi+1).filter(r=>r.some(x=>String(x||'').trim())).map(r=>{const o={};heads.forEach((h,i)=>{if(h)o[h]=r[i]??''});return o})};
A.resolveBank=async products=>{const response=await fetch('/api/encartes/resolve-products',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({items:products.map(p=>({code:p.code,name:p.name}))})});const data=await response.json();if(!response.ok||!data.ok)throw Error(data.error||'Banco de Produtos indisponível');let found=0;products.forEach((p,i)=>{const x=(data.results||[])[i]||{};if(x.found){found++;p.bankFound=true;p.matchMethod=x.match_method||'';p.identityKey=x.identity_key||'';p.name=x.canonical_name||p.name||('PRODUTO '+p.code);p.unit=p.unit||x.unidade||'UN';p.image=x.image||'';p.code=x.codigo||x.codigo_ciss||p.code;p.category=x.categoria||p.category}else{p.name=p.name||('CÓDIGO '+(p.code||'NÃO IDENTIFICADO'));p.unit=p.unit||'UN'}});return found};
A.importSheet=async file=>{if(!file)return{total:0,found:0};let rows=[];if(/\.csv$|\.txt$/i.test(file.name)){const wb=XLSX.read(await file.text(),{type:'string'});rows=A.rowsFromSheet(wb.Sheets[wb.SheetNames[0]])}else{const wb=XLSX.read(await file.arrayBuffer(),{type:'array'});rows=A.rowsFromSheet(wb.Sheets[wb.SheetNames[0]])}const products=rows.map(A.rowProduct).filter(Boolean);if(!products.length)throw Error('Nenhuma linha de produto reconhecida.');let found=0;try{found=await A.resolveBank(products)}catch(e){console.warn(e);products.forEach(p=>{p.name=p.name||('CÓDIGO '+(p.code||'NÃO IDENTIFICADO'));p.unit=p.unit||'UN'})}A.snapshot();A.state.products.push(...products);A.commit();return{total:products.length,found}};
A.registerFont=async f=>{if(!f?.family||!f?.url)return;try{const face=new FontFace(f.family,'url("'+f.url+'")');document.fonts.add(await face.load())}catch(e){console.warn(e)}};
A.loadFonts=async()=>{try{const r=await fetch('/api/encartes/fonts'),d=await r.json();if(d.ok){A.state.fonts=d.fonts||[];for(const f of A.state.fonts)await A.registerFont(f)}}catch(e){console.warn(e)}return A.state.fonts};
A.importFonts=async files=>{let ok=0;for(const file of [...(files||[])]){const response=await fetch('/api/encartes/font-upload?name='+encodeURIComponent(file.name),{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:await file.arrayBuffer()});const data=await response.json();if(!response.ok||!data.ok)throw Error(data.error||('Falha ao importar '+file.name));A.state.fonts=A.state.fonts.filter(x=>x.name!==data.font.name);A.state.fonts.push(data.font);await A.registerFont(data.font);ok++}A.commit();return ok};
})();

(() => {
'use strict';
const A=window.SR11;
A.validate=()=>{
  const out=[];
  for(let pi=0;pi<A.state.pages.length;pi++){
    const pg=A.state.pages[pi],label=pg.name||('Página '+(pi+1));
    if(!(pg.elements||[]).length)out.push({severity:'warn',message:label+': página sem produtos.'});
    const seen=new Set();
    for(const e of pg.elements||[]){
      const p=A.state.products.find(x=>x.id===e.productId);
      if(!p){out.push({severity:'error',message:label+': produto vinculado não existe.'});continue}
      if(seen.has(p.id))out.push({severity:'warn',message:label+': '+p.name+' aparece mais de uma vez.'});
      seen.add(p.id);
      if(!p.name)out.push({severity:'error',message:label+': produto sem nome.'});
      if(!p.price||p.price==='0,00')out.push({severity:'error',message:label+': '+p.name+' sem preço.'});
      if(!p.image)out.push({severity:'error',message:label+': '+p.name+' sem imagem oficial.'});
      if(!p.unit)out.push({severity:'warn',message:label+': '+p.name+' sem unidade.'});
      if(!p.bankFound)out.push({severity:'warn',message:label+': '+p.name+' não localizado no Banco de Produtos.'});
      if(!e.slotId&&(e.x<0||e.y<0||e.x+e.w>pg.width||e.y+e.h>pg.height))out.push({severity:'error',message:label+': '+p.name+' está fora da página.'});
      if(!e.slotId&&p.name.length>55)out.push({severity:'warn',message:label+': nome longo em '+p.name+'.'});
      if(e.slotId){
        const slot=(pg.templateSlots||[]).find(x=>x.id===e.slotId);
        if(!slot)out.push({severity:'error',message:label+': vínculo do template perdido.'});
        else for(const field of ['NOME','IMAGEM','PRECO_REAIS','PRECO_CENTAVOS'])if(!slot.fields?.[field])out.push({severity:'warn',message:label+': bloco '+slot.index+' não possui campo '+field+'.'});
      }
    }
    const normal=(pg.elements||[]).filter(e=>!e.slotId);
    for(let i=0;i<normal.length;i++)for(let j=i+1;j<normal.length;j++){
      const a=normal[i],b=normal[j];
      const ix=Math.max(0,Math.min(a.x+a.w,b.x+b.w)-Math.max(a.x,b.x));
      const iy=Math.max(0,Math.min(a.y+a.h,b.y+b.h)-Math.max(a.y,b.y));
      if(ix*iy>Math.min(a.w*a.h,b.w*b.h)*.18)out.push({severity:'warn',message:label+': produtos sobrepostos.'});
    }
    const empty=(pg.templateSlots||[]).length-(pg.elements||[]).filter(e=>e.slotId).length;
    if(empty>0)out.push({severity:'warn',message:label+': '+empty+' bloco(s) do PPTX ainda vazio(s).'});
  }
  return out;
};
})();

(() => {
'use strict';
const A=window.SR11;
const E=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=String(text);return n};
A.E=E;
const root=document.getElementById('sr11-root');
const app=E('div','app');root.replaceChildren(app);
const top=E('div','top');app.appendChild(top);
const brand=E('div','brand','SR STUDIO · ENCARTES');top.appendChild(brand);top.appendChild(E('div','ver',A.VERSION));
function topButton(label,action,primary=false){const b=E('button',primary?'primary':'',label);b.dataset.action=action;top.appendChild(b);return b}
topButton('Planilha','sheet');topButton('PPTX Canva','pptx');topButton('Fontes','fonts');topButton('↶','undo');topButton('↷','redo');topButton('Layout automático','auto');topButton('Validar','validate');top.appendChild(E('span','spacer'));
A.statusNode=E('span','status','LOCAL FIRST');top.appendChild(A.statusNode);
const zoom=E('select');zoom.id='zoom';for(const [v,t] of [['.55','55%'],['.65','65%'],['.75','75%'],['.9','90%'],['1','100%']]){const o=E('option','',t);o.value=v;if(v==String(A.state.zoom))o.selected=true;zoom.appendChild(o)}top.appendChild(zoom);topButton('PDF / Imprimir','print',true);
for(const [id,accept,multiple] of [['sheetFile','.xlsx,.xls,.csv,.txt',false],['pptxFile','.pptx',false],['fontFile','.ttf,.otf,.woff,.woff2',true]]){const f=E('input','file');f.id=id;f.type='file';f.accept=accept;f.multiple=multiple;top.appendChild(f)}
const main=E('div','main');app.appendChild(main);const left=E('aside','side');const center=E('main','center');const right=E('aside','side right');main.append(left,center,right);
left.appendChild(E('div','title','Produtos'));const row=E('div','row');left.appendChild(row);const manual=E('button','btn','+ Produto');manual.dataset.action='manual';const clear=E('button','btn','Limpar');clear.dataset.action='clear';row.append(manual,clear);
const search=E('input','input');search.id='search';search.placeholder='Buscar produto...';left.appendChild(search);const category=E('select','input');category.id='category';left.appendChild(category);A.productsNode=E('div','products');left.appendChild(A.productsNode);
A.zoomNode=E('div','zoom');A.pageNode=E('div','page');A.zoomNode.appendChild(A.pageNode);center.appendChild(A.zoomNode);A.centerNode=center;
right.appendChild(E('div','title','Validação'));A.kpiNode=E('div','kpis');right.appendChild(A.kpiNode);A.inspectorNode=E('div');right.appendChild(A.inspectorNode);A.issueNode=E('div','issues');right.appendChild(A.issueNode);
A.pagesNode=E('div','pages');app.appendChild(A.pagesNode);A.toastNode=E('div','toast');root.appendChild(A.toastNode);
A.toast=msg=>{A.toastNode.textContent=msg;A.toastNode.classList.add('show');clearTimeout(A.toastNode._timer);A.toastNode._timer=setTimeout(()=>A.toastNode.classList.remove('show'),1800)};
A.setStatus=s=>A.statusNode.textContent=s;
A.renderCategories=()=>{const current=A.state.categoryFilter;category.replaceChildren();for(const c of A.categories()){const o=E('option','',c);o.value=c;if(c===current)o.selected=true;category.appendChild(o)}};
A.renderProducts=()=>{const q=A.norm(search.value),cat=A.state.categoryFilter,used=A.usedIds();A.productsNode.replaceChildren();const rows=A.state.products.filter(p=>(!q||A.norm(p.name).includes(q)||String(p.code).includes(q))&&(cat==='TODAS'||(p.category||'SEM CATEGORIA')===cat));if(!rows.length){A.productsNode.appendChild(E('div','help','Nenhum produto neste filtro.'));return}for(const p of rows){const card=E('div','prod'+(used.has(p.id)?' used':''));card.draggable=true;card.dataset.productId=p.id;const info=E('div');info.appendChild(E('div','prod-name',p.name||'SEM NOME'));info.appendChild(E('div','prod-meta',(p.price?'R$ '+p.price:'SEM PREÇO')+' · '+(p.unit||'—')+' · '+(p.bankFound?'BANCO OK':'NÃO LOCALIZADO')+(p.image?' · imagem OK':' · sem imagem')));info.appendChild(E('span','cat',p.category||'SEM CATEGORIA'));const add=E('button','prod-add','+');add.dataset.productId=p.id;card.append(info,add);card.addEventListener('dragstart',ev=>ev.dataTransfer.setData('application/x-sr-product',p.id));A.productsNode.appendChild(card)}};
A.renderPages=()=>{A.pagesNode.replaceChildren();A.state.pages.forEach((p,i)=>{const b=E('button','page-tab'+(i===A.state.pageIndex?' active':''),p.name||('Página '+(i+1)));b.dataset.pageIndex=String(i);A.pagesNode.appendChild(b)});for(const [label,action] of [['+ Página','addPage'],['Duplicar página','dupPage'],['Excluir página','delPage']]){const b=E('button','page-action',label);b.dataset.action=action;A.pagesNode.appendChild(b)}A.pagesNode.appendChild(E('span','page-meta',A.state.pages.length+' página(s)'))};
A.renderKPIs=()=>{A.kpiNode.replaceChildren();const all=A.validate(),errors=all.filter(x=>x.severity==='error').length,warns=all.filter(x=>x.severity==='warn').length;for(const [v,t] of [[A.page().elements.length,'ITENS'],[errors,'ERROS'],[warns,'AVISOS']]){const k=E('div','kpi');k.append(E('b','',v),E('span','',t));A.kpiNode.appendChild(k)}};
})();

(() => {
'use strict';
const A=window.SR11,E=A.E;
const pos=(node,b)=>{node.style.left=b.x+'px';node.style.top=b.y+'px';node.style.width=b.w+'px';node.style.height=b.h+'px'};
const value=(role,p)=>{const price=A.priceParts(p.price);if(role==='NOME')return p.name||'';if(role==='PRECO_RS')return'R$';if(role==='PRECO_REAIS')return price.reais;if(role==='PRECO_CENTAVOS')return price.centavos;if(role==='UNIDADE')return p.unit||'UN';if(role==='LIMITE')return p.limit?('LIMITE DE '+p.limit+' POR CPF'):'';if(role==='PRECO_APP')return p.app?('R$ '+p.app):'';return''};
const textStyle=(node,s={})=>{node.style.fontFamily=s.font||'Segoe UI';node.style.fontSize=Number(s.fontSize||20)+'px';node.style.fontWeight=s.bold?'900':'600';node.style.fontStyle=s.italic?'italic':'normal';node.style.color=s.color||'#172033';node.style.textAlign=s.align||'left';node.style.justifyContent=s.align==='center'?'center':s.align==='right'?'flex-end':'flex-start'};
function template(pg,filled){
  if(pg.backgroundUrl){
    const bg=E('img','tpl-img');bg.src=pg.backgroundUrl;bg.alt='Design original do Canva';bg.style.objectFit='fill';bg.style.pointerEvents='none';bg.style.userSelect='none';bg.style.zIndex='1';pos(bg,{x:0,y:0,w:pg.width,h:pg.height});A.pageNode.appendChild(bg);return;
  }
  for(const t of pg.templateElements||[]){
    if(t.placeholder){const slot=(pg.templateSlots||[]).find(s=>Object.values(s.fields||{}).some(f=>f.sourceId===t.id));if(slot&&filled.has(slot.id))continue}
    if(t.type==='image'){const img=E('img','tpl-img'+(t.placeholder?' tpl-placeholder':''));img.src=t.url||'';img.style.objectFit=t.style?.fit||'contain';pos(img,t);A.pageNode.appendChild(img)}
    else{const d=E('div','tpl-text'+(t.placeholder?' tpl-placeholder':''),t.text||'');textStyle(d,t.style);pos(d,t);A.pageNode.appendChild(d)}
  }
}
function slotProduct(pg,e,p,slot){
  for(const [role,f] of Object.entries(slot.fields||{})){
    if(role==='IMAGEM'){if(!p.image)continue;const img=E('img','slot-field image');img.src=p.image;img.alt=p.name||'Produto';img.style.zIndex='20';pos(img,f);A.pageNode.appendChild(img)}
    else{const d=E('div','slot-field text',value(role,p));d.style.zIndex='20';textStyle(d,f.style);pos(d,f);A.pageNode.appendChild(d)}
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
  const pg=A.page();A.pageNode.replaceChildren();A.pageNode.classList.toggle('grid',A.state.grid&&!pg.backgroundUrl);A.pageNode.style.width=pg.width+'px';A.pageNode.style.height=pg.height+'px';A.zoomNode.style.transform='scale('+A.state.zoom+')';A.zoomNode.style.marginBottom='-'+(pg.height*(1-A.state.zoom))+'px';
  const filled=new Map((pg.elements||[]).filter(e=>e.slotId).map(e=>[e.slotId,e]));template(pg,filled);
  for(const slot of pg.templateSlots||[])if(!filled.has(slot.id)){const empty=E('div','slot-empty','PRODUTO '+slot.index);empty.style.zIndex='30';pos(empty,slot);A.pageNode.appendChild(empty)}
  for(const e of pg.elements||[]){const p=A.state.products.find(x=>x.id===e.productId);if(!p)continue;if(e.slotId){const slot=(pg.templateSlots||[]).find(s=>s.id===e.slotId);if(slot)slotProduct(pg,e,p,slot)}else genericCard(pg,e,p)}
};
A.pageNode.addEventListener('click',ev=>{if(ev.target===A.pageNode){A.state.selected=null;A.emit()}});
A.centerNode.addEventListener('dragover',ev=>ev.preventDefault());
A.centerNode.addEventListener('drop',ev=>{ev.preventDefault();const id=ev.dataTransfer.getData('application/x-sr-product');if(!id)return;const r=A.pageNode.getBoundingClientRect(),scale=Number(A.state.zoom)||1;A.placeProduct(id,{x:(ev.clientX-r.left)/scale,y:(ev.clientY-r.top)/scale})});
})();

(() => {
'use strict';
const A=window.SR11,E=A.E;
A.makeField=(parent,label,value,type='text')=>{
  const box=E('div','prop');box.appendChild(E('label','',label));let input;
  if(type==='select'){
    input=E('select','input');
    for(const item of value.items){const o=E('option','',item.label??item.value);o.value=item.value;if(String(item.value)===String(value.current))o.selected=true;input.appendChild(o)}
  }else{input=E('input','input');input.type=type;input.value=value??''}
  box.appendChild(input);parent.appendChild(box);return input;
};
})();

(() => {
'use strict';
const A=window.SR11,E=A.E;
A.renderInspector=()=>{
  A.inspectorNode.replaceChildren();A.issueNode.replaceChildren();
  const pg=A.page(),e=pg.elements.find(x=>x.id===A.state.selected),p=e&&A.state.products.find(x=>x.id===e.productId);
  if(!p){
    A.inspectorNode.appendChild(E('div','title','Editor'));
    A.inspectorNode.appendChild(E('div','help','Clique ou arraste um produto para o encarte. Se houver um PPTX do Canva, o primeiro bloco vazio será preenchido automaticamente.'));
    const fonts=E('div');for(const f of A.state.fonts||[])fonts.appendChild(E('span','font-pill',f.family));
    if(fonts.childNodes.length){A.inspectorNode.appendChild(E('div','title','Fontes importadas'));A.inspectorNode.appendChild(fonts)}return;
  }
  A.inspectorNode.appendChild(E('div','title','Produto selecionado'));
  const F=A.makeField;
  const name=F(A.inspectorNode,'Nome comercial',p.name),price=F(A.inspectorNode,'Preço',p.price),app=F(A.inspectorNode,'Preço APP',p.app);
  const unit=F(A.inspectorNode,'Unidade',{current:p.unit||'UN',items:['UN','KG','CX','PCT','BDJ','DZ','LT'].map(x=>({value:x,label:x}))},'select');
  const limit=F(A.inspectorNode,'Limite por CPF',p.limit),category=F(A.inspectorNode,'Categoria',p.category||'SEM CATEGORIA');
  const highlight=F(A.inspectorNode,'Destaque',{current:String(e.highlight||0),items:[{value:'0',label:'Normal'},{value:'1',label:'Destaque'},{value:'2',label:'Destaque principal'}]},'select');
  const fontItems=[{value:'Segoe UI',label:'Segoe UI'},...(A.state.fonts||[]).map(f=>({value:f.family,label:f.family}))];
  const font=F(A.inspectorNode,'Fonte',{current:e.fontFamily||'Segoe UI',items:fontItems},'select');
  const row=E('div','row'),dup=E('button','btn','Duplicar produto'),del=E('button','btn danger','Excluir');dup.dataset.action='dupSelected';del.dataset.action='delSelected';row.append(dup,del);A.inspectorNode.appendChild(row);
  A.inspectorNode.appendChild(E('div','help','Preço profissional: R$, REAIS e ,CENTAVOS ficam separados. No PPTX, cada parte preenche a caixa correspondente do Canva.'));
  const save=()=>{A.snapshot();p.name=name.value.trim();p.price=A.money(price.value);p.app=A.money(app.value);p.unit=unit.value;p.limit=limit.value.trim();p.category=category.value.trim()||'SEM CATEGORIA';e.highlight=Number(highlight.value)||0;e.fontFamily=font.value||'Segoe UI';A.commit()};
  for(const input of [name,price,app,unit,limit,category,highlight,font])input.addEventListener('change',save);
  const pageIssues=A.validate().filter(x=>x.message.startsWith(pg.name+':')).slice(0,6);
  if(!pageIssues.length)A.issueNode.appendChild(E('div','issue ok','Página sem pendências críticas.'));
  else for(const issue of pageIssues)A.issueNode.appendChild(E('div','issue '+issue.severity,issue.message));
};
A.renderAll=()=>{A.renderCategories();A.renderProducts();A.renderPages();A.renderCanvas();A.renderKPIs();A.renderInspector()};
A.onChange(A.renderAll);
})();

(() => {
'use strict';
const A=window.SR11,E=A.E;
const sheet=document.getElementById('sheetFile'),pptx=document.getElementById('pptxFile'),fonts=document.getElementById('fontFile'),search=document.getElementById('search'),category=document.getElementById('category'),zoom=document.getElementById('zoom');
const printHost=E('div','print-host');document.body.appendChild(printHost);
function manualProduct(){A.snapshot();A.state.products.push({id:A.uid('p'),name:'NOVO PRODUTO',code:'',price:'0,00',app:'',limit:'',unit:'UN',image:'',category:'SEM CATEGORIA',bankFound:false,matchMethod:'MANUAL'});A.commit()}
function validationModal(){const list=A.validate(),bg=E('div','modal-bg'),box=E('div','modal');box.appendChild(E('h2','',list.length?'Verificação do Encarte':'Encarte validado'));const issues=E('div','issues');if(!list.length)issues.appendChild(E('div','issue ok','Nenhum erro ou aviso encontrado.'));else for(const item of list)issues.appendChild(E('div','issue '+item.severity,item.message));box.appendChild(issues);const actions=E('div','modal-actions'),close=E('button','btn','Fechar');close.addEventListener('click',()=>bg.remove());actions.appendChild(close);box.appendChild(actions);bg.appendChild(box);document.body.appendChild(bg)}
function preparePrint(){const old=A.state.pageIndex;printHost.replaceChildren();for(let i=0;i<A.state.pages.length;i++){A.state.pageIndex=i;A.renderCanvas();const copy=A.pageNode.cloneNode(true);copy.classList.remove('grid');copy.querySelectorAll('.selected,.slot-outline,.slot-empty').forEach(n=>n.remove());printHost.appendChild(copy)}A.state.pageIndex=old;A.renderAll();setTimeout(()=>window.print(),100)}
async function importPptx(file){
  if(!file)return;
  A.setStatus('Analisando PPTX do Canva e renderizando design...');
  const response=await fetch('/api/encartes/import-pptx?name='+encodeURIComponent(file.name),{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:await file.arrayBuffer()});
  const data=await response.json();if(!response.ok||!data.ok)throw Error(data.error||'Falha ao analisar PPTX');
  A.snapshot();A.state.pages=(data.pages||[]).map((p,i)=>({...p,id:A.uid('pg'),name:p.name||('Página '+(i+1)),elements:[]}));if(!A.state.pages.length)A.state.pages=[A.newPage('Página 1')];A.state.pageIndex=0;A.state.selected=null;A.commit();
  const full=data.visualMode==='powerpoint-render';
  if(full){A.setStatus('PPTX: design completo · '+(data.autoImageSlotCount||0)+' área(s) de imagem · '+(data.slotCount||0)+' bloco(s)');A.toast((data.pageCount||0)+' página(s) do Canva importada(s) com design completo')}
  else{const warning=data.visualWarning||'Design completo não pôde ser renderizado.';A.setStatus('PPTX em modo estrutural · '+(data.slotCount||0)+' bloco(s)');A.toast(warning);setTimeout(()=>alert('PPTX importado em modo estrutural.\n\n'+warning+'\n\nOs campos foram reconhecidos, mas o design visual completo não foi aplicado.'),120)}
}
document.addEventListener('click',async ev=>{
  const add=ev.target.closest('[data-product-id]');if(add&&add.classList.contains('prod-add')){A.placeProduct(add.dataset.productId);return}
  const tab=ev.target.closest('[data-page-index]');if(tab){A.state.pageIndex=Number(tab.dataset.pageIndex)||0;A.state.selected=null;A.emit();return}
  const action=ev.target.closest('[data-action]')?.dataset.action;if(!action)return;
  try{
    if(action==='sheet')sheet.click();else if(action==='pptx')pptx.click();else if(action==='fonts')fonts.click();else if(action==='undo')A.undo();else if(action==='redo')A.redo();else if(action==='auto'){const mode=A.autoLayout();A.toast(mode==='template'?'Template preenchido automaticamente':'Produtos organizados por categoria')}else if(action==='validate')validationModal();else if(action==='print')preparePrint();else if(action==='manual')manualProduct();else if(action==='clear'){if(confirm('Limpar produtos e páginas do projeto?')){A.snapshot();A.state.products=[];A.state.pages=[A.newPage('Página 1')];A.state.pageIndex=0;A.state.selected=null;A.commit()}}else if(action==='addPage')A.addPage();else if(action==='dupPage')A.duplicatePage();else if(action==='delPage'){if(!A.deletePage())A.toast('O projeto precisa ter pelo menos uma página.')}else if(action==='dupSelected'){if(!A.duplicateSelected())A.toast('Não há outro bloco livre para duplicar.')}else if(action==='delSelected')A.deleteSelected();
  }catch(e){console.error(e);A.toast(e.message||'Falha na operação')}
});
sheet.addEventListener('change',async()=>{const file=sheet.files[0];if(!file)return;try{A.setStatus('Importando planilha e consultando Banco...');const r=await A.importSheet(file);A.setStatus('Banco: '+r.found+' encontrado(s) · '+(r.total-r.found)+' não localizado(s)');A.toast(r.total+' produto(s) importados')}catch(e){A.toast(e.message);A.setStatus('Falha na planilha')}finally{sheet.value=''}});
pptx.addEventListener('change',async()=>{try{await importPptx(pptx.files[0])}catch(e){A.toast(e.message);A.setStatus('Falha no PPTX')}finally{pptx.value=''}});
fonts.addEventListener('change',async()=>{try{const total=await A.importFonts(fonts.files);A.toast(total+' fonte(s) importada(s) manualmente')}catch(e){A.toast(e.message)}finally{fonts.value=''}});
search.addEventListener('input',A.renderProducts);category.addEventListener('change',()=>{A.state.categoryFilter=category.value;A.renderProducts()});zoom.addEventListener('change',()=>{A.state.zoom=Number(zoom.value)||.75;A.save();A.renderCanvas()});
document.addEventListener('keydown',ev=>{if((ev.ctrlKey||ev.metaKey)&&ev.key.toLowerCase()==='z'){ev.preventDefault();ev.shiftKey?A.redo():A.undo()}else if((ev.ctrlKey||ev.metaKey)&&ev.key.toLowerCase()==='y'){ev.preventDefault();A.redo()}else if(ev.key==='Delete'&&!['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName))A.deleteSelected()});
A.loadFonts().then(()=>A.emit());A.renderAll();
})();
