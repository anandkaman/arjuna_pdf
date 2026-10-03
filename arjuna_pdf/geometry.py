"""Coordinate contract: Arjuna output frame -> raster frame -> PDF user space.

Arjuna (kanen_infer.batch_pipeline) returns boxes in the frame it finally read the page in:
    final = flip180?( deskew( rot90?(raster) ) )
    rot90  : np.rot90(img, 1) when page.rotation in {90, 270}      (x', y') = (y, W - x)
    deskew : cv2.getRotationMatrix2D((w/2, h/2), deg, 1) on a same-size canvas, ONLY when |deg| > 0.4
    flip180: np.rot90(img, 2) when page.rotation in {180, 270}    (x', y') = (w - x, h - y)
`page.deskew_deg` is reported even when it was below the 0.4 threshold and NOT applied -- replicate that.
This module inverts the chain exactly; tests/test_geometry.py checks it against Arjuna on rotated renders.
"""
import numpy as np, cv2

DESKEW_MIN_DEG = 0.4   # batch_pipeline._stage_a: `if abs(ang[i]) > 0.4`


class ArjunaToRaster:
    def __init__(self, raster_w, raster_h, rotation, deskew_deg):
        self.W, self.H = float(raster_w), float(raster_h); self.rot = int(rotation) % 360
        self.r90 = self.rot in (90, 270); self.f180 = self.rot in (180, 270)
        self.w1, self.h1 = (self.H, self.W) if self.r90 else (self.W, self.H)   # frame after rot90
        self.Minv = None
        if abs(deskew_deg) > DESKEW_MIN_DEG:
            M = cv2.getRotationMatrix2D((self.w1 / 2, self.h1 / 2), float(deskew_deg), 1.0)
            self.Minv = cv2.invertAffineTransform(M)

    def __call__(self, pts):
        p = np.asarray(pts, np.float64).reshape(-1, 2).copy()
        if self.f180: p[:, 0] = self.w1 - p[:, 0]; p[:, 1] = self.h1 - p[:, 1]
        if self.Minv is not None: p = p @ self.Minv[:, :2].T + self.Minv[:, 2]
        if self.r90: p = np.stack([self.W - p[:, 1], p[:, 0]], 1)
        return p


class RasterToPdf:
    """Raster pixel -> PDF user space for a page rendered by pdfium at `scale` px/pt (CropBox, /Rotate applied)."""
    def __init__(self, cropbox, rotate, scale, user_unit=1.0):
        self.x0, self.y0, self.x1, self.y1 = map(float, cropbox); self.rot = int(rotate) % 360
        self.s = float(scale) * float(user_unit)

    def __call__(self, pts):
        p = np.asarray(pts, np.float64).reshape(-1, 2) / self.s     # points in the rendered (rotated) view, y down
        u, v = p[:, 0], p[:, 1]
        if self.rot == 0:   X, Y = self.x0 + u, self.y1 - v
        elif self.rot == 90:  X, Y = self.x0 + v, self.y0 + u
        elif self.rot == 180: X, Y = self.x1 - u, self.y0 + v
        elif self.rot == 270: X, Y = self.x1 - v, self.y1 - u
        else: raise ValueError(f"/Rotate {self.rot}")
        return np.stack([X, Y], 1)


def line_frame(bbox, to_raster, to_pdf):
    """Arjuna line bbox [x0,y0,x1,y1] (final frame) -> (origin, unit direction, height, width) in PDF space."""
    x0, y0, x1, y1 = map(float, bbox)
    tl, tr, br, bl = to_pdf(to_raster([[x0, y0], [x1, y0], [x1, y1], [x0, y1]]))
    along = br - bl; up = tl - bl
    width = float(np.hypot(*along)); height = float(np.hypot(*up))
    d = along / width if width > 0 else np.array([1.0, 0.0])
    return (float(bl[0]), float(bl[1])), (float(d[0]), float(d[1])), height, width
