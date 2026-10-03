"""M6 head-to-head scorer: text layers of output PDFs vs hand-verified page ground truth.

Ground truth = VERIFIED lines of a page (not every line on the page was labelled, so this is RECALL only).
Both sides: NFC, whitespace collapsed, ZWJ/ZWNJ removed (Tesseract emits ZWNJ the labels never carry).
  word_recall  multiset recall of GT words in the extracted text
  line_found   fraction of GT lines whose full text appears verbatim (normalised) in the extracted text
Extractors: pdfium (Chrome) and pdfminer. Usage: bench_m6.py <gt.json> <out_dir> [<out_dir> ...]
"""
import sys, json, unicodedata, collections, io
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "tests")); sys.path.append(str(ROOT / ".deps"))
import pypdfium2 as pdfium

ZW = dict.fromkeys(map(ord, "‌‍"), None)
def norm(s): return " ".join(unicodedata.normalize("NFC", s).translate(ZW).split())
def ex_pdfium(p): return pdfium.PdfDocument(str(p))[0].get_textpage().get_text_range()
def ex_pdfminer(p):
    from pdfminer.high_level import extract_text; return extract_text(str(p))


def score(gt_json, out_dir):
    gt = json.loads(Path(gt_json).read_text()); res = {}
    for name, fn in (("pdfium", ex_pdfium), ("pdfminer", ex_pdfminer)):
        hit = tot = lf = lt = 0; per = []
        for m in gt:
            f = Path(out_dir) / f"{m['page_id']}.pdf"
            if not f.exists(): continue
            text = norm(fn(f)); E = collections.Counter(text.split())
            G = collections.Counter(w for l in m["gt_lines"] for w in norm(l).split())
            h = sum((G & E).values()); hit += h; tot += sum(G.values())
            found = sum(1 for l in m["gt_lines"] if norm(l) and norm(l) in text); lf += found; lt += len(m["gt_lines"])
            per.append((m["page_id"], round(h / max(sum(G.values()), 1), 4)))
        res[name] = {"pages": len(per), "word_recall": round(hit / max(tot, 1), 4), "line_found": round(lf / max(lt, 1), 4),
                     "gt_words": tot, "gt_lines": lt, "worst_pages": sorted(per, key=lambda x: x[1])[:5]}
    return res


if __name__ == "__main__":
    gt_json = sys.argv[1]
    print(json.dumps({Path(d).name: score(gt_json, d) for d in sys.argv[2:]}, ensure_ascii=False, indent=1))
