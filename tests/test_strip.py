"""M4: strip old invisible OCR layers. On every private fixture: old text gone, visible text kept, page renders
pixel-identical before/after, image streams byte-identical.  python tests/test_strip.py [dirs...]"""
import sys, io, glob, hashlib
from pathlib import Path
import numpy as np, pypdfium2 as pdfium
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT)); sys.path.append(str(ROOT / ".deps"))
import pikepdf
from arjuna_pdf.pdftext import strip_invisible_text

def render(data, dpi=72):
    a = pdfium.PdfDocument(data)[0].render(scale=dpi / 72).to_numpy(); return a[:, :, :3].astype(np.int16)
def chars(data):
    return pdfium.PdfDocument(data)[0].get_textpage().get_text_range()
def img_md5(data):
    pdf = pikepdf.open(io.BytesIO(data))
    return sorted(hashlib.md5(o.read_raw_bytes()).hexdigest() for o in pdf.objects if isinstance(o, pikepdf.Stream) and o.get("/Subtype") == "/Image")

dirs = sys.argv[1:] or [str(ROOT / "data/fixtures_private/kn_private"), str(ROOT / "data/fixtures_private/hi_private")]
bad = 0; n = 0
for f in sorted(p for d in dirs for p in glob.glob(d + "/*.pdf")):
    before = Path(f).read_bytes(); pdf = pikepdf.open(io.BytesIO(before)); st = strip_invisible_text(pdf, pdf.pages[0])
    b = io.BytesIO(); pdf.save(b); after = b.getvalue(); n += 1
    diff = int(np.abs(render(before) - render(after)).max()); tb, ta = chars(before), chars(after)
    ok = diff == 0 and img_md5(before) == img_md5(after)
    bad += not ok
    print(f"{'OK ' if ok else 'BAD'} {Path(f).name[:34]:34s} removed_ops={st.get('removed_ops', 0):4d} chars {len(tb):5d} -> {len(ta):4d} "
          f"pixel_diff={diff} left={ta.strip()[:40]!r}")
print(f"{n - bad}/{n} pages pass")
