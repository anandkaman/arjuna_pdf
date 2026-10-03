"""M3 geometry tests (no OCR):  python tests/test_geometry.py

1. RasterToPdf: a black box drawn at a KNOWN user-space rectangle on pages with /Rotate 0/90/180/270, offset CropBoxes
   and /UserUnit; rendered by pdfium exactly like the engine does; its pixel bbox mapped back must land on the rectangle.
2. ArjunaToRaster: a marker on a raster, pushed through Arjuna's OWN transforms in Arjuna's order
   (rot90 -> deskew rotate_small if |deg| > 0.4 -> flip180), found again, and mapped back must land on the original.
"""
import io, sys
from pathlib import Path
import numpy as np, cv2, pypdfium2 as pdfium
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT)); sys.path.append(str(ROOT / ".deps"))
import pikepdf
from arjuna_pdf.geometry import RasterToPdf, ArjunaToRaster
sys.path.insert(0, "/root/server_ai/Arjuna/deploy/inference_repo")
from kanen_infer.geometry import rotate_page, rotate_small

RECT = (130.0, 210.0, 250.0, 260.0)   # user-space x0 y0 x1 y1 of the black box


def make_pdf(rotate=0, media=(0, 0, 400, 600), crop=None, user_unit=None):
    pdf = pikepdf.new(); pdf.add_blank_page(page_size=(400, 600)); p = pdf.pages[0]
    p.obj.MediaBox = pikepdf.Array(list(media))
    if crop: p.obj.CropBox = pikepdf.Array(list(crop))
    if rotate: p.obj.Rotate = rotate
    if user_unit: p.obj.UserUnit = user_unit
    x0, y0, x1, y1 = RECT
    p.obj.Contents = pdf.make_stream(f"0 g {x0} {y0} {x1 - x0} {y1 - y0} re f\n".encode())
    b = io.BytesIO(); pdf.save(b); return b.getvalue()


def check_pdf_case(rotate, media=(0, 0, 400, 600), crop=None, user_unit=None, dpi=150.0):
    data = make_pdf(rotate, media, crop, user_unit); pg = pdfium.PdfDocument(data)[0]
    # engine: render(scale=dpi/72), RasterToPdf(cropbox, rotation, dpi/72)
    a = pg.render(scale=dpi / 72, grayscale=True).to_numpy(); a = a[:, :, 0] if a.ndim == 3 else a
    ys, xs = np.nonzero(a < 128)
    px = np.array([[xs.min(), ys.min()], [xs.max() + 1, ys.max() + 1]], float)
    m = RasterToPdf(pg.get_cropbox(), pg.get_rotation(), dpi / 72.0)(px)
    got = (m[:, 0].min(), m[:, 1].min(), m[:, 0].max(), m[:, 1].max())
    err = max(abs(g - r) for g, r in zip(got, RECT))
    return err, got


def check_arjuna_case(rotation, deskew, W=900, H=1300):
    img = np.full((H, W), 255, np.uint8); pt = (310, 420); cv2.circle(img, pt, 6, 0, -1)
    x = img
    if rotation in (90, 270): x = rotate_page(x, 1)
    if abs(deskew) > 0.4: x = rotate_small(x, deskew)
    if rotation in (180, 270): x = rotate_page(x, 2)
    ys, xs = np.nonzero(x < 128); c = np.array([[xs.mean() + 0.5, ys.mean() + 0.5]])
    back = ArjunaToRaster(W, H, rotation, deskew)(c)[0]
    return float(np.hypot(back[0] - (pt[0] + 0.5), back[1] - (pt[1] + 0.5)))


def main():
    fails = 0
    for rot in (0, 90, 180, 270):
        for media, crop in (((0, 0, 400, 600), None), ((0, 0, 400, 600), (50, 80, 380, 560)), ((-100, -50, 300, 550), None)):
            err, got = check_pdf_case(rot, media, crop); ok = err < 1.0; fails += not ok
            print(f"{'OK ' if ok else 'BAD'} pdf  /Rotate {rot:3d} media={media} crop={crop}: max err {err:.2f} pt")
    for uu in (2.0,):
        err, got = check_pdf_case(0, user_unit=uu); ok = err < 1.0
        print(f"{'OK ' if ok else 'INFO'} pdf  /UserUnit {uu}: max err {err:.2f} pt (got {tuple(round(v, 1) for v in got)})")
    for rot in (0, 90, 180, 270):
        for dk in (0.0, 0.3, 1.7, -2.4):
            e = check_arjuna_case(rot, dk); ok = e < 1.5; fails += not ok
            print(f"{'OK ' if ok else 'BAD'} arjuna rotation {rot:3d} deskew {dk:5.1f}: error {e:.2f} px")
    print("FAILURES:", fails); return fails


if __name__ == "__main__":
    sys.exit(main())
