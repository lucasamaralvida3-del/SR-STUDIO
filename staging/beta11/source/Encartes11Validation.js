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
