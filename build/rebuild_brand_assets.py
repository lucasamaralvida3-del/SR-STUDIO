from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageFilter

ROOT=Path(__file__).resolve().parents[1]
ASSETS=ROOT/'src'/'sr_studio'/'assets'
LOGO=ASSETS/'SR_logo.png'
ICON=ASSETS/'SR_Studio.ico'


def rebuild():
    with Image.open(LOGO) as src:
        base=src.convert('RGBA')
    # Mantém exatamente a arte existente; apenas cria uma matriz muito maior
    # com reamostragem de alta qualidade e nitidez leve para HiDPI.
    hd=base.resize((2048,2048),Image.Resampling.LANCZOS)
    hd=hd.filter(ImageFilter.UnsharpMask(radius=1.6,percent=115,threshold=2))
    hd.save(LOGO,'PNG',optimize=True)
    # ICO multi-resolução para janela/atalho do Windows.
    rgb=hd.convert('RGBA')
    rgb.save(ICON,format='ICO',sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(96,96),(128,128),(256,256)])
    print('BRAND_HD_OK',LOGO.stat().st_size,ICON.stat().st_size)


if __name__=='__main__':
    rebuild()
