"""Run arjuna-pdf over a directory of PDFs (one process, one language pack). Usage: run_bench.py <kn|hi> <in_dir> <out_dir> [mode]"""
import sys, json, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from arjuna_pdf.engine import ArjunaPDF
lang, src, out = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]); mode = sys.argv[4] if len(sys.argv) > 4 else "redo"
out.mkdir(parents=True, exist_ok=True); eng = ArjunaPDF(lang); timing = {}
for f in sorted(src.glob("*.pdf")):
    t = time.time(); r = eng.process(f, out / f.name, mode=mode, sidecar=out / (f.stem + ".json")); timing[f.name] = round(time.time() - t, 2)
    print(f.name, timing[f.name], "s", flush=True)
(out / "timing.json").write_text(json.dumps(timing, indent=1))
