"""arjuna-pdf command line:  python -m arjuna_pdf.cli in.pdf -o out.pdf --lang kn [--dpi 200] [--force] [--sidecar out.json]"""
import argparse, json, logging
from .engine import ArjunaPDF

def main(argv=None):
    ap = argparse.ArgumentParser(prog="arjuna-pdf")
    ap.add_argument("inputs", nargs="+"); ap.add_argument("-o", "--output", help="output PDF (single input) or directory")
    ap.add_argument("--lang", default="kn", choices=["kn", "hi"]); ap.add_argument("--dpi", type=float)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--redo", action="store_true", help="strip old invisible OCR text, then OCR (born-digital pages are skipped)")
    g.add_argument("--force", action="store_true", help="OCR every page, keep existing text")
    ap.add_argument("--providers", help="trt | cuda | cpu | auto"); ap.add_argument("--sidecar", help="JSON report path")
    ap.add_argument("--txt", help="also write the recognised text here (pages separated by form feeds)")
    ap.add_argument("--autorotate", action="store_true", help="set /Rotate so pages Arjuna had to turn display upright")
    ap.add_argument("--pdfa", choices=["1b", "2b", "3b"], help="write PDF/A of this flavour (pikepdf.pdfa)")
    ap.add_argument("--no-word-boxes", action="store_true", help="proportional word placement (skip the CTC word step)")
    ap.add_argument("--include-withheld", action="store_true", help="also write lines Arjuna withholds (seal/figure/handwriting)")
    a = ap.parse_args(argv); logging.basicConfig(level=logging.INFO)
    eng = ArjunaPDF(a.lang, dpi=a.dpi, providers=a.providers, word_boxes=not a.no_word_boxes, include_withheld=a.include_withheld)
    from pathlib import Path
    for f in a.inputs:
        out = Path(a.output) if a.output and (len(a.inputs) == 1 and not Path(a.output).is_dir()) else Path(a.output or ".") / (Path(f).stem + "_ocr.pdf")
        r = eng.process(f, out, mode="redo" if a.redo else "force" if a.force else "skip", sidecar=a.sidecar,
                        txt=a.txt if len(a.inputs) == 1 else None, autorotate=a.autorotate, pdfa=a.pdfa)
        print(json.dumps({"output": str(out), "seconds": r["seconds"], "pages": [(p["page"], p.get("lines", p.get("skipped"))) for p in r["pages"]]}, ensure_ascii=False))

if __name__ == "__main__":
    main()
