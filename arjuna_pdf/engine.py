"""arjuna-pdf engine: PDF in -> Arjuna OCR (layout -> detection -> our recogniser) -> invisible text layer grafted
onto the ORIGINAL pages -> searchable PDF out. The page images are never modified or re-encoded."""
import sys, json, time, logging
from pathlib import Path
import numpy as np, cv2

_HERE = Path(__file__).resolve().parent
sys.path.append(str(_HERE.parent / ".deps"))           # pikepdf; appended so ocr_env's own packages win
import pikepdf, pypdfium2 as pdfium
from .geometry import ArjunaToRaster, RasterToPdf, line_frame
from .textlayer import TextLine, Word, text_form, graft
from . import words as W
from .pdftext import strip_invisible_text
import io

LOG = logging.getLogger("arjuna_pdf")
import os
# Arjuna language packs on Hugging Face (code + config + models in one repo), pinned to the RELEASE commits
# "v1.3.3" / "v1.1.3" (2026-10-04 04:20 UTC), every file byte-identical to the benchmarked local packages.
# The v1.3.3 / v1.1.3 TAGS point to older commits with different code -- pin commits, not those tags.
# NOTE: Kannada comes from `arjuna-ocr-kn-en-inference`; the `arjuna-ocr-kn-en` card repo still holds v1.2.1 (layout v12).
HF_PACKS = {
    "kn": ("anandkaman/arjuna-ocr-kn-en-inference", "1b7414a101c6b4a07f09911ded85f66369ef11d9", "kanen.yaml"),
    # the config MUST be passed: kanen_infer looks for kanen.yaml, the Hindi pack ships arjuna_hi.yaml, and without it the
    # loader silently falls back to the Kannada models (found 2026-10-03; same code in the public hi release)
    "hi": ("anandkaman/arjuna-ocr-hi-en", "072bc43ec22f8329647eacc4ee4cb8a4b2f937bf", "arjuna_hi.yaml"),
}
ENV_PKG = {"kn": "ARJUNA_KN_PKG", "hi": "ARJUNA_HI_PKG"}   # optional: a local directory with kanen_infer/ + config + models/
ENV_REV = {"kn": "ARJUNA_KN_REVISION", "hi": "ARJUNA_HI_REVISION"}   # optional: another HF revision (tag/branch/commit)


def pack_dir(lang):
    """Local directory of the Arjuna pack for `lang`: $ARJUNA_<LANG>_PKG if set, else a Hugging Face snapshot (downloaded
    once into the HF cache, ~170 MB per pack; only code, config, models and VERSION are fetched)."""
    if os.environ.get(ENV_PKG[lang]): return os.environ[ENV_PKG[lang]]
    from huggingface_hub import snapshot_download
    repo, rev, cfg = HF_PACKS[lang]
    return snapshot_download(repo, revision=os.environ.get(ENV_REV[lang], rev),
                             allow_patterns=["kanen_infer/*", cfg, "models/**", "models/*", "VERSION"])


SCRIPT_RANGE = {"kn": (0x0C80, 0x0CFF), "hi": (0x0900, 0x097F)}   # the recogniser's charset must cover this block
DPI_MIN, DPI_MAX, DPI_DEFAULT = 100, 300, 200
VISIBLE_TEXT_MIN = 200   # redo mode: a page keeping >= this many VISIBLE chars is born-digital -> not OCR'd
MODES = ("skip", "redo", "force")


def low_memory_cpu(threads=2):
    """For CPU runs beside training: make every ONNX Runtime session in THIS process skip the CPU memory arena and
    memory-pattern caching (they keep the peak of every shape seen; a single private page exceeded 7 GB), and use few
    threads. Patches onnxruntime.SessionOptions before Arjuna creates its sessions; Arjuna's files are untouched."""
    import onnxruntime as ort
    if getattr(ort.SessionOptions, "_arjuna_pdf_lowmem", False): return
    Base = ort.SessionOptions
    class LowMem(Base):
        _arjuna_pdf_lowmem = True
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self.enable_cpu_mem_arena = False; self.enable_mem_pattern = False
            self.intra_op_num_threads = threads; self.inter_op_num_threads = 1
    ort.SessionOptions = LowMem


