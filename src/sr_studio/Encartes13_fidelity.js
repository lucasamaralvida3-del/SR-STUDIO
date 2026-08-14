(() => {
'use strict';
const A=window.SR11;if(!A||A.__SR5_FIDELITY__)return;A.__SR5_FIDELITY__=true;
A.VERSION='5.0.0 • Beta 4';
const ver=document.querySelector('.ver');if(ver)ver.textContent=A.VERSION;

const ICONS={
 encarte:'<svg viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18M9 9v11"/></svg>',
 products:'<svg viewBox="0 0 24 24"><path d="m12 3 9 5-9 5-9-5 9-5Z"/><path d="M3 8v9l9 5 9-5V8M12 13v9"/></svg>',
 models:'<svg viewBox="0 0 24 24"><path d="m12 4 9 5-9 5-9-5 9-5Z"/><path d="m3 13 9 5 9-5M3 17l9 5 9-5"/></svg>',
 sheet:'<svg viewBox="0 0 24 24"><rect x="4" y="3" width="16" height="18" rx="2"/><path d="M4 8h16M4 13h16M4 17h16M10 8v13M15 8v13"/></svg>',
 check:'<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/></svg>',
 export:'<svg viewBox="0 0 24 24"><path d="M4 10v10h16V10"/><path d="M12 16V3M7 8l5-5 5 5"/></svg>',
 auto:'<svg viewBox="0 0 24 24"><path d="M5 20 18 7M15 4l5 5M5 4v4M3 6h4M19 15v5M16.5 17.5h5"/></svg>',
 undo:'<svg viewBox="0 0 24 24"><path d="M9 7H4v-5"/><path d="M4 7c3-4 10-5 14-1 4 4 3 11-1 14"/></svg>',
 redo:'<svg viewBox="0 0 24 24"><path d="M15 7h5v-5"/><path d="M20 7c-3-4-10-5-14-1-4 4-3 11 1 14"/></svg>',
 fonts:'<svg viewBox="0 0 24 24"><path d="M4 20 10 4h4l6 16M7 14h10"/></svg>'
};
function svg(name){return ICONS[name]||ICONS.encarte}
function setButtonIcon(button,name,label){if(!button)return;button.innerHTML=svg(name)+(label?'<span>'+label+'</span>':'');}

const logo=document.querySelector('.sr5-rail-logo');if(logo){logo.src='assets/SR_logo.png?v=5.0.0-beta4';logo.decoding='async';}
const railMap={Encarte:'encarte',Produtos:'products',Modelos:'models',Planilha:'sheet',Validar:'check',Exportar:'export'};
document.querySelectorAll('.sr5-rail-btn').forEach(btn=>{
 const label=btn.querySelector('span')?.textContent?.trim();const icon=railMap[label];const b=btn.querySelector('b');if(icon&&b)b.innerHTML=svg(icon);
});

for(const [action,name,label] of [
 ['sheet','sheet','Importar Planilha'],['pptx','models','Importar PPTX'],['auto','auto','Layout automático'],
 ['validate','check','Validar'],['print','export','Exportar'],['fonts','fonts','Fontes'],['undo','undo',''],['redo','redo','']
]){setButtonIcon(document.querySelector('.top button[data-action="'+action+'"]'),name,label)}

const floatButtons=[...document.querySelectorAll('.sr5-float-tools button')];
const floatIcons=['undo','redo','sheet','models','check'];
floatButtons.forEach((b,i)=>{if(floatIcons[i])b.innerHTML=svg(floatIcons[i])});

document.documentElement.dataset.srFidelity='beta4';
console.info('[SR Studio] Fidelidade Visual Beta 4 ativa.');
})();
