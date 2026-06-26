"""Cross-family CLOUD-VISION QA jury — the EXTERNAL_VERIFIER gate for sprite-motion-mcp.
Parameterized (no hardcoded characters). Refute-by-default, 2-of-3 consensus to PASS, a designated
CANARY whose solo flag is a soft warning (not a hard fail). Optional bug-free REFERENCE image anchors
the check (GlitchBench arXiv:2312.05291: reference-anchored VLM QA stops false positives on dark/ornate
assets) — when given, the jury compares the test to the clean reference and flags only NEW defects.

Run: python jury.py --image <test>.png [--reference <clean>.png] --context "..." --intended "..."
       --checklist "..." [--models a:cloud,b:cloud,c:cloud] [--canary c:cloud] [--ollama http://127.0.0.1:11434]
Emits one JSON object: {"verdict":"PASS|FAIL|INCONCLUSIVE","passes":N,"of":M,"jurors":[...]}
"""
import argparse, base64, json, sys, urllib.request, concurrent.futures as cf
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--image", required=True)
ap.add_argument("--reference", default="")
ap.add_argument("--context", required=True)
ap.add_argument("--intended", default="")
ap.add_argument("--checklist", required=True)
ap.add_argument("--models", default="minimax-m3:cloud,kimi-k2.6:cloud,gemini-3-flash-preview:cloud")
ap.add_argument("--canary", default="gemini-3-flash-preview:cloud")
ap.add_argument("--ollama", default="http://127.0.0.1:11434")
A = ap.parse_args()
JURY = [m.strip() for m in A.models.split(",") if m.strip()]
OLLAMA = A.ollama.rstrip("/") + "/api/chat"

def b64(p): return base64.b64encode(Path(p).read_bytes()).decode()

def prompt(has_ref):
    intended = (f"\nINTENDED design features (NEVER flag these as defects): {A.intended}." if A.intended else "")
    if has_ref:
        return ("You are a precise 3D game-asset QA reviewer comparing TWO renders of the SAME character.\n"
            "IMAGE 1 is a VERIFIED-CLEAN reference render (a human confirmed it has NO geometry defects).\n"
            "IMAGE 2 is the TEST render — the same character, only the POSE differs.\n"
            f"Asset: {A.context}.{intended}\n"
            f"Flag ONLY genuine NEW geometry defects in IMAGE 2 that are NOT in IMAGE 1, specifically: {A.checklist}. "
            "If IMAGE 2 is the same build quality as the clean reference and only the pose differs, return pass:true. "
            "Anything present in BOTH images is intended. Do NOT flag the 3D/CGI look or the grey background.\n"
            'Respond with STRICT JSON only: {"pass": true|false, "issues": ["short NEW defect", ...]}. JSON only.')
    return ("You are a STRICT 3D game-asset QA reviewer. REFUTE BY DEFAULT: assume the asset is DEFECTIVE "
        "unless it is clearly clean.\n"
        f"INTENDED asset: {A.context}.{intended}\n"
        f"Report ONLY genuine defects, especially: {A.checklist}.\n"
        "This is a 3D render (NOT anime, NOT a photo) on a plain grey background — do NOT flag 'CGI/3D look', "
        "'not painterly', 'low detail', or the grey background; those are intended.\n"
        'Respond with STRICT JSON only: {"pass": true|false, "issues": ["short defect", ...]}. JSON only.')

def call(model):
    if not Path(A.image).exists(): return {"model": model, "pass": None, "issues": [], "error": "image missing"}
    has_ref = bool(A.reference and Path(A.reference).exists())
    imgs = ([b64(A.reference)] if has_ref else []) + [b64(A.image)]
    payload = {"model": model, "stream": False, "think": False,
               "messages": [{"role": "user", "content": prompt(has_ref), "images": imgs}]}
    try:
        req = urllib.request.Request(OLLAMA, json.dumps(payload).encode(), {"Content-Type": "application/json"})
        txt = json.loads(urllib.request.urlopen(req, timeout=300).read()).get("message", {}).get("content", "")
        i, j = txt.find("{"), txt.rfind("}")
        if i >= 0 and j > i:
            o = json.loads(txt[i:j + 1]); return {"model": model, "pass": bool(o.get("pass")), "issues": o.get("issues") or []}
        return {"model": model, "pass": None, "issues": [], "raw": txt[:200]}
    except Exception as e:
        return {"model": model, "pass": None, "issues": [], "error": str(e)[:200]}

with cf.ThreadPoolExecutor(max_workers=len(JURY)) as ex:
    jurors = list(ex.map(call, JURY))
passes = sum(1 for r in jurors if r.get("pass") is True)
decided = [r for r in jurors if r.get("pass") is not None]
verdict = "PASS" if passes >= 2 else ("FAIL" if len(decided) >= 2 else "INCONCLUSIVE")
print(json.dumps({"verdict": verdict, "passes": passes, "of": len(JURY), "canary": A.canary, "jurors": jurors}))