def load_ocr(lang, providers=None, **overrides):
    pkg = str(Path(pack_dir(lang)).resolve()); cfg = HF_PACKS[lang][2]
    if "kanen_infer" in sys.modules and not str(Path(sys.modules["kanen_infer"].__file__).resolve()).startswith(pkg):
        raise RuntimeError("another Arjuna language pack is already loaded in this process (one language per process)")
    sys.path.insert(0, pkg)
    try:   # kanen_infer.models.resolve() recognises a pack only by kanen.yaml; pin it to THIS pack so the Hindi pack does
        import kanen_infer.models as _m   # not go and download the Kannada repo (it ships arjuna_hi.yaml instead)
        _m._resolved = Path(pkg)
    except ImportError:
        pass
    from kanen_infer.api import KanEnOCR
    ocr = KanEnOCR(config=str(Path(pkg) / cfg), providers=providers, **overrides)
    check_identity(ocr, lang)
    return ocr


def check_identity(ocr, lang):
    """Refuse to run when the loaded recogniser cannot emit the requested script (wrong model pack / config)."""
    lo, hi = SCRIPT_RANGE[lang]; chars = "".join(getattr(ocr.rec, "chars", []) or [])
    n = sum(lo <= ord(c) <= hi for c in chars)
    if n < 40:
        raise RuntimeError(f"Arjuna model identity check failed: lang={lang} but the recogniser charset has {n} characters in "
                           f"U+{lo:04X}-U+{hi:04X} (config {ocr.cfg.source}, rec {ocr.cfg['models']['rec']})")


def to_pdfa(path, flavour):
    """Convert `path` in place to PDF/A (1b/2b/3b) in a subprocess (see pdfa_tool.py). Returns its JSON report; on failure
    the plain PDF is kept and the report says why."""
    import subprocess, os, tempfile
    tmp = str(path) + ".pdfa.tmp"
    env = dict(os.environ, PYTHONPATH=str(_HERE.parent / ".deps") + os.pathsep + str(_HERE.parent))
    r = subprocess.run([sys.executable, "-m", "arjuna_pdf.pdfa_tool", str(path), tmp, flavour], env=env, capture_output=True, text=True)
    try: rep = json.loads(r.stdout.strip().splitlines()[-1])
    except Exception: rep = {"flavour": flavour, "passed": False, "error": (r.stderr or "")[-1500:]}
    if rep.get("passed") and Path(tmp).exists(): os.replace(tmp, path)
    elif Path(tmp).exists(): os.remove(tmp)
    return rep


def page_has_text(pdf_page):
    tp = pdf_page.get_textpage()
    try: return tp.count_chars() > 0
    finally: tp.close()


def native_dpi(pk_page, crop_w_pt):
    """Pixel density of a page that is one scanned image (else None): render at it so no resampling happens."""
    try:
        imgs = list(pk_page.images.values())
    except Exception:
        return None
    if len(imgs) != 1: return None
    return int(imgs[0].Width) / (crop_w_pt / 72.0)


