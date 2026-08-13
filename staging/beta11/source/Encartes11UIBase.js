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
