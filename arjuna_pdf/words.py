"""Word boxes from the recogniser's CTC frames (M2).

Arjuna returns LINES. For a word-exact text layer we need where each word sits. Without touching the shipped package:
  1. `capture()` wraps `kanen_infer.batch_pipeline.assemble` for this process only, so every page document also carries
     the raw detector quads, their recognised texts and the final-frame image the recogniser read (`_raw`).
  2. `word_quads()` re-crops each quad exactly as the pipeline does (`pipeline_base.crop`), runs the SAME ONNX session
     with the same preprocessing, and decodes greedily while keeping the frame index of every emitted character.
     If the re-decoded string differs from the line text Arjuna returned (second-pass / 180° crops use other padding),
     the line is left to the proportional fallback -- never a guess presented as a measurement.
  3. Word extents run from the space frame before the word to the space frame after it, then shrink to the ink columns
     inside that span; the inverse of the crop's perspective warp maps them back onto the detector quad (final frame).
"""
import math, threading, hashlib
import numpy as np, cv2

_LOCK = threading.Lock()


class SessionTap:
    """Stands in for the recogniser's ONNX session: forwards every call and remembers, per input row, the argmax frame
    ids it produced, keyed by a hash of that exact input tensor. The word step rebuilds the bit-identical tensor for a
    crop and reads the frames from here -> no second recogniser pass, and words agree with Arjuna's own reading
    (including TensorRT fp16 numerics). A miss (e.g. the engine was swapped) falls back to running the session."""
    def __init__(self, inner):
        self.inner = inner; self.ids = {}; self.hits = 0; self.misses = 0; self._lk = threading.Lock()

    @staticmethod
    def key(row):
        return hashlib.blake2b(np.ascontiguousarray(row).tobytes(), digest_size=16).digest()

    def run(self, names, feeds, *a, **kw):
        out = self.inner.run(names, feeds, *a, **kw)
        x = feeds.get("image") if isinstance(feeds, dict) else None
        if x is not None and len(out) and getattr(out[0], "ndim", 0) == 3:
            ids = out[0].argmax(-1).astype(np.int16)
            with self._lk:
                for k in range(len(x)): self.ids[self.key(x[k])] = ids[k]
        return out

    def clear(self):
        with self._lk: self.ids.clear()

    def __getattr__(self, name):   # get_providers() etc. go to the real session
        return getattr(self.inner, name)


def tap(rec):
    """Install a SessionTap on rec.s (idempotent). Returns the tap."""
    if not isinstance(rec.s, SessionTap): rec.s = SessionTap(rec.s)
    return rec.s


def capture(bp_module):
    """Wrap batch_pipeline.assemble once; documents gain `_raw` = {img, quads, texts}. Idempotent."""
    if getattr(bp_module.assemble, "_arjuna_pdf_wrapped", False): return
    orig = bp_module.assemble

    def wrapped(w, h, blocks, boxes, texts, *a, **kw):
        quads = [np.asarray(b, np.float32).copy() for b, _ in boxes]
        tx = [t for t, _ in texts]
        d = orig(w, h, blocks, boxes, texts, *a, **kw)
        d["_raw"] = {"img": kw.get("img"), "quads": quads, "texts": tx}
        return d
    wrapped._arjuna_pdf_wrapped = True
    bp_module.assemble = wrapped


def _run(rec, x):
    """rec session on a batch; on an allocation failure halve the batch (never fail a page) -- same policy as the recogniser."""
    try:
        sess = rec.s.inner if isinstance(rec.s, SessionTap) else rec.s   # misses must not be re-recorded
        with _LOCK: return sess.run(None, {"image": x})[0]
    except Exception as e:
        if len(x) == 1 or ("memory" not in str(e).lower() and "alloc" not in str(e).lower()): raise
        h = len(x) // 2
        return np.concatenate([_run(rec, x[:h]), _run(rec, x[h:])], axis=0)


def _prep(gray, H, buckets, max_ratio):
    """Exactly KanEnRecognizer's per-crop preprocessing: (bucket width W, resized width nw, float image row)."""
    ratio = min(gray.shape[1] / max(gray.shape[0], 1), max_ratio)
    W = next((b for b in buckets if b >= int(math.ceil(ratio * H / 4) * 4)), buckets[-1])
    nw = min(W, max(8, int(round(gray.shape[1] * H / max(gray.shape[0], 1)))))
    r = cv2.resize(gray, (nw, H), interpolation=cv2.INTER_AREA if gray.shape[0] > H else cv2.INTER_CUBIC).astype(np.float32) / 255.0
    x = np.ones((3, H, W), np.float32); x[:, :, :nw] = (r - 0.5) / 0.5
    return W, nw, x


