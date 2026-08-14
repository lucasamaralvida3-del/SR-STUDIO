from pathlib import Path
import json
R=Path('work/files')
js=(R/'Encartes10_beta16.js').read_text(encoding='utf-8')
html=(R/'Encartes3_index.html').read_text(encoding='utf-8')
v=json.loads((R/'version.json').read_text(encoding='utf-8'))
checks={
'version':v.get('distribution_version')=='4.0.15-hybrid.beta16',
'html':'Encartes10_beta16.js' in html,
'multiselect':'proSelection' in js and "mode==='toggle'" in js,
'handles':"['nw','n','ne','e','se','s','sw','w']" in js,
'rotate':'sr16-rotate' in js and 'startRotate' in js,
'inline_text':'contentEditable' in js and 'commitRoleText' in js,
'crop':'cropKey' in js and 'startCropDrag' in js,
'group':'groupSelection' in js and 'ungroupSelection' in js,
'layers':'layerSelection' in js and 'Bloquear / desbloquear' in js,
'align':'alignSelection' in js and 'distributeSelection' in js,
'context':'contextmenu' in js and 'sr16-menu' in js,
'floating':'sr16-float' in js,
'marquee':'sr16-marquee' in js,
'shortcuts':"key.toLowerCase()==='g'" in js and "key===']'||key==='['" in js,
'beta15_preserved':(R/'Encartes9_beta15.js').exists(),
'beta14_preserved':(R/'Encartes8_beta14.js').exists(),
}
for k,val in checks.items():print(k,'OK' if val else 'FAIL')
assert all(checks.values()),checks
print('Beta 16 validada')
