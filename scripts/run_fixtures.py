"""OCR every fixture page of one language pair into runs/<out>/<set>/ (+ JSON sidecars). One process per pair.
Usage: run_fixtures.py <kn|hi> <out_name> [providers] [--no-words]. All pages run in redo mode: the private pages carry an old invisible OCR layer, which is stripped first."""
import sys, json, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from arjuna_pdf.engine import ArjunaPDF
lang, name_out = sys.argv[1], sys.argv[2]; prov = sys.argv[3] if len(sys.argv) > 3 and not sys.argv[3].startswith("--") else None
sets = {"kn": [("fixtures", "kn"), ("fixtures_private", "kn_private")], "hi": [("fixtures", "hi"), ("fixtures_private", "hi_private")]}[lang]
import os
ov = {"provider": {"cuda_mem_limit_gb": float(os.environ["ARJUNA_PDF_CUDA_GB"])}} if os.environ.get("ARJUNA_PDF_CUDA_GB") else None
eng = ArjunaPDF(lang, providers=prov, word_boxes="--no-words" not in sys.argv, overrides=ov); summary = []
for base, name in sets:
    out = ROOT / "runs" / name_out / name; out.mkdir(parents=True, exist_ok=True)
    for f in sorted((ROOT / "data" / base / name).glob("*.pdf")):
        t = time.time(); r = eng.process(f, out / f.name, mode="redo", sidecar=out / (f.stem + ".json")); p = r["pages"][0]
        summary.append({"set": name, "file": f.name, "s": round(time.time() - t, 2), **{k: p.get(k) for k in ("lines", "lines_ctc_words", "lines_proportional", "lines_withheld", "dpi")}})
        print(json.dumps(summary[-1], ensure_ascii=False), flush=True)
(ROOT / "runs" / name_out / f"summary_{lang}.json").write_text(json.dumps(summary, indent=1))
