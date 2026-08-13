from pathlib import Path
p=Path(__import__('sys').argv[1])/'files'/'Encartes4_beta6.js'; s=p.read_text(encoding='utf-8')
s=s.replace("if(typeof e==='number' && !Number.isInteger(e)) return 'KG';\n    return 'UN';","if(typeof e==='number') return Number.isInteger(e)?'UN':'KG';\n    return '';",1)
s=s.replace("const code=pick(row,['CODIGO','CÓDIGO','COD BARRAS','CODIGO DE BARRAS','EAN']);\n    if(!name && !price) return null;\n    return {id:uid('p'), name:String(name||'PRODUTO SEM NOME').trim(), price:fmtMoney(price), app:fmtMoney(app), unit:detectUnit(row), limit:String(limit||'').trim(), image:String(image||'').trim(), code:String(code||'').trim()};",
"const code=pick(row,['EAN','CODIGO','CÓDIGO','COD','COD.','CODIGO CISS','CÓDIGO CISS','COD CISS','COD BARRAS','CODIGO DE BARRAS','CÓDIGO DE BARRAS']);\n    if(!name && !price && !code) return null;\n    return {id:uid('p'),name:String(name||'').trim(),price:fmtMoney(price),app:fmtMoney(app),unit:detectUnit(row),limit:String(limit||'').trim(),image:String(image||'').trim(),code:String(code||'').trim(),bankFound:false,matchMethod:''};",1)
marker='  function parseCSV(text){\n'
insert=r'''  function worksheetRows(ws){
    const matrix=XLSX.utils.sheet_to_json(ws,{header:1,defval:'',raw:false}); if(!matrix.length)return [];
    const signals=['EAN','CODIGO','CÓDIGO','PRODUTO','PRODUTOS','DESCRICAO','DESCRIÇÃO','PROMOCAO','PROMOÇÃO','VENDA','ENTRADA','LIMITE']; let best=0,score=-1;
    for(let i=0;i<Math.min(matrix.length,30);i++){const cells=(matrix[i]||[]).map(norm);let n=0;for(const c of cells)if(signals.some(x=>c===norm(x)))n++;if(n>score){score=n;best=i;}}
    const head=(matrix[best]||[]).map((x,i)=>String(x||`COLUNA_${i+1}`).trim());
    return matrix.slice(best+1).map(v=>{const o={};head.forEach((h,i)=>o[h]=v[i]??'');return o;}).filter(o=>Object.values(o).some(v=>String(v??'').trim()));
  }
  async function resolveFromProductBank(products){
    try{
      const res=await fetch('/api/encartes/resolve-products',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({items:products.map(p=>({code:p.code,name:p.name}))})});
      const data=await res.json();if(!res.ok||!data.ok)throw new Error(data.error||'Falha no Banco de Produtos');let found=0,missing=0;
      products.forEach((p,i)=>{const r=(data.results||[])[i]||{};if(r.found){found++;p.bankFound=true;p.matchMethod=r.match_method||'';p.identityKey=r.identity_key||'';p.name=r.canonical_name||p.name||`PRODUTO ${p.code}`;p.unit=p.unit||r.unidade||'UN';p.image=p.image||r.image||'';p.code=r.codigo||r.codigo_ciss||p.code;p.category=r.categoria||'';}else{missing++;p.name=p.name||`CÓDIGO ${p.code||'NÃO IDENTIFICADO'}`;p.unit=p.unit||'UN';}});return {products,found,missing};
    }catch(e){console.error(e);products.forEach(p=>{p.name=p.name||`CÓDIGO ${p.code||'NÃO IDENTIFICADO'}`;p.unit=p.unit||'UN';});return {products,found:0,missing:products.length,error:e};}
  }
'''
if marker not in s: raise SystemExit('parseCSV não encontrado')
s=s.replace(marker,insert+marker,1)
old="else if(window.XLSX){ const buf=await file.arrayBuffer(); const wb=XLSX.read(buf,{type:'array'}); rows=XLSX.utils.sheet_to_json(wb.Sheets[wb.SheetNames[0]],{defval:''}); }\n      else { notify('XLSX não disponível nesta tela; exporte como CSV'); return; }\n      const ps=rows.map(rowToProduct).filter(Boolean); if(!ps.length) return notify('Nenhum produto reconhecido');\n      snapshot(); state.products.push(...ps); renderAll(); notify(`${ps.length} produtos importados`);"
new="else if(window.XLSX){ const buf=await file.arrayBuffer(); const wb=XLSX.read(buf,{type:'array'}); rows=worksheetRows(wb.Sheets[wb.SheetNames[0]]); }\n      else { notify('XLSX não disponível nesta tela; exporte como CSV'); return; }\n      const ps=rows.map(rowToProduct).filter(Boolean); if(!ps.length) return notify('Nenhuma linha de produto encontrada na planilha');\n      statusEl.textContent=`Consultando Banco de Produtos...`; const resolved=await resolveFromProductBank(ps);\n      snapshot(); state.products.push(...resolved.products); renderAll(); statusEl.textContent=`Banco: ${resolved.found} encontrado(s) · ${resolved.missing} não encontrado(s)`; notify(`${resolved.products.length} produtos importados · ${resolved.found} encontrados no banco`);"
if old not in s: raise SystemExit('importador base não encontrado')
s=s.replace(old,new,1)
s=s.replace("${p.price?'R$ '+esc(p.price):'SEM PREÇO'} · ${esc(p.unit||'UN')}${p.image?' · imagem OK':' · sem imagem'}","${p.price?'R$ '+esc(p.price):'SEM PREÇO'} · ${esc(p.unit||'UN')} · ${p.bankFound?'BANCO OK':'NÃO LOCALIZADO'}${p.image?' · imagem OK':' · sem imagem'}",1)
p.write_text(s,encoding='utf-8')
