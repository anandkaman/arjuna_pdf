"""Page images -> one image-only PDF (like a scanner makes): lossless (Flate) grayscale/RGB, page size from the DPI.
Usage: images_to_pdf.py out.pdf dpi img1 img2 ..."""
import sys, zlib
from pathlib import Path
import numpy as np, cv2
sys.path.append(str(Path(__file__).resolve().parents[1] / ".deps")); import pikepdf
out, dpi, imgs = sys.argv[1], float(sys.argv[2]), sys.argv[3:]
pdf = pikepdf.new()
for f in imgs:
    im = cv2.imread(f, cv2.IMREAD_COLOR); h, w = im.shape[:2]
    gray = bool(np.all(im[:, :, 0] == im[:, :, 1]) and np.all(im[:, :, 1] == im[:, :, 2]))
    if gray: data, cs, ncomp = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY).tobytes(), pikepdf.Name.DeviceGray, 1
    else: data, cs, ncomp = cv2.cvtColor(im, cv2.COLOR_BGR2RGB).tobytes(), pikepdf.Name.DeviceRGB, 3
    W, H = w * 72.0 / dpi, h * 72.0 / dpi
    pdf.add_blank_page(page_size=(W, H)); p = pdf.pages[-1]
    img = pikepdf.Stream(pdf, zlib.compress(data, 9), Type=pikepdf.Name.XObject, Subtype=pikepdf.Name.Image, Width=w, Height=h,
                         ColorSpace=cs, BitsPerComponent=8, Filter=pikepdf.Name.FlateDecode)
    p.obj.Resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary(Im0=img))
    p.obj.Contents = pdf.make_stream(f"q {W:.4f} 0 0 {H:.4f} 0 0 cm /Im0 Do Q\n".encode())
pdf.save(out); print(out, len(imgs), "pages", "gray" if gray else "rgb")