class ArjunaPDF:
    def __init__(self, lang="kn", dpi=None, providers=None, ocr=None, word_boxes=True, include_withheld=False, overrides=None):
        """word_boxes: place words from the recogniser's CTC frames (else proportional estimates).
        include_withheld: also write lines Arjuna withholds from its text (suppressed seal/figure/handwriting blocks)."""
        self.lang = lang; self.dpi = dpi; self.word_boxes = word_boxes; self.include_withheld = include_withheld
        self.ocr = ocr or load_ocr(lang, providers, **(overrides or {}))
        import kanen_infer.batch_pipeline as bp
        from kanen_infer.pipeline_base import crop
        self._crop = crop
        self._tap = None
        if word_boxes: W.capture(bp); self._tap = W.tap(self.ocr.rec)

    def _render(self, pdf_page, dpi):
        bmp = pdf_page.render(scale=dpi / 72.0, grayscale=True)
        a = bmp.to_numpy(); a = a[:, :, 0] if a.ndim == 3 else a
        return cv2.cvtColor(np.ascontiguousarray(a), cv2.COLOR_GRAY2BGR)

    def process(self, in_pdf, out_pdf, mode="skip", pages=None, sidecar=None, skip_text=None, txt=None, autorotate=False,
                chunk=8, pdfa=None):
        """OCR `in_pdf` into `out_pdf`. Returns a report; `sidecar` (path) also gets the per-page JSON of what was written.
        mode  skip  : pages that already contain any text are left alone (PDF24 default)
              redo  : old INVISIBLE text layers are stripped (pixel-identical page), then every page is OCR'd unless it
                      still shows >= VISIBLE_TEXT_MIN visible characters (born-digital)
              force : every page is OCR'd, existing text is kept
        txt        : also write the recognised text (Arjuna reading order, pages separated by form feeds) to this path
        autorotate : pages Arjuna had to turn by 90/180/270 to read get /Rotate so they DISPLAY upright (image untouched)
        chunk      : pages rendered + OCR'd at a time (bounds memory on long PDFs)
        pdfa       : e.g. "2b" / "2u" -> write PDF/A with pikepdf.pdfa (prepare + save + validate, no Ghostscript)
        skip_text  : deprecated alias (True -> skip, False -> force)."""
        if skip_text is not None: mode = "skip" if skip_text else "force"
        assert mode in MODES, mode
        t0 = time.time(); pk = pikepdf.open(str(in_pdf))
        report = {"input": str(in_pdf), "output": str(out_pdf), "lang": self.lang, "mode": mode, "pages": []}
        stripped = {}
        if mode == "redo":
            for i, page in enumerate(pk.pages):
                if pages and i + 1 not in pages: continue
                stripped[i] = strip_invisible_text(pk, page)
            buf = io.BytesIO(); pk.save(buf); data = buf.getvalue(); pk = pikepdf.open(io.BytesIO(data)); src = pdfium.PdfDocument(data)
        else:
            src = pdfium.PdfDocument(str(in_pdf))
        texts, todo, model = {}, [], None
        for i in range(len(src)):
            if pages and i + 1 not in pages: continue
            pg = src[i]; entry = {"page": i + 1}; report["pages"].append(entry)
            if i in stripped: entry["stripped_old_text_ops"] = stripped[i].get("removed_ops", 0)
            if mode == "skip" and page_has_text(pg):
                entry["skipped"] = "has_text"; continue
            if mode == "redo":
                tp = pg.get_textpage(); nvis = tp.count_chars(); tp.close()
                if nvis >= VISIBLE_TEXT_MIN:
                    entry["skipped"] = f"visible_text({nvis})"; continue
            cb = pg.get_cropbox(); rot = pg.get_rotation(); uu = float(pk.pages[i].obj.get("/UserUnit", 1.0))
            dpi = self.dpi or native_dpi(pk.pages[i], (cb[2] - cb[0]) if rot in (0, 180) else (cb[3] - cb[1])) or DPI_DEFAULT
            dpi = float(min(max(dpi, DPI_MIN), DPI_MAX))
            img = self._render(pg, dpi)
            entry.update(dpi=round(dpi, 1), cropbox=[round(v, 3) for v in cb], rotate=rot, user_unit=uu, raster=[img.shape[1], img.shape[0]])
            todo.append((i, img, entry))
            if len(todo) >= chunk:
                model = self._ocr_chunk(pk, todo, texts, autorotate) or model; todo = []
        if todo: model = self._ocr_chunk(pk, todo, texts, autorotate) or model
        pk.save(str(out_pdf), compress_streams=True, object_stream_mode=pikepdf.ObjectStreamMode.generate)
        if pdfa: report["pdfa"] = to_pdfa(out_pdf, pdfa)
        if txt:
            Path(txt).write_text("\f".join(texts.get(i, "") for i in range(len(src)) if not pages or i + 1 in pages), encoding="utf-8")
        report["seconds"] = round(time.time() - t0, 2); report["model"] = model
        if self._tap is not None: report["rec_frames_reused"] = {"hits": self._tap.hits, "misses": self._tap.misses}
        if sidecar: Path(sidecar).write_text(json.dumps(report, ensure_ascii=False, indent=1))
        return report

    def _ocr_chunk(self, pk, todo, texts, autorotate):
        """OCR a chunk of rendered pages and graft their text layers. Returns the model ids."""
        from collections import Counter
        docs = self.ocr.pages([img for _, img, _ in todo])
        for (i, img, entry), doc in zip(todo, docs):
            P = doc["page"]; texts[i] = doc.get("text", "")
            to_r = ArjunaToRaster(img.shape[1], img.shape[0], P.get("rotation", 0), P.get("deskew_deg", 0.0))
            to_p = RasterToPdf(entry["cropbox"], entry["rotate"], entry["dpi"] / 72.0)   # pdfium: CropBox, /Rotate applied
            raw = doc.pop("_raw", None)
            pw = W.page_words({"_raw": raw}, self.ocr.rec, self._crop) if (self.word_boxes and raw) else []
            self._why = Counter(); self._raw_quads = raw["quads"] if raw else []; self._dbg = []
            lines, written = [], []; n_ctc = n_prop = n_withheld = 0
            for b in doc["blocks"]:
                if b.get("text_suppressed") and not self.include_withheld:
                    n_withheld += len(b.get("lines", [])); continue
                for l in b.get("lines", []):
                    t = " ".join((l.get("text") or "").split())
                    if not t: continue
                    o, d, h, w = line_frame(l["bbox"], to_r, to_p)
                    words = self._line_words(l, t, pw, to_r, to_p, o, d)
                    if words: n_ctc += 1
                    else: n_prop += 1
                    lines.append(TextLine(origin=o, direction=d, height=h, width=w, text=t, words=words or []))
                    written.append({"text": t, "block": b.get("type"), "pdf_origin": [round(o[0], 2), round(o[1], 2)],
                                    "dir": [round(d[0], 4), round(d[1], 4)], "h": round(h, 2), "w": round(w, 2),
                                    "words": [[x.text, round(x.x0, 2), round(x.x1, 2)] for x in words] if words else None})
            page = pk.pages[i]
            graft(pk, page, text_form(pk, lines, [float(v) for v in page.mediabox]))
            arot = int(P.get("rotation", 0)) % 360
            if autorotate and arot:
                # Arjuna turned the raster `arot` degrees counter-clockwise to read it; /Rotate is clockwise
                page.obj.Rotate = (int(entry["rotate"]) - arot) % 360; entry["set_rotate"] = int(page.obj.Rotate)
            entry.update(lines=len(lines), lines_ctc_words=n_ctc, lines_proportional=n_prop, lines_withheld=n_withheld,
                         proportional_why=dict(self._why), arjuna_rotation=arot, deskew_deg=P.get("deskew_deg", 0.0), written=written,
                         **({"debug_mismatch": self._dbg} if getattr(self, "debug", False) else {}))
        if self._tap is not None: self._tap.clear()
        return docs[0].get("model") if docs else None

    def _line_words(self, line, text, pw, to_r, to_p, origin, direction):
        """Word boxes for one assembled line from the raw detector quads it was built from, as [Word] along the line's
        baseline in PDF points. None when the quads cannot be matched token-for-token (-> proportional fallback)."""
        if not pw: self._why["no_raw"] += 1; return None
        x0, y0, x1, y1 = line["bbox"]; hh = y1 - y0; mx = 0.25 * hh
        toks = text.split(); cand = []
        dec_bad = 0
        for qi, qtext, wq in pw:
            if wq is None:
                q = self._raw_quads[qi]; c = q.mean(0)
                if x0 - mx <= c[0] <= x1 + mx and y0 - mx <= c[1] <= y1 + mx: dec_bad += 1
                continue
            cx = float(np.mean([p[1][:, 0].mean() for p in wq])); cy = float(np.mean([p[1][:, 1].mean() for p in wq]))
            if x0 - mx <= cx <= x1 + mx and y0 - mx <= cy <= y1 + mx: cand.append((cx, wq))
        if dec_bad: self._why["decode_mismatch"] += 1; return None
        if not cand: self._why["no_quad_in_line"] += 1; return None
        # neighbouring quads (stamp fragments, a bracketed note beside the line) can sit inside the tolerance band:
        # keep only quads whose token run occurs in this line, then demand an exact token-for-token match
        padded = " " + " ".join(toks) + " "
        cand = [c for c in cand if (" " + " ".join(w for w, _ in c[1]) + " ") in padded]
        if not cand: self._why["no_quad_in_line"] += 1; return None
        cand.sort(key=lambda c: c[0]); got = [wd for _, wq in cand for wd in wq]
        if [g[0] for g in got] != toks:
            self._why["token_mismatch"] += 1
            if getattr(self, "debug", False): self._dbg.append({"line": text, "quads": " | ".join(" ".join(w for w, _ in wq) for _, wq in cand)})
            return None
        o = np.array(origin); dvec = np.array(direction); out = []
        for word, quad in got:
            pq = to_p(to_r(quad))            # TL TR BR BL in PDF space
            a = float(np.dot(pq[3] - o, dvec)); bb = float(np.dot(pq[2] - o, dvec))
            out.append(Word(word, min(a, bb), max(a, bb)))
        out.sort(key=lambda w: w.x0)
        return out
