"""M1 gate for arjuna-pdf outputs (runs/m1/<set>/*.pdf + sidecar JSON).

1. FIDELITY  - our text layer alone (the OCR form XObject on a blank page) is extracted by pdfium, poppler
               (pdftotext -raw), pdfminer and mupdf; every written line must come back exactly (whitespace-normalised),
               with no control chars / U+FFFD / "(cid:" and no words split by spurious spaces.
2. GEOMETRY  - pdfium character boxes of each extracted line vs the box we meant to write (IoU, axis-aligned,
               in points). Run on the text-only page so old text layers cannot interfere.
3. IMAGES    - every image XObject stream of the input is byte-identical in the output.
4. GRAFT     - the FULL output page (incl. any old text) still yields our lines in order via pdfium.
Usage: python tests/gate_m1.py runs/m1/kn runs/m1/hi ...
"""
import sys, re, json, hashlib, subprocess, unicodedata, io
from pathlib import Path
from collections import Counter
ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / ".deps")); sys.path.append(str(ROOT / ".deps_test"))
import pikepdf, pypdfium2 as pdfium

BAD = re.compile(r"[\x00-\x08\x0b\x0e-\x1f�]|\(cid:")   # \t \n \f \r are layout separators, not corruption
norm = lambda s: " ".join(unicodedata.normalize("NFC", s).split())


def text_only_pdf(out_pdf, page_no):
    """New one-page PDF holding only our OCR form XObject (same MediaBox) -> bytes."""
    src = pikepdf.open(out_pdf); pg = src.pages[page_no - 1]
    names = [k for k in pg.obj.Resources.XObject.keys() if k.startswith("/OCR")]
    assert len(names) == 1, names
    dst = pikepdf.new(); dst.add_blank_page(page_size=(100, 100)); p = dst.pages[0]
    p.obj.MediaBox = pikepdf.Array([float(v) for v in pg.mediabox])
    p.obj.Resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary({names[0]: dst.copy_foreign(pg.obj.Resources.XObject[names[0]])}))
    p.obj.Contents = dst.make_stream(f"q {names[0]} Do Q\n".encode())
    b = io.BytesIO(); dst.save(b); return b.getvalue()


def ex_pdfium(data):
    d = pdfium.PdfDocument(data); tp = d[0].get_textpage(); return tp.get_text_range()
def ex_poppler(data):
    return subprocess.run(["pdftotext", "-raw", "-", "-"], input=data, capture_output=True).stdout.decode("utf-8", "replace")
def ex_pdfminer(data):
    from pdfminer.high_level import extract_text; return extract_text(io.BytesIO(data))
def ex_mupdf(data):
    import pymupdf; return pymupdf.open(stream=data, filetype="pdf")[0].get_text()
_NODE = ROOT / ".deps_test" / "nodejs_wheel" / "bin" / "node"; _PDFJS = ROOT / "tools" / "pdfjs"
def ex_pdfjs(data):
    """pdf.js (Firefox / web viewers) getTextContent, items joined, newline at hasEOL (tools/pdfjs/ext.mjs)."""
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
        f.write(data); f.flush()
        return subprocess.run([str(_NODE), "ext.mjs", f.name], cwd=_PDFJS, capture_output=True).stdout.decode("utf-8", "replace")
EXTRACTORS = {"pdfium": ex_pdfium, "poppler": ex_poppler, "pdfminer": ex_pdfminer, "mupdf": ex_mupdf}
if _NODE.exists() and (_PDFJS / "ext.mjs").exists(): EXTRACTORS["pdfjs"] = ex_pdfjs


def fidelity(written, text):
    """Token-multiset recall/precision of written words in extracted text + forbidden-char count + split words."""
    w = Counter(t for l in written for t in norm(l).split()); e = Counter(norm(text).split())
    hit = sum((w & e).values())
    extra = e - w   # tokens that were never written: fragments of split words or merged neighbours
    if not w and not e: return {"recall": 1.0, "precision": 1.0, "bad": len(BAD.findall(text)), "extra_tokens": 0, "extra_examples": []}
    return {"recall": hit / max(sum(w.values()), 1), "precision": hit / max(sum(e.values()), 1), "bad": len(BAD.findall(text)),
            "extra_tokens": sum(extra.values()), "extra_examples": [t for t, _ in extra.most_common(3)]}


