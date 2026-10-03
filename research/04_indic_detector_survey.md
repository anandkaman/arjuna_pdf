# 04 — Indic-capable text detectors: survey (sub-agent web research, 2026-10-03)

Verdict: **no public, commercially usable detector trained on PRINTED Kannada/Devanagari pages exists**
(verified ones with Indic data are scene text or handwriting). Keep our PP-OCRv6-det fine-tune (v1.2.1,
self-distilled); fix clipping via label definition + vertical unclip / connected-component snap.

## Shortlist
1. PP-OCRv6 det (Apache-2.0, ONNX) — ours already; PP-OCRv5 has Indic REC only, no Indic det.
2. Kraken BLLA / Orli (Apache-2.0) — baseline+boundary formulation suits matras/vattus; Latin/Malayalam
   training, no ONNX; known Devanagari failures (Shreeshrii/kraken_devanagari). Fine-tune only.
3. docTR DB/LinkNet (+OnnxTR) and PLATTER (arXiv 2502.06172) — DBNet on CHIPS (25k handwritten pages,
   10 Indic scripts incl. kn+hi); checkpoint NOT located.
4. IndicPhotoOCR TextBPN++ (MIT code, weights licence unstated) — BSTD scene text (kn, hi); F1 0.77 vs DBNet 0.59.
   Worth a by-eye matra-coverage test on our pages.
5. Surya det — "any language" lines+polygons; weights OpenRAIL-M restricted (>$5M) → A/B reference only.

Rejected/flagged: TEXTRON (GPL-3.0), HF YOLO line detectors (Ultralytics AGPL), Hi-SAM (slow, no Indic),
CRAFT (F1 0.19 on BSTD), MMOCR (dormant), Bodhan IndicDocLayout (block-level only, own licence),
Sarvam/Krutrim (no detector published).

## Datasets
CHIPS (handwritten Indic pages, word boxes), BSTD (scene, 11 Indic, CC-BY-SA images, ~17 GB),
TEXTRON_INDIC (GPL), Mozhi (crops only), MLT-2019 / IIIT-ILST (research-only). No public printed-Kannada
page set with line polygons found → our 539 relabelled pages + synthetic pages remain the best source.

## Model-independent clipping fixes
1. GT box = rendered ink union (both bands), not font metrics.  2. Vertical-only unclip (k·x-height).
3. Connected-component snap of each box in y (capped ~0.6 h; shared marks → nearer baseline).
4. Baseline+boundary representation.  5. Recognizer trained with random ±15-25 % vertical padding.
No source gives evidence on matra/conjunct coverage for ANY model — must be measured on our pages
(dropped above/below-mark count on identical pixels, at scale).

Sources: PaddleOCR PP-OCRv6 blog + PP-OCRv5 multi-language docs, datalab-to/surya, python-doctr,
arXiv 2502.06172, Bhashini-IITJ/IndicPhotoOCR + BharatSceneTextDataset, arXiv 2511.23071,
zenodo 14602569 / 20558179, Shreeshrii/kraken_devanagari, ymy-k/Hi-SAM, JaidedAI/EasyOCR,
IITB-LEAP-OCR/TEXTRON, cvit usodi, Bodhan blog, Sarvam Vision 2.1 blog.
