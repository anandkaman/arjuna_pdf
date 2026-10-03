"""A/B text-layer encodings WITHOUT re-running OCR: rebuild our layer from the sidecar `written` lines onto a blank
page of the same MediaBox and score every extractor. Usage: textlayer_ab.py <sidecar.json>... """
import sys, json, io
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tests"))
sys.path.append(str(ROOT / ".deps"))
import pikepdf
from arjuna_pdf.textlayer import TextLine, Word, text_form
from gate_m1 import EXTRACTORS, fidelity
MODES = [m for m in ("line", "words", "split", "fit") if m in sys.argv[-1].split(",")] if "," in sys.argv[-1] or sys.argv[-1] in ("line","words","split","fit") else ["line", "words"]
if sys.argv[-1] in ("line","words","split","fit") or "," in sys.argv[-1]: sys.argv = sys.argv[:-1]
res = {}
for side in sys.argv[1:]:
    rep = json.loads(Path(side).read_text()); src = pikepdf.open(rep["output"])
    for pg in rep["pages"]:
        if not pg.get("written"): continue
        lines = [TextLine(tuple(w["pdf_origin"]), tuple(w["dir"]), w["h"], w["w"], text=w["text"],
                          words=[Word(t, a, b) for t, a, b in w["words"]] if w.get("words") else []) for w in pg["written"]]
        for mode in MODES:
            pdf = pikepdf.new(); pdf.add_blank_page(page_size=(100, 100)); p = pdf.pages[0]
            p.obj.MediaBox = pikepdf.Array([float(v) for v in src.pages[pg["page"] - 1].mediabox])
            f = text_form(pdf, lines, [float(v) for v in p.mediabox], mode)
            p.obj.Resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary({"/OCRab": f})); p.obj.Contents = pdf.make_stream(b"q /OCRab Do Q\n")
            b = io.BytesIO(); pdf.save(b); data = b.getvalue(); texts = [w["text"] for w in pg["written"]]
            if any(l.words for l in lines):   # selection fidelity: pdfium char boxes per word vs the span asked for
                import pypdfium2 as pdfium
                tp = pdfium.PdfDocument(data)[0].get_textpage(); full = tp.get_text_range(); pos = 0; sel = res.setdefault((mode, "~sel_iou"), [])
                for l in lines:
                    if not l.words or abs(l.direction[1]) > 0.05: continue
                    for wd in l.words:
                        k = full.find(wd.text, pos)
                        if k < 0: continue
                        bx = [tp.get_charbox(i) for i in range(k, k + len(wd.text))]; lo, hi = min(c[0] for c in bx), max(c[2] for c in bx)
                        A0, A1 = l.origin[0] + wd.x0, l.origin[0] + wd.x1; uni = max(hi, A1) - min(lo, A0)
                        sel.append(max(0, min(hi, A1) - max(lo, A0)) / uni if uni > 0 else 0); pos = k + len(wd.text)
            for e, fn in EXTRACTORS.items():
                r = fidelity(texts, fn(data)); k = (mode, e); a = res.setdefault(k, [0, 0, 0, 0])
                a[0] += 1; a[1] += r["recall"] == 1 and r["precision"] == 1 and r["bad"] == 0; a[2] += r["extra_tokens"]; a[3] += r["bad"]
for (mode, e), v in sorted(res.items()):
    if e == "~sel_iou": print(f"{mode:6s} selection IoU mean {sum(v)/max(len(v),1):.3f}  <0.8: {sum(x < 0.8 for x in v)}/{len(v)}"); continue
    n, ex, extra, bad = v; print(f"{mode:6s} {e:9s} exact {ex}/{n}  extra_tokens {extra}  bad {bad}")
