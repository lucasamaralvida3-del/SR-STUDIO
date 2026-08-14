from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageFilter, ImageFile

ROOT=Path(__file__).resolve().parents[1]
ASSETS=ROOT/'src'/'sr_studio'/'assets'
LOGO=ASSETS/'SR_logo.png'
ICON=ASSETS/'SR_Studio.ico'


def rebuild():
    # A logo antiga da linha 4.x abre no Tkinter/Windows, mas contém um stream
    # PNG parcialmente truncado. Carregamos de forma tolerante e regravamos um
    # PNG limpo antes de gerar os derivados HiDPI.
    ImageFile.LOAD_TRUNCATED_IMAGES=True
    with Image.open(LOGO) as src:
        src.load()
        base=src.convert('RGBA').copy()

    clean=base.resize((512,512),Image.Resampling.LANCZOS)
    clean=clean.filter(ImageFilter.UnsharpMask(radius=1.0,percent=105,threshold=2))
    hd=clean.resize((2048,2048),Image.Resampling.LANCZOS)
    hd=hd.filter(ImageFilter.UnsharpMask(radius=1.4,percent=115,threshold=2))
    hd.save(LOGO,'PNG',optimize=True)

    # ICO multi-resolução para janela/atalho do Windows.
    hd.save(ICON,format='ICO',sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(96,96),(128,128),(256,256)])
    print('BRAND_HD_OK',LOGO.stat().st_size,ICON.stat().st_size)


if __name__=='__main__':
    rebuild()
