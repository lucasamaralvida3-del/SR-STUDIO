from pathlib import Path
import zipfile
from PIL import Image, ImageFilter

ROOT=Path(__file__).resolve().parents[1]
TARGET=ROOT/'src'/'sr_studio'/'assets'


def restore(bundle: Path):
    bundle=Path(bundle)
    with zipfile.ZipFile(bundle) as z:
        data=z.read('files/assets/SR_logo.png')
    tmp=ROOT/'build'/'_stable_logo_source.png'
    tmp.write_bytes(data)
    with Image.open(tmp) as src:
        src.load()
        base=src.convert('RGBA')
        print('STABLE_LOGO_SOURCE',base.size)
        hd=base.resize((2048,2048),Image.Resampling.LANCZOS)
        hd=hd.filter(ImageFilter.UnsharpMask(radius=1.2,percent=105,threshold=2))
        hd.save(TARGET/'SR_logo.png','PNG',optimize=True)
        hd.save(TARGET/'SR_Studio.ico',format='ICO',sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(96,96),(128,128),(256,256)])
    tmp.unlink(missing_ok=True)
    with Image.open(TARGET/'SR_logo.png') as check:
        check.load()
        assert check.size==(2048,2048)
    print('BRAND_RESTORED_OK',(TARGET/'SR_logo.png').stat().st_size,(TARGET/'SR_Studio.ico').stat().st_size)


if __name__=='__main__':
    import sys
    if len(sys.argv)!=2: raise SystemExit('Uso: restore_brand_from_stable.py <stable4.zip>')
    restore(Path(sys.argv[1]))
