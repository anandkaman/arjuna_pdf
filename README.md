# arjuna-pdf

Searchable PDFs from scanned **Kannada + English** and **Hindi + English** documents, using
[Arjuna-OCR](https://huggingface.co/anandkaman/arjuna-ocr-kn-en) for layout, detection and recognition.

The original page images are left untouched. arjuna-pdf only adds an invisible text layer on top of them, with each
word placed over its ink, so you can select, copy and search the Kannada and Devanagari text. This is the same kind of
output PDF24 Creator produces, but with Arjuna's models in place of Tesseract.

## Results

Measured on held-out, hand-labelled private documents. Text is extracted from each tool's output PDF.

| | words found | lines found verbatim |
|---|---|---|
| Kannada documents (39 pages, 1,629 lines) — PDF24 (Tesseract) | 78.8 % | 58.5 % |
| Kannada documents — **arjuna-pdf** | **98.5 %** | **95.1 %** |
| Hindi documents (43 pages, 382 lines) — PDF24 (Tesseract) | 86.8 % | 41.6 % |
| Hindi documents — **arjuna-pdf** | **98.4 %** | **88.2 %** |

- **Copy-paste correctness:** no corrupted characters in any of the five text extractors tested (pdfium/Chrome,
  pdf.js/Firefox, MuPDF, poppler, pdfminer).
- **Images:** byte-identical to the input on every test page.
- **Speed on an RTX 5060 Ti:** about 0.25 s per page for Kannada and 1.2 s per page for Hindi.

Details are in `research/09_m6_headtohead.md` and `research/07_m2_m4_results.md`. The PDF24 side was reproduced on Linux
with the same Tesseract version family, the same language models PDF24 downloads, and PDF24's OCR settings
(`scripts/pdf24_equiv.py`).

## Install

```bash
pip install -e .            # or: pip install -r requirements.txt
pip install -e ".[pdfa]"    # optional PDF/A output
```

The Arjuna models download automatically from Hugging Face on first use (about 230 MB per language, cached in
`~/.cache/huggingface`). Each pack is pinned to the exact commit arjuna-pdf was tested and benchmarked with:

| `--lang` | Hugging Face repo | release (tag = pinned commit) |
|---|---|---|
| `kn` (Kannada + English) | [anandkaman/arjuna-ocr-kn-en-inference](https://huggingface.co/anandkaman/arjuna-ocr-kn-en-inference) | `v1.3.3` = `1b7414a1`, layout v15 |
| `hi` (Hindi + English) | [anandkaman/arjuna-ocr-hi-en](https://huggingface.co/anandkaman/arjuna-ocr-hi-en) | `v1.1.3` = `072bc43e`, layout v15 |

Use `arjuna-ocr-kn-en-inference` for Kannada: the `arjuna-ocr-kn-en` card repo still holds the older v1.2.1 files.

Optional overrides:

```bash
export ARJUNA_KN_PKG=/path/to/local/pack      # use a local copy (kanen_infer/ + config + models/) instead of downloading
export ARJUNA_HI_REVISION=v1.1.1              # use another Hugging Face revision (tag, branch or commit)
```

The Hindi pack must be loaded with its own `arjuna_hi.yaml`, and arjuna-pdf does this for you. Before it OCRs
anything, it checks that the loaded recogniser can actually emit the requested script. Use one language per process.

## Use

```bash
arjuna-pdf scan.pdf -o scan_ocr.pdf --lang kn                 # Kannada + English
arjuna-pdf scan.pdf -o scan_ocr.pdf --lang hi --redo --txt scan.txt
```

| option | what it does |
|---|---|
| (default) | pages that already contain text are left alone (like PDF24) |
| `--redo` | strips an old **invisible** OCR layer (pixel-identical), then OCRs; pages with real visible text are skipped |
| `--force` | OCRs every page and keeps any existing text |
| `--txt FILE` | also writes the recognised text, with pages separated by form feeds |
| `--autorotate` | sets `/Rotate` so that pages Arjuna had to turn display upright (the image itself is not changed) |
| `--pdfa 1b\|2b\|3b` | writes PDF/A (pikepdf.pdfa, no Ghostscript) |
| `--include-withheld` | also writes lines that Arjuna withholds (suppressed seal/figure/handwriting blocks) |
| `--no-word-boxes` | spaces words evenly along the line instead of using the recogniser's CTC positions |
| `--providers cpu` | runs on CPU (see `engine.low_memory_cpu()` and `scripts/ocr_pagewise.py` for low-RAM runs) |

Python:

```python
from arjuna_pdf import ArjunaPDF
ArjunaPDF("kn").process("scan.pdf", "scan_ocr.pdf", mode="redo", txt="scan.txt")
```

## How it works

```
PDF -> render each page (pdfium, the scan's native DPI) -> Arjuna: layout -> detection -> recognition -> assembly
    -> word boxes from the recogniser's own CTC frames (no second pass)
    -> map coordinates back through Arjuna's rotate/deskew and the page's CropBox and /Rotate into PDF space
    -> invisible GlyphLessFont text: one glyph per code point, identity ToUnicode, per-word Tz stretch
    -> drawn as a foreground Form XObject on the original page
```

**Copying Kannada and Devanagari text.**

- **Whole words copy exactly.** That covers a double-click, search, select-all, or any selection that covers whole
  words. On a 12-page Kannada document, all 1,230 Kannada words copied back intact, including all 659 words with
  conjuncts. No PDF engine we tested produced a single corrupted character: pdfium/Chrome, pdf.js/Firefox, MuPDF,
  poppler and pdfminer.
- **Selecting part of a word can split a syllable.** In the same document, about half of all drag-selections that end
  in the middle of a word cut a syllable, for example `ಸಂಖ್ಯೆ` → `ಸಂಖ್` or `ಶುದ್ಧ` → `ಶುದ`. The invisible characters
  are spaced evenly across the word, not placed under each printed akshara. Kannada and Devanagari spell one visible
  syllable with several characters (`ಕ್ಷೇ` is four), so a selection edge inside a word can fall between them.
  Tesseract and PDF24 output behave the same way, because they use the same technique.

Why it is built this way: the invisible text writes each Unicode character as its own glyph, in the order the
recogniser produced it, with a one-to-one character mapping. Some other OCR tools instead draw the hidden text with a
real Kannada or Devanagari font and shape the conjuncts. That breaks copy-paste even for whole words. Test lines
written that way came back as `शि\x07क्षा`, `कि ताब` and `ಕರ್ನಾ ಟಕ` (`research/05_text_layer_survey.md`). That is
those tools' output, not arjuna-pdf's.

## Repository layout

| path | contents |
|---|---|
| `arjuna_pdf/` | the tool: `engine.py`, `textlayer.py` (writer), `geometry.py`, `words.py` (CTC word boxes), `pdftext.py` (redo), `cli.py` |
| `tests/` | `test_textlayer.py`, `test_geometry.py`, `test_strip.py` (fast, no OCR); `gate_m1.py`, `gate_m2.py`, `bench_m6.py` (need OCR outputs) |
| `scripts/` | PDF24-equivalent pipeline (`pdf24_equiv.py`), batch runners, page-wise CPU runner, A/B harness, drawing tools |
| `research/` | design (03), detector and text-layer surveys (04-05), milestone results (06-09) |

Not in git: test PDFs and benches (`data/`), outputs (`runs/`, `outputs/`), the PDF24 installer and its unpacked
files, the downloaded Tesseract models, and local dependency folders. The private registration and revenue records
used for the benchmarks never leave the machine.

## Tests

```bash
python tests/test_textlayer.py      # writer: 5 extractors, exact Kannada/Hindi/English round trip
python tests/test_geometry.py       # /Rotate, CropBox, UserUnit, Arjuna rotate/deskew inverse
python tests/test_strip.py <dir>    # redo mode on PDFs that carry old invisible OCR layers
```

## License

Apache-2.0 (see `LICENSE` and `NOTICE`). The bundled `arjuna_pdf/data/pdf.ttf` is Tesseract's GlyphLessFont
(Apache-2.0).
