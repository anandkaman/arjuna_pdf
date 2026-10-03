"""M2 gate: are the word boxes where the words are?  (pixels of the ORIGINAL page, no ground truth needed)

For every written line that got CTC word boxes, the SAME line is also split proportionally (the M1 fallback), and both
are measured on the page image rendered at the sidecar's DPI (Otsu ink mask), sampling across the line's inner band:
  edge_in_ink   fraction of word edges whose column 1.5 px OUTSIDE the word holds ink (box cuts a glyph) -> lower is better
  uncovered_ink fraction of the line's ink columns covered by no word box                        -> lower is better
  selection_iou pdfium per-word char boxes vs the word span we wrote (renderer fidelity, CTC only)
Pages with /Rotate != 0 are skipped (M3). Usage: python tests/gate_m2.py runs/m2/kn runs/m2/hi ...
"""
import sys, json, io
from pathlib import Path
import numpy as np, cv2, pypdfium2 as pdfium
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT)); sys.path.append(str(ROOT / ".deps"))
from arjuna_pdf.textlayer import split_words
from gate_m1 import text_only_pdf

BAND = (0.15, 0.80)   # fraction of line height sampled (box has 3 % top / 25 % bottom padding; avoid neighbour lines)


def column_ink(mask, o, d, up, x, h, s, x0c, y1c):
    """Ink pixels in the 1-pt-wide column at distance x along the line (PDF space -> pixel space)."""
    ts = np.linspace(BAND[0], BAND[1], max(4, int(h * s * (BAND[1] - BAND[0]))))
    pts = o[None] + d[None] * x + up[None] * ts[:, None] * h
    px = np.round((pts[:, 0] - x0c) * s).astype(int); py = np.round((y1c - pts[:, 1]) * s).astype(int)
    ok = (px >= 0) & (py >= 0) & (px < mask.shape[1]) & (py < mask.shape[0])
    return int(mask[py[ok], px[ok]].sum())


def measure(spans, mask, o, d, up, h, w, s, x0c, y1c):
    step = 1.0 / s   # one pixel along the line, in pt
    edges = [x for a, b in spans for x in (a - 1.5 * step, b + 1.5 * step)]   # just OUTSIDE each word: should be paper
    cut = sum(column_ink(mask, o, d, up, x, h, s, x0c, y1c) > 0 for x in edges)
    xs = np.arange(0, w, step); ink = np.array([column_ink(mask, o, d, up, x, h, s, x0c, y1c) > 0 for x in xs])
    cov = np.zeros_like(ink)
    for a, b in spans: cov |= (xs >= a) & (xs <= b)
    return cut, len(edges), int((ink & ~cov).sum()), int(ink.sum())


def main(dirs):
    agg = {}
    for dd in dirs:
        A = agg.setdefault(Path(dd).name, {"lines": 0, "ctc_lines": 0, "ctc": [0, 0, 0, 0], "prop": [0, 0, 0, 0], "sel": []})
        for side in sorted(Path(dd).glob("*.json")):
            rep = json.loads(side.read_text()); pg = rep["pages"][0]
            if "written" not in pg or pg.get("rotate", 0) != 0: continue
            doc = pdfium.PdfDocument(rep["input"]); page = doc[pg["page"] - 1]; s = pg["dpi"] / 72.0
            gray = page.render(scale=s, grayscale=True).to_numpy(); gray = gray[:, :, 0] if gray.ndim == 3 else gray
            _, mask = cv2.threshold(np.ascontiguousarray(gray), 0, 1, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            x0c, _, _, y1c = page.get_cropbox()
            tp = pdfium.PdfDocument(text_only_pdf(rep["output"], pg["page"]))[0].get_textpage()
            full = tp.get_text_range(); pos = 0
            for wl in pg["written"]:
                A["lines"] += 1
                if not wl.get("words"): continue
                A["ctc_lines"] += 1
                o = np.array(wl["pdf_origin"]); d = np.array(wl["dir"]); h, w = wl["h"], wl["w"]; up = np.array([-d[1], d[0]])
                ctc = [(a, b) for _, a, b in wl["words"]]; prop = [(x.x0, x.x1) for x in split_words(wl["text"], w)]
                for key, spans in (("ctc", ctc), ("prop", prop)):
                    r = measure(spans, mask, o, d, up, h, w, s, x0c, y1c); A[key] = [u + v for u, v in zip(A[key], r)]
                # renderer fidelity: pdfium char boxes of each written word vs the span we asked for (horizontal lines only)
                if abs(d[1]) < 0.05:
                    for word, a, b in wl["words"]:
                        k = full.find(word, pos)
                        if k < 0: continue
                        bx = [tp.get_charbox(i) for i in range(k, k + len(word))]
                        lo, hi = min(c[0] for c in bx), max(c[2] for c in bx); A0, A1 = o[0] + a, o[0] + b
                        inter = max(0, min(hi, A1) - max(lo, A0)); uni = max(hi, A1) - min(lo, A0)
                        A["sel"].append(inter / uni if uni > 0 else 0); pos = k + len(word)
    out = {}
    for k, A in agg.items():
        f = lambda v: {"edge_in_ink": round(v[0] / max(v[1], 1), 4), "uncovered_ink": round(v[2] / max(v[3], 1), 4)}
        out[k] = {"lines": A["lines"], "ctc_word_lines": A["ctc_lines"], "ctc_coverage": round(A["ctc_lines"] / max(A["lines"], 1), 4),
                  "ctc": f(A["ctc"]), "proportional_same_lines": f(A["prop"]),
                  "selection_iou_mean": round(float(np.mean(A["sel"])), 4) if A["sel"] else None,
                  "selection_iou_lt_0.8": int(sum(v < 0.8 for v in A["sel"])), "words_checked": len(A["sel"])}
    return out


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1:]), indent=1))
