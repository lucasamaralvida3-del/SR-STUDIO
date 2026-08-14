(() => {
'use strict';
const A=window.SR11;if(!A||A.__SR5_VISUAL__)return;A.__SR5_VISUAL__=true;
const E=A.E||((tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=String(text);return n});
const app=document.querySelector('.app'),top=document.querySelector('.top');if(!app||!top)return;
A.VERSION='5.0.0 • Beta 2';const ver=document.querySelector('.ver');if(ver)ver.textContent=A.VERSION;

function clickAction(action){const b=top.querySelector('button[data-action="'+action+'"]');if(b)b.click()}
function focusProducts(){const s=document.getElementById('search');if(s){s.focus();s.scrollIntoView({block:'center'})}}
function railButton(icon,label,fn,active=false){const b=E('button','sr5-rail-btn'+(active?' active':''));const i=E('b','',icon),t=E('span','',label);b.append(i,t);b.addEventListener('click',fn);return b}
const rail=E('nav','sr5-rail');const logo=E('img','sr5-rail-logo');logo.src='assets/SR_logo.png';logo.alt='SR';rail.appendChild(logo);
rail.append(
 railButton('▣','Encarte',()=>document.querySelector('.center')?.scrollIntoView({block:'center'}),true),
 railButton('◇','Produtos',focusProducts),
 railButton('▧','Modelos',()=>clickAction('pptx')),
 railButton('▦','Planilha',()=>clickAction('sheet')),
 railButton('✓','Validar',()=>clickAction('validate')),
 railButton('⇧','Exportar',()=>clickAction('print'))
);
rail.appendChild(E('span','sr5-rail-spacer'));
rail.appendChild(E('div','sr5-rail-version','SR Studio\n5.0'));
app.prepend(rail);

const brand=document.querySelector('.brand');if(brand){brand.innerHTML='SR Studio <strong>Encartes Studio</strong>'}
const projectHead=E('div','sr5-project-head');const kicker=E('div','kicker','Projeto atual'),name=E('div','name',A.state?.projectName||'Novo Encarte'),saved=E('span','saved','● Salvo');projectHead.append(kicker,name,saved);if(brand?.nextSibling)top.insertBefore(projectHead,brand.nextSibling);else top.prepend(projectHead);
function updateProject(){name.textContent=A.state?.projectName||'Novo Encarte'}A.onChange?.(updateProject);

for(const [action,label] of [['sheet','▦  Importar Planilha'],['pptx','▧  Importar PPTX'],['auto','✦  Layout automático'],['validate','✓  Validar'],['print','⇧  Exportar']]){const b=top.querySelector('button[data-action="'+action+'"]');if(b)b.textContent=label}
const fonts=top.querySelector('button[data-action="fonts"]');if(fonts)fonts.textContent='Aa  Fontes';
const undo=top.querySelector('button[data-action="undo"]');if(undo)undo.textContent='↶';const redo=top.querySelector('button[data-action="redo"]');if(redo)redo.textContent='↷';

const float=E('div','sr5-float-tools');
for(const [label,fn,title] of [
 ['↶',()=>A.undo?.(),'Desfazer'],['↷',()=>A.redo?.(),'Refazer'],['▦',()=>clickAction('sheet'),'Importar planilha'],['▧',()=>clickAction('pptx'),'Importar PPTX'],['✓',()=>clickAction('validate'),'Validar encarte']
]){const b=E('button','',label);b.title=title;b.addEventListener('click',fn);float.appendChild(b)}
document.body.appendChild(float);

const left=document.querySelector('.side:not(.right)');if(left){const title=left.querySelector('.title');if(title)title.textContent='PRODUTOS';const search=left.querySelector('#search');if(search)search.placeholder='Buscar produtos...'}
const right=document.querySelector('.side.right');if(right){const title=right.querySelector('.title');if(title)title.textContent='PROPRIEDADES E VALIDAÇÃO'}

const status=A.statusNode;if(status){const observer=new MutationObserver(()=>{const text=(status.textContent||'').toLowerCase();saved.textContent=text.includes('salv')?'● Salvo':'● '+(status.textContent||'Pronto');saved.style.color=text.includes('erro')?'#c43b3b':text.includes('salv')?'#159455':'#6b7890'});observer.observe(status,{childList:true,subtree:true,characterData:true})}

console.info('[SR Studio] Nova interface visual Beta 2 ativa.');
})();
