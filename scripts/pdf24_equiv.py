"""PDF24 Creator OCR, reproduced on Linux with its default OCR settings: [strip old invisible text = removeExistingText] -> render GRAY at
min(300 dpi, <= 50 MP) -> tesseract -l <langs> -c textonly_pdf=1 --dpi D --oem 3 --psm 1 pdf txt (PDF24's own tessdata)
-> overlay the text-only page as a FOREGROUND form onto the original page.  Usage:
    pdf24_equiv.py <langs e.g. kan+eng> <out_dir> in1.pdf in2.pdf ...      (OMP_THREAD_LIMIT=1 is forced)"""
import sys, os, io, json, time, subprocess, tempfile
from pathlib import Path
import numpy as np, cv2, pypdfium2 as pdfium
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT)); sys.path.append(str(ROOT / ".deps"))
import pikepdf
from arjuna_pdf.pdftext import strip_invisible_text
TESSDATA = ROOT / "models/tessdata_pdf24"


def pdf24_dpi(w_pt, h_pt, dpi=300, max_mp=50.0):
    return min(int((max_mp * 1024 * 1024 * 72 * 72 / w_pt / h_pt) ** 0.5), dpi)


def ocr_pdf(src_path, out_path, langs):
    t0 = time.time(); pk = pikepdf.open(src_path)
    for p in pk.pages: strip_invisible_text(pk, p)
    buf = io.BytesIO(); pk.save(buf); data = buf.getvalue(); pk = pikepdf.open(io.BytesIO(data)); doc = pdfium.PdfDocument(data)
    with tempfile.TemporaryDirectory() as td:
        for i in range(len(doc)):
            pg = doc[i]; x0, y0, x1, y1 = pg.get_cropbox(); rot = pg.get_rotation()
            if rot: raise NotImplementedError("PDF24-equivalent: /Rotate != 0 not handled here")
            dpi = pdf24_dpi(x1 - x0, y1 - y0)
            a = pg.render(scale=dpi / 72, grayscale=True).to_numpy(); a = a[:, :, 0] if a.ndim == 3 else a
            png = f"{td}/p{i}.png"; cv2.imwrite(png, a); base = f"{td}/t{i}"
            subprocess.run(["nice", "-n", "19", "tesseract", png, base, "--tessdata-dir", str(TESSDATA), "-l", langs, "-c", "textonly_pdf=1",
                            "--dpi", str(dpi), "--oem", "3", "--psm", "1", "pdf", "txt"], check=True, capture_output=True,
                           env=dict(os.environ, OMP_THREAD_LIMIT="1"))
            tp = pikepdf.open(base + ".pdf"); tpage = tp.pages[0]; tw, th = float(tpage.mediabox[2]), float(tpage.mediabox[3])
            form = pk.copy_foreign(tpage.as_form_xobject()); page = pk.pages[i]
            name = pikepdf.Name.random(prefix="PDF24")
            if pikepdf.Name.XObject not in page.obj.Resources: page.obj.Resources.XObject = pikepdf.Dictionary()
            page.obj.Resources.XObject[name] = form
            cm = f"{(x1 - x0) / tw:.6f} 0 0 {(y1 - y0) / th:.6f} {x0:.4f} {y0:.4f} cm"
            page.contents_add(pikepdf.Stream(pk, b"q\n"), prepend=True)
            page.contents_add(pikepdf.Stream(pk, f"\nQ\nq {cm} {name} Do Q\n".encode()), prepend=False)
    pk.save(out_path); return round(time.time() - t0, 2)


if __name__ == "__main__":
    langs, out = sys.argv[1], Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True); res = {}
    for f in sys.argv[3:]:
        res[Path(f).name] = ocr_pdf(f, out / Path(f).name, langs); print(Path(f).name, res[Path(f).name], "s", flush=True)
    (out / "timing.json").write_text(json.dumps(res, indent=1))
