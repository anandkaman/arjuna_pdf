import subprocess
from pathlib import Path
import uharfbuzz as hb
from ocrmypdf.models.ocr_element import OcrElement, OcrClass, BoundingBox
from ocrmypdf.fpdf_renderer.renderer import Fpdf2PdfRenderer
from ocrmypdf.font import MultiFontManager
import ocrmypdf.fpdf_renderer  # applies patches
from exp import LINES, extract
DPI=300; fs_px=60
lines=[]; y=200
for k,(fp,text) in LINES.items():
    blob=hb.Blob.from_file_path(fp); face=hb.Face(blob); font=hb.Font(face)
    x=100; words=[]
    for w in text.split(" "):
        b=hb.Buffer(); b.add_str(w); b.guess_segment_properties(); hb.shape(font,b,{})
        wd=sum(p.x_advance for p in b.glyph_positions)/face.upem*fs_px
        words.append(OcrElement(ocr_class=OcrClass.WORD,text=w,bbox=BoundingBox(x,y,x+wd,y+fs_px)))
        x+=wd+fs_px*0.3
    lang={"hi":"hin","kn":"kan"}[k]
    lines.append(OcrElement(ocr_class=OcrClass.LINE,bbox=BoundingBox(100,y,x,y+fs_px),children=words,language=lang))
    y+=200
page=OcrElement(ocr_class=OcrClass.PAGE,bbox=BoundingBox(0,0,2480,1000),children=lines)
mfm=MultiFontManager()
Fpdf2PdfRenderer(page,DPI,mfm).render(Path("exp_ocrmypdf.pdf"))
gold=[t for _,t in LINES.values()]
for eng,txt in extract("exp_ocrmypdf.pdf").items():
    norm=" ".join(txt.split()); ok=[g in norm for g in gold]
    print(f"  {eng:12s} hi={'OK ' if ok[0] else 'BAD'} kn={'OK ' if ok[1] else 'BAD'} | {norm[:150]!r}")
print(subprocess.run(["pdffonts","exp_ocrmypdf.pdf"],capture_output=True,text=True).stdout)
