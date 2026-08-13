from pathlib import Path
import json,sys
z=json.loads(Path(sys.argv[1]).read_text()); repo=sys.argv[2]
m={'format':'SRSTUDIO_HYBRID_BUNDLE_1','product':'SR Studio Desktop Core','channel':'beta','version':'4.0.9-hybrid.beta10','created_at':'2026-08-13T17:05:00-03:00','min_launcher_version':'4.0.0-hybrid.pro1.1','bundle':{'url':f'https://github.com/{repo}/releases/download/v4.0.9-hybrid.beta10/SR_STUDIO_4.0.9_BETA10_BANCO_AUTOMATICO.zip','sha256':z['sha256'],'size':z['size'],'member_prefix':'files/'},'repair':{'mode':'local_hash_catalog','full_check_every_days':7},'delete':[],'notes':'Beta 10: Encartes consulta automaticamente o Banco de Produtos durante a importação de planilhas.'}
Path('beta/manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
