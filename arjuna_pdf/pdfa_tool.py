"""PDF/A conversion in its OWN process: `pikepdf.pdfa` needs jsonschema >= 4.18, ocr_env ships an older one that shadows
ours (we append .deps last on purpose so ocr_env's packages win). Run with PYTHONPATH=<.deps> first:
    python -m arjuna_pdf.pdfa_tool in.pdf out.pdf 2b      -> prints a JSON report"""
import sys, json
import pikepdf, pikepdf.pdfa as PA

if __name__ == "__main__":
    src, dst, flavour = sys.argv[1:4]
    rep = PA.save(pikepdf.open(src), dst, flavour, compress_streams=True, object_stream_mode=pikepdf.ObjectStreamMode.generate)
    print(json.dumps({"flavour": flavour, "passed": bool(rep.passed),
                      "findings": [{"kind": str(f.kind), "rule": f.rule, "where": str(f.where), "message": f.message[:300]} for f in rep.findings][:50]}))