def decode_frames(rec, crops):
    """[(text, [(char, frame_x_in_crop_px)])] for crops, using the recogniser's own session; frame x = centre of the frame."""
    H = rec.H; buckets = list(rec.buckets); max_ratio = getattr(rec, "MAX_RATIO", 40)
    grays = [c if c.ndim == 2 else cv2.cvtColor(c, cv2.COLOR_BGR2GRAY) for c in crops]
    preps = [_prep(g, H, buckets, max_ratio) for g in grays]
    out = [None] * len(crops); groups = {}
    for i, (W, _, _) in enumerate(preps): groups.setdefault(W, []).append(i)
    tp = rec.s if isinstance(rec.s, SessionTap) else None
    for W, idx in groups.items():
        ids_of = {}
        if tp is not None:   # frames Arjuna's own recogniser call already produced for this exact tensor
            for i in idx:
                hit = tp.ids.get(SessionTap.key(preps[i][2]))
                if hit is not None: ids_of[i] = hit; tp.hits += 1
        todo = [i for i in idx if i not in ids_of]
        if tp is not None: tp.misses += len(todo)
        bs = max(1, min(16, int(16 * 320 // max(W, 64))))   # narrower batches for wide buckets, like the recogniser
        for s in range(0, len(todo), bs):
            part = todo[s:s + bs]; x = np.stack([preps[i][2] for i in part])
            probs = _run(rec, x)
            for k, i in enumerate(part): ids_of[i] = probs[k].argmax(-1)
        for i in idx:
            ids = ids_of[i]; T = len(ids); stride = W / T
            prev = 0; chars = []; nw = preps[i][1]; scale = grays[i].shape[1] / nw
            for t, c in enumerate(ids):
                if c != prev and c != 0: chars.append((rec.chars[c - 1], (t + 0.5) * stride * scale))
                prev = c
            out[i] = ("".join(c for c, _ in chars), chars)
    return out


def _ink_span(gray, x0, x1):
    """Tighten [x0, x1) to the columns that hold ink (Otsu on the crop); unchanged if none."""
    a, b = max(0, int(math.floor(x0))), min(gray.shape[1], int(math.ceil(x1)))
    if b - a < 2: return x0, x1
    _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    cols = (bw[:, a:b] > 0).sum(0) >= max(1, int(0.03 * gray.shape[0]))
    nz = np.flatnonzero(cols)
    return (a + nz[0], a + nz[-1] + 1) if nz.size else (x0, x1)


def word_quads(crop, quad, text, decoded):
    """Words of one detector quad -> [(word, quad4x2 in final frame)] or None when the decode disagrees with `text`.
    `crop` is the quad's crop exactly as the recogniser saw it (pipeline_base.crop)."""
    dtext, chars = decoded
    if " ".join(dtext.split()) != " ".join(text.split()) or not chars: return None
    gray = crop if crop.ndim == 2 else cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape[:2]
    # split emitted characters into words at space characters; remember the space frame positions as boundaries
    words, cur, bounds, last_space = [], [], [], 0.0
    for c, x in chars:
        if c == " ":
            if cur: words.append(cur); bounds.append([last_space, x]); cur = []
            last_space = x
        else:
            cur.append((c, x))
    if cur: words.append(cur); bounds.append([last_space, float(w)])
    if not words: return None
    Minv = np.linalg.inv(cv2.getPerspectiveTransform(quad.astype(np.float32), np.array([[0, 0], [w, 0], [w, h], [0, h]], np.float32)))
    out = []
    for wd, (L, R) in zip(words, bounds):
        x0, x1 = _ink_span(gray, L, R)
        pts = np.array([[x0, 0], [x1, 0], [x1, h], [x0, h]], np.float64)
        q = cv2.perspectiveTransform(pts[None].astype(np.float32), Minv.astype(np.float32))[0]
        out.append(("".join(c for c, _ in wd), q))
    return out


def page_words(doc, rec, crop_fn):
    """For one captured document: [(quad_index, text, [(word, quad)] or None)]."""
    raw = doc.get("_raw")
    if not raw or raw["img"] is None: return []
    img, quads, texts = raw["img"], raw["quads"], raw["texts"]
    keep = [i for i, t in enumerate(texts) if t and t.strip()]
    crops = [crop_fn(img, quads[i]) for i in keep]
    dec = decode_frames(rec, crops) if crops else []
    out = {i: word_quads(c, quads[i], texts[i], d) for i, c, d in zip(keep, crops, dec)}
    # lines Arjuna re-read in its confidence-gated second pass came from a taller crop (batch_pipeline: pad 0.06 / 0.08)
    retry = [i for i in keep if out[i] is None]
    if retry:
        pq = {i: _pad_quad(quads[i], SECOND_PASS_PAD) for i in retry}; pc = {i: crop_fn(img, pq[i]) for i in retry}
        for i, d in zip(retry, decode_frames(rec, [pc[i] for i in retry])):
            out[i] = word_quads(pc[i], pq[i], texts[i], d)
    return [(i, texts[i], out[i]) for i in keep]


SECOND_PASS_PAD = (0.06, 0.08)   # batch_pipeline._stage_b second pass: self._crops(..., pad=(0.06, 0.08))


def _pad_quad(b, pad):
    """Same vertical padding as BatchOCR._crops(pad=...)."""
    b = np.asarray(b, np.float32).copy(); hgt = 0.5 * ((b[3, 1] - b[0, 1]) + (b[2, 1] - b[1, 1]))
    b[0, 1] -= pad[0] * hgt; b[1, 1] -= pad[0] * hgt; b[2, 1] += pad[1] * hgt; b[3, 1] += pad[1] * hgt
    return b