def geometry(data, written):
    """For each written line, find its first+last char in pdfium's char stream and compare boxes (IoU in pt)."""
    d = pdfium.PdfDocument(data); tp = d[0].get_textpage(); n = tp.count_chars(); full = tp.get_text_range()
    ious, pos = [], 0
    for wl in written:
        t = unicodedata.normalize("NFC", wl["text"]).strip(); k = full.find(t, pos)
        if k < 0: continue
        boxes = [tp.get_charbox(i) for i in range(k, k + len(t)) if not full[i].isspace()]
        boxes = [b for b in boxes if b[2] > b[0]]
        if not boxes: continue
        x0, y0 = min(b[0] for b in boxes), min(b[1] for b in boxes); x1, y1 = max(b[2] for b in boxes), max(b[3] for b in boxes)
        ox, oy = wl["pdf_origin"]; dx, dy = wl["dir"]; h, w = wl["h"], wl["w"]
        cx = [ox, ox + dx * w, ox - dy * h, ox + dx * w - dy * h]; cy = [oy, oy + dy * w, oy + dx * h, oy + dy * w + dx * h]
        X0, X1, Y0, Y1 = min(cx), max(cx), min(cy), max(cy)
        ix = max(0, min(x1, X1) - max(x0, X0)); iy = max(0, min(y1, Y1) - max(y0, Y0)); inter = ix * iy
        u = (x1 - x0) * (y1 - y0) + (X1 - X0) * (Y1 - Y0) - inter
        ious.append(inter / u if u > 0 else 0.0); pos = k + len(t)
    return ious


def image_hashes(pdf_path):
    pdf = pikepdf.open(pdf_path); hs = []
    for o in pdf.objects:
        if isinstance(o, pikepdf.Stream) and o.get("/Subtype") == "/Image":
            hs.append(hashlib.md5(o.read_raw_bytes()).hexdigest())
    return sorted(hs)


def main(dirs):
    rows = []
    for d in dirs:
        for side in sorted(Path(d).glob("*.json")):
            rep = json.loads(side.read_text()); out = Path(rep["output"]); src = Path(rep["input"])
            for pg in rep["pages"]:
                if "written" not in pg: continue
                lines = [w["text"] for w in pg["written"]]; data = text_only_pdf(out, pg["page"])
                row = {"set": Path(d).name, "file": out.name, "page": pg["page"], "lines": len(lines)}
                for name, fn in EXTRACTORS.items():
                    f = fidelity(lines, fn(data)); row[name] = f
                g = geometry(data, pg["written"]); row["iou_mean"] = sum(g) / len(g) if g else None
                row["iou_lt_0.8"] = sum(1 for v in g if v < 0.8); row["geom_found"] = f"{len(g)}/{len(lines)}"
                row["images_identical"] = image_hashes(src) == image_hashes(out)
                full = pdfium.PdfDocument(str(out))[pg["page"] - 1].get_textpage().get_text_range()
                row["graft_recall"] = fidelity(lines, full)["recall"]
                rows.append(row)
    return rows


def summarise(rows):
    import statistics as st
    sets = sorted({r["set"] for r in rows}); out = {}
    for s in sets:
        R = [r for r in rows if r["set"] == s]; o = {"pages": len(R), "lines": sum(r["lines"] for r in R)}
        for e in [x for x in EXTRACTORS if x in R[0]]:
            o[e] = {"exact_pages": sum(1 for r in R if r[e]["recall"] == 1 and r[e]["precision"] == 1 and r[e]["bad"] == 0),
                    "recall_min": round(min(r[e]["recall"] for r in R), 4), "precision_min": round(min(r[e]["precision"] for r in R), 4),
                    "bad_chars": sum(r[e]["bad"] for r in R), "extra_tokens": sum(r[e]["extra_tokens"] for r in R)}
        ious = [r["iou_mean"] for r in R if r["iou_mean"] is not None]
        o["iou_mean"] = round(st.mean(ious), 4) if ious else None; o["iou_lt_0.8_lines"] = sum(r["iou_lt_0.8"] for r in R)
        o["images_identical"] = f'{sum(r["images_identical"] for r in R)}/{len(R)}'
        o["graft_recall_min"] = round(min(r["graft_recall"] for r in R), 4); out[s] = o
    return out


if __name__ == "__main__":
    rows = main(sys.argv[1:])
    (ROOT / "runs" / "m1" / "gate_rows.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1))
    print(json.dumps(summarise(rows), ensure_ascii=False, indent=1))
