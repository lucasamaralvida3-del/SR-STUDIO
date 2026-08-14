from pathlib import Path
import json

beta_path = Path('beta/manifest.json')
launcher_path = Path('manifests/launcher.json')

beta = json.loads(beta_path.read_text(encoding='utf-8-sig'))
launcher = json.loads(launcher_path.read_text(encoding='utf-8-sig'))
changed = False

if beta.get('format') == 'SRSTUDIO_HYBRID_BUNDLE_1':
    bundle = beta.get('bundle')
    if not isinstance(bundle, dict):
        bundle = {}
        beta['bundle'] = bundle
        changed = True

    url = bundle.get('url') or beta.get('bundle_url') or beta.get('url')
    sha = bundle.get('sha256') or beta.get('sha256')
    size = bundle.get('size') or beta.get('size')
    prefix = bundle.get('member_prefix') or beta.get('member_prefix') or 'files/'

    required = {'url': url, 'sha256': sha, 'size': size, 'member_prefix': prefix}
    for key, value in required.items():
        if value is not None and bundle.get(key) != value:
            bundle[key] = value
            changed = True

    if not url or not sha:
        raise SystemExit('Manifesto Beta bundle não pode ser reparado: URL/SHA ausente')

    current_launcher = launcher.get('version')
    if current_launcher:
        if beta.get('min_launcher') != current_launcher:
            beta['min_launcher'] = current_launcher
            changed = True
        if beta.get('min_launcher_version') != current_launcher:
            beta['min_launcher_version'] = current_launcher
            changed = True

if changed:
    beta_path.write_text(json.dumps(beta, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('BETA_MANIFEST_AUTO_REPAIRED')
else:
    print('BETA_MANIFEST_OK')
