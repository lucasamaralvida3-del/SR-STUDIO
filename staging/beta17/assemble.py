from pathlib import Path
import json, re

R=Path('work/files')

# Mesma base funcional da Stable 2; muda apenas identidade do canal de teste.
vpath=R/'version.json'
v=json.loads(vpath.read_text(encoding='utf-8'))
v.update(
    distribution_version='4.0.16-hybrid.beta17',
    product_version='4.0.16',
    channel='beta',
    release_label='Beta 17',
    updated_at='2026-08-14T11:08:00-03:00',
)
vpath.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

(R/'VERSAO.txt').write_text(
    'SR Studio 4.0.16 • Beta 17\n'
    'Sincronizada com a Stable 2: mesmo código e mesmas funções, incluindo corretor ortográfico local e Encartes Studio Canva-like.\n',
    encoding='utf-8'
)

# Identidade visual do Encartes no canal Beta.
js=R/'Encartes10_beta16.js'
if js.exists():
    text=js.read_text(encoding='utf-8')
    text=re.sub(r"A\.VERSION='4\.0\.16\s*•\s*Stable 2';", "A.VERSION='4.0.16 • Beta 17';", text, count=1)
    text=re.sub(r"A\.VERSION='4\.0\.15\s*•\s*Beta 16';", "A.VERSION='4.0.16 • Beta 17';", text, count=1)
    js.write_text(text,encoding='utf-8')

engine=R/'Encartes3Engine.py'
if engine.exists():
    text=engine.read_text(encoding='utf-8')
    text=text.replace("'version':'4.0.15-beta16'", "'version':'4.0.16-beta17'")
    text=text.replace('BETA 16 • EDIÇÃO VISUAL ESTILO CANVA','BETA 17 • SINCRONIZADA COM STABLE 2')
    text=text.replace('STABLE 2 • EDIÇÃO VISUAL ESTILO CANVA','BETA 17 • SINCRONIZADA COM STABLE 2')
    engine.write_text(text,encoding='utf-8')

print('Beta 17 sincronizada com Stable 2')
