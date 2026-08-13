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
