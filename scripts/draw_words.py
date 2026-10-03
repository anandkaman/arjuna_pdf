"""Draw the word boxes WE wrote (sidecar JSON) on the rendered original page: green = CTC words, orange = proportional.
Usage: draw_words.py sidecar.json out.jpg [dpi]"""
import sys, json
import numpy as np, cv2, pypdfium2 as pdfium
side, out = sys.argv[1], sys.argv[2]; dpi = float(sys.argv[3]) if len(sys.argv) > 3 else 150
rep = json.load(open(side)); pg = rep["pages"][0]; doc = pdfium.PdfDocument(rep["input"]); page = doc[pg["page"] - 1]
img = page.render(scale=dpi / 72).to_numpy()[:, :, :3].copy(); s = dpi / 72
x0c, y0c, x1c, y1c = page.get_cropbox()
P = lambda p: (int(round((p[0] - x0c) * s)), int(round((y1c - p[1]) * s)))
for w in pg.get("written", []):
    o = np.array(w["pdf_origin"]); d = np.array(w["dir"]); up = np.array([-d[1], d[0]]) * w["h"]
    spans = [(a, b, (0, 170, 0)) for _, a, b in w["words"]] if w.get("words") else None
    if spans is None:   # proportional: reproduce the writer's split
        sys.path.insert(0, "."); from arjuna_pdf.textlayer import split_words
        spans = [(x.x0, x.x1, (0, 140, 255)) for x in split_words(w["text"], w["w"])]
    for a, b, col in spans:
        q = [o + d * a, o + d * b, o + d * b + up, o + d * a + up]
        cv2.polylines(img, [np.array([P(p) for p in q], np.int32)], True, col, 1)
cv2.imwrite(out, img); print(out, img.shape)
