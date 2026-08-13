(() => {
'use strict';
const A=window.SR11;
const sheet=document.getElementById('sheetFile'),pptx=document.getElementById('pptxFile'),fonts=document.getElementById('fontFile'),search=document.getElementById('search'),category=document.getElementById('category'),zoom=document.getElementById('zoom');
sheet.addEventListener('change',async()=>{const file=sheet.files[0];if(!file)return;try{A.setStatus('Importando planilha e consultando Banco...');const r=await A.importSheet(file);A.setStatus('Banco: '+r.found+' encontrado(s) · '+(r.total-r.found)+' não localizado(s)');A.toast(r.total+' produto(s) importados')}catch(e){A.toast(e.message);A.setStatus('Falha na planilha')}finally{sheet.value=''}});
pptx.addEventListener('change',async()=>{try{await A.importPptxFile(pptx.files[0])}catch(e){A.toast(e.message);A.setStatus('Falha no PPTX')}finally{pptx.value=''}});
fonts.addEventListener('change',async()=>{try{const total=await A.importFonts(fonts.files);A.toast(total+' fonte(s) importada(s) manualmente')}catch(e){A.toast(e.message)}finally{fonts.value=''}});
search.addEventListener('input',A.renderProducts);
category.addEventListener('change',()=>{A.state.categoryFilter=category.value;A.renderProducts()});
zoom.addEventListener('change',()=>{A.state.zoom=Number(zoom.value)||.75;A.save();A.renderCanvas()});
document.addEventListener('keydown',ev=>{if((ev.ctrlKey||ev.metaKey)&&ev.key.toLowerCase()==='z'){ev.preventDefault();ev.shiftKey?A.redo():A.undo()}else if((ev.ctrlKey||ev.metaKey)&&ev.key.toLowerCase()==='y'){ev.preventDefault();A.redo()}else if(ev.key==='Delete'&&!['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName))A.deleteSelected()});
A.loadFonts().then(()=>A.emit());
A.renderAll();
})();
