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
