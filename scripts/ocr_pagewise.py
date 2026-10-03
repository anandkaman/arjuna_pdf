"""OCR a PDF one page per process (bounded RAM on CPU beside training): page k is OCR'd in a fresh process with
mode=force on the previous result, so each step adds exactly one page's text layer. Usage:
    ocr_pagewise.py <kn|hi> in.pdf out.pdf [txt]      (each step runs under a 7 GB cgroup, CPU provider)"""
import sys, json, subprocess, shutil
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
lang, src, out = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]); txt = sys.argv[4] if len(sys.argv) > 4 else None
sys.path.append(str(ROOT / ".deps")); import pikepdf
n = len(pikepdf.open(src).pages); work = out.with_suffix(".work.pdf"); reports, texts = [], []
start = int(sys.argv[5]) if len(sys.argv) > 5 else 1   # resume: continue an existing .work.pdf from this page
if start == 1: shutil.copy(src, work)
STEP = """
import sys, json; sys.path.insert(0, %r)
from arjuna_pdf.engine import ArjunaPDF, low_memory_cpu
low_memory_cpu()
r = ArjunaPDF(%r, providers='cpu').process(%r, %r, mode='force', pages=[%d], autorotate=True, txt=%r)
p = r['pages'][0]; p.pop('written', None); print('REPORT', json.dumps(p, ensure_ascii=False))
"""
for k in range(start, n + 1):
    nxt = out.with_suffix(f".p{k}.pdf"); ptxt = str(out.with_suffix(f".p{k}.txt"))
    cmd = ["systemd-run", "--scope", "--quiet", "-p", "MemoryMax=7G", "-p", "MemorySwapMax=0", sys.executable, "-c",
           STEP % (str(ROOT), lang, str(work), str(nxt), k, ptxt)]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    line = [l for l in r.stdout.splitlines() if l.startswith("REPORT")]
    if r.returncode or not line: print(f"page {k}: FAILED rc={r.returncode}", r.stderr[-400:]); sys.exit(1)
    rep = json.loads(line[0][7:]); reports.append(rep); shutil.move(nxt, work)
    texts.append(Path(ptxt).read_text(encoding="utf-8")); Path(ptxt).unlink()
    print(f"page {k}/{n}: lines {rep.get('lines')} ctc-words {rep.get('lines_ctc_words')} withheld {rep.get('lines_withheld')} rot {rep.get('arjuna_rotation')}", flush=True)
shutil.move(work, out)
if txt: Path(txt).write_text("\f".join(texts), encoding="utf-8")
Path(str(out) + ".report.json").write_text(json.dumps(reports, ensure_ascii=False, indent=1)); print("DONE", out)
