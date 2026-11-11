"""Run one LLM test system on one source condition and one claims CSV.

Used for the main LLM runs, the retrieval (E3), prompt-variant (E4) and edit-set (E5) runs, and the cost test.
Every raw response is cached under runs/<run_id>/raw/<claim_id>.json, so a re-run resumes from the cache;
predictions go to runs/<run_id>/predictions.csv.

Systems:
  haiku, sonnet       : Anthropic API through the Python SDK (claude-haiku-5-5, claude-sonnet-5-5).
                        system = [instructions + label definitions] + [source], both with cache_control ephemeral (5 min);
                        the claim is in the user turn; streaming + get_final_message; no temperature (not accepted,
                        prereg D6); output_config.effort set explicitly (CLAUDE_EFFORT). Claims of one announcement run
                        consecutively in one worker so that later claims read the cache. Logged per call: model id,
                        stop_reason, effort, uncached input / cache read / cache write / output tokens and cost.
                        stop_reason "refusal" is logged and the prediction is REFUSED (no fallback model, no retry).
                        ANTHROPIC_API_KEY is read from .env in the repository root, in memory only.
  opus                : `claude -p --model opus --output-format json` (cost test only; not a test system)
  gpt55, gpt54mini    : OpenAI Responses API (plain HTTPS); OPENAI_API_KEY read from .env in the repository root
  qwen                : mlx-community/Qwen2.5-7B-Instruct-4bit via mlx-lm, local, greedy decoding
Conditions:
  C0 : no source (claim only)
  C1 : press release only
  C2 : press release + full decision text; where there is no full text, C2 is byte-identical to C1
  Main study (--src-root data/sources): <src_root>/<ann_id>/T1.txt (press release) and T2.txt (full text, may be empty).
  Where meta.json has t1_is_act = 1, T1 already holds the act, so C2 = C1 (prereg D3).
  Dev (default --src-root = pilot announcements): the files of <src_root>/<ann_id>/ as the pilot read them, and
  <src_root>/<ann_id>-DEC/ as the full text.

Prompt: --prompt prompts/<file>.txt (main study: prompts/main.txt; E4 variants: prompts/e4_v*.txt; header lines
"#! key: value" set source_placement system|user and output). With --prompt, every LLM system gets the same request
content (build_claude_request): instruction block = the prompt text (+ the C0 note in C0), source block =
<A> press release [+ full text] </A>, user turn = "CLAIM (from a news report): ...". Placement per backend:
  haiku/sonnet : system = [instructions (cached), source (cached)], user = claim (source_placement user: the source is a
                 cached first block of the user turn);
  gpt55        : Responses API `instructions` = instructions + "\n\n" + source, `input` = claim (the shared prefix is
                 cached automatically; prompt_cache_key = announcement|condition|prompt hash keeps the claims of one
                 announcement together);
  qwen         : chat template, system message = instructions + "\n\n" + source, user message = claim; the source is cut
                 to 20,000 characters by the pilot overlap retrieval (claim-specific; logged as truncated); max 16 new tokens.
  All --prompt runs parse strictly (a LABEL: line, else a last line starting with a label); invalid outputs are retried once.
Without --prompt (dev and cost test only): the pilot prompt adapted to the 5 labels (ASK below) for the systems other
than the Claude API ones, with the loose pilot parse.
E3: --retrieval FILE --k K replaces the source block by the top-K retrieved passages of the C2 source (FILE from
scripts/e3_retrieve.py), in document order.

Usage:
  python scripts/run_llm.py run --system haiku --condition C1 [--claims CSV] [--limit N] [--workers 4] [--run-id ID]
        [--prompt prompts/main.txt] [--src-root data/sources] [--effort low] [--max-chars N] [--cost-cap USD] [--dry-run]
  python scripts/run_llm.py summarize --out runs/dev_choice/cost_test.csv RUN_ID [RUN_ID ...]
The claims CSV needs claim_id, ann_id, claim_text; gold_label is optional (used for scoring).
Default claims: the 155 pilot dev claims (../pilot/adjudication/gold_labels.csv; labels SUPPORTED/CONTRADICTED/
NOT_ADDRESSED, training pair CBAR-5573 excluded, NOT_ADDRESSED mapped to NOT_IN_SOURCE).
"""
import tempfile
import argparse, concurrent.futures as cf, csv, glob, hashlib, json, math, os, re, subprocess, sys, threading, time, urllib.request, urllib.error
from collections import Counter

MAIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PILOT = os.path.join(os.path.dirname(MAIN), "pilot")
LABELS = ["SUPPORTED", "CONTRADICTED", "MISREPRESENTED", "NOT_IN_SOURCE", "UNASSESSABLE"]
BOILER = ("gov.az domeni", "Güvənilir vebsayt", "URL çubuğunda", "Dili seçin", "Axtar")

CLAUDE_MODELS = {"opus": "opus"}  # `claude -p` path (cost test only)
CLAUDE_API_MODELS = {"haiku": "claude-haiku-5-5", "sonnet": "claude-sonnet-5-5"}
# Effort, set explicitly (Haiku 5.5's default is medium, Sonnet 5.5's is high): low for Haiku, medium for Sonnet, since
# one-label classification needs little thinking. Recorded per call; override with --effort.
CLAUDE_EFFORT = {"haiku": "low", "sonnet": "medium"}
CLAUDE_MAX_TOKENS = 8000  # covers adaptive thinking + a one-line answer
# USD per 1M tokens: (input, output, cache read, cache write 5 min), from the Anthropic pricing table as of 2026-10-06.
# Haiku 5.5 has two cards chosen by prompt length (input + cache read + cache write tokens):
# <= 100K tokens $0.10/$0.50 (cache read $0.01, write $0.125); > 100K $0.50/$2.50 (cache read 0.1x = $0.05, write 1.25x =
# $0.625; the cache multipliers for the long card are derived from the documented 0.1x/1.25x rule, not quoted).
CLAUDE_PRICE = {"claude-haiku-5-5": [(100_000, (0.10, 0.50, 0.01, 0.125)), (float("inf"), (0.50, 2.50, 0.05, 0.625))],
                "claude-sonnet-5-5": [(float("inf"), (2.00, 10.00, 0.20, 2.50))]}
GUIDE_PATH = os.path.join(MAIN, "annotation", "guidelines_v1.2.md")
OPENAI_MODELS = {"gpt55": "gpt-5.5-2026-04-23", "gpt54mini": "gpt-5.4-mini-2026-03-17"}
# USD per 1M tokens (input, cached input, output), standard tier, short context (<=272K input).
# Source: https://developers.openai.com/api/docs/pricing, as of 2026-11-09.
OPENAI_PRICE = {"gpt-5.5-2026-04-23": (5.00, 0.50, 30.00), "gpt-5.4-mini-2026-03-17": (0.75, 0.075, 4.50)}
OPENAI_EFFORT = "low"   # lowest reasoning effort used in the cost test; recorded per call
QWEN_REPO = "mlx-community/Qwen2.5-7B-Instruct-4bit"
# Source caps (characters). Longer sources are cut to the best-matching lines (pilot overlap retrieval), logged.
MAX_CHARS = {"qwen": 20000}
QWEN_MAX_NEW = 16  # "LABEL: NOT_IN_SOURCE" is about 8 tokens
DEFAULT_MAX_CHARS = 400000  # no main-study source (max T1+T2 about 160k chars) is cut for API models (prereg section 5: cut only beyond the context)

ASK = ("Label the CLAIM against the official text with one of: "
       "SUPPORTED (the official text states it), "
       "CONTRADICTED (the claim and the official text cannot both be true), "
       "MISREPRESENTED (the official text addresses the point; the claim is not strictly incompatible with it, but gives a wrong picture "
       "of it: status or certainty upgraded, scope widened or narrowed, consequence misread, or a condition dropped), "
       "NOT_IN_SOURCE (the official text does not settle it and the claim does not distort it), "
       "UNASSESSABLE (too vague to check, or a question). Answer with one word.")


# Data
def src_lines(folder):
    out = []
    for f in sorted(glob.glob(f"{folder}/text_*.txt")) + sorted(glob.glob(f"{folder}/tables_*.txt")):
        out += [l.strip() for l in open(f, encoding="utf-8") if l.strip() and not any(b in l for b in BOILER)]
    return out


def toks(s):
    return set(re.findall(r"\w+", s.lower()))


def cut(lines, claim, max_chars):
    """Keep the best-matching lines (pilot overlap score) up to max_chars, in document order."""
    text = "\n".join(lines)
    if len(text) <= max_chars:
        return text, False
    q = toks(claim)
    order = sorted(range(len(lines)), key=lambda i: -len(q & toks(lines[i])) / math.sqrt(1 + len(toks(lines[i]))))
    keep, n = set(), 0
    for i in order:
        if n + len(lines[i]) + 1 > max_chars:
            continue
        keep.add(i); n += len(lines[i]) + 1
    return "\n".join(lines[i] for i in sorted(keep)), True


def load_claims(path):
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    if os.path.abspath(path) == os.path.abspath(os.path.join(PILOT, "adjudication/gold_labels.csv")):
        rows = [r for r in rows if r["gold_label"] in ("SUPPORTED", "CONTRADICTED", "NOT_ADDRESSED") and r["ann_id"] != "CBAR-5573"]
    for r in rows:
        if r.get("gold_label") == "NOT_ADDRESSED":
            r["gold_label"] = "NOT_IN_SOURCE"
    return rows


def file_lines(path):
    return [l.strip() for l in open(path, encoding="utf-8") if l.strip()] if os.path.exists(path) else []


def source_lines(claim, cond, src_root):
    """(press-release lines, full-text lines) for C1/C2. Main study: <src_root>/<ann_id>/T1.txt and T2.txt.
    Dev: the pilot announcement folder and its -DEC folder. The full text is returned only in C2."""
    folder = os.path.join(src_root, claim["ann_id"])
    if os.path.exists(os.path.join(folder, "T1.txt")):
        t1, t2 = file_lines(os.path.join(folder, "T1.txt")), file_lines(os.path.join(folder, "T2.txt"))
        mp = os.path.join(folder, "meta.json")
        if t2 and os.path.exists(mp) and json.load(open(mp, encoding="utf-8")).get("t1_is_act") == 1:
            t2 = []  # prereg D3: T1 is the full act, so C2 = C1
    else:
        dec = folder + "-DEC"
        t1, t2 = src_lines(folder), (src_lines(dec) if os.path.isdir(dec) else [])
    if not t1:
        raise SystemExit(f"no source text for {claim['ann_id']} under {src_root}")
    return t1, (t2 if cond == "C2" else [])


def load_prompt(path):
    """E4 prompt file: '#! key: value' header lines, then the instruction text ({GUIDELINES} = frozen guidelines v1.2)."""
    opts, body = {"source_placement": "system", "output": "label"}, []
    for l in open(path, encoding="utf-8"):
        if l.startswith("#! "):
            k, v = l[3:].split(":", 1); opts[k.strip()] = v.strip()
        else:
            body.append(l)
    text = "".join(body).strip()
    if "{GUIDELINES}" in text:
        text = text.replace("{GUIDELINES}", open(GUIDE_PATH, encoding="utf-8").read().strip())
    assert opts["source_placement"] in ("system", "user"), opts
    return {"path": os.path.relpath(path, MAIN), "text": text, **opts}


C0_NOTE = "You do not have the official text A; judge from your knowledge only."


BUILDER_VERSION = "main-2026-11-09 (D3 t1_is_act; all systems --prompt)"
RETRIEVED = {}  # E3: claim_id -> passages (best first) from scripts/e3_retrieve.py
RETR_K = 0


def build_claude_request(claim, cond, src_root, max_chars, prompt):
    """Anthropic request parts. Block 1 (cached) = instructions + label definitions; block 2 (cached) = the source A;
    user turn = the claim. Block 2 sits in the system prompt, or (source_placement user) as a cached first block of the user turn.
    Both blocks depend only on (prompt, announcement, condition), so all claims of one announcement share the cached prefix,
    unless the source had to be cut (claim-specific retrieval; logged as truncated)."""
    instr = prompt["text"] if prompt else ASK
    claim_txt = f"CLAIM (from a news report): {claim['claim_text']}"  # the claim's text part (headline/lead/body) is not shown
    if cond == "C0":
        system = [{"type": "text", "text": f"{instr}\n\n{C0_NOTE}", "cache_control": {"type": "ephemeral"}}]
        return {"system": system, "messages": [{"role": "user", "content": claim_txt}]}, False, 0
    t1, t2 = source_lines(claim, cond, src_root)
    full = len("\n".join(t1 + t2))
    trunc = False
    if RETR_K:  # E3: top-k retrieved passages of the C2 source instead of the whole text (claim-specific)
        ps = RETRIEVED[claim["claim_id"]]
        top = sorted(ps[:RETR_K], key=lambda x: x["idx"])  # document order
        body = "\n".join(f"[{i + 1}] {x['text']}" for i, x in enumerate(top))
        src = f"<A id=\"{claim['ann_id']}\">\n<retrieved_passages k=\"{RETR_K}\">\n{body}\n</retrieved_passages>\n</A>"
        t1txt = t2txt = None
    elif full > max_chars and t2 and len("\n".join(t1)) < max_chars:  # keep the press release whole; cut the full text
        t2txt, trunc = cut(t2, claim["claim_text"], max_chars - len("\n".join(t1)) - 1)
        t1txt = "\n".join(t1)
    elif full > max_chars:  # the press release alone fills the cap: cut press release (+ full text) together
        t1txt, trunc = cut(t1 + t2, claim["claim_text"], max_chars)
        t2txt = ""
    else:
        t1txt, t2txt = "\n".join(t1), "\n".join(t2)
    if t1txt is not None:
        src = f"<A id=\"{claim['ann_id']}\">\n<press_release>\n{t1txt}\n</press_release>\n"
        if t2txt:
            src += f"<full_decision_text>\n{t2txt}\n</full_decision_text>\n"
        src += "</A>"
    b1 = {"type": "text", "text": instr, "cache_control": {"type": "ephemeral"}}
    b2 = {"type": "text", "text": src, "cache_control": {"type": "ephemeral"}}
    if prompt and prompt["source_placement"] == "user":
        req = {"system": [b1], "messages": [{"role": "user", "content": [b2, {"type": "text", "text": claim_txt}]}]}
    else:
        req = {"system": [b1, b2], "messages": [{"role": "user", "content": claim_txt}]}
    return req, trunc, full


def flat_request(req):
    """(instructions text, claim text) of a build_claude_request request, for the OpenAI and Qwen backends: the system
    blocks (and a source block placed in the user turn) joined with a blank line, in the same order."""
    sysblocks = [b["text"] for b in req["system"]]
    content = req["messages"][0]["content"]
    if isinstance(content, list):
        sysblocks += [b["text"] for b in content[:-1]]
        content = content[-1]["text"]
    return "\n\n".join(sysblocks), content


def build_prompt(claim, cond, src_root, max_chars):
    c = claim["claim_text"]
    if cond == "C0":
        return (f"{ASK}\nYou do not have the official text; judge from your knowledge only.\n\nCLAIM (from a news report): {c}"), False, 0
    t1, t2 = source_lines(claim, cond, src_root)
    lines = list(t1)
    if t2:
        lines += ["", "FULL DECISION TEXT:"] + t2
    text, trunc = cut(lines, c, max_chars)
    return f"{ASK}\n\nOFFICIAL TEXT:\n{text}\n\nCLAIM: {c}", trunc, len("\n".join(lines))


def parse_label(text, strict=False):
    """Return the label of a model answer, or None if invalid.

    strict (Claude API runs and all --prompt runs): the last 'LABEL: X' line, else the last non-empty line if it starts
    with a label (a bare 'SUPPORTED', or 'SUPPORTED: reason'); anything else is invalid (retried once).
    Not strict (other runs without --prompt): the pilot rule, first label anywhere in the text."""
    t = (text or "").upper().replace("NOT IN SOURCE", "NOT_IN_SOURCE").replace("NOT_ADDRESSED", "NOT_IN_SOURCE")
    if strict:
        # Matching is case-insensitive, but a second label counts only in upper case (LABEL tokens), so a reason such as
        # "neither supported nor contradicted" does not make the answer ambiguous.
        o = (text or "").replace("NOT_ADDRESSED", "NOT_IN_SOURCE")
        lab = "|".join(LABELS).replace("NOT_IN_SOURCE", "NOT[_ ]IN[_ ]SOURCE")
        other = lambda first, rest: bool({x.replace(" ", "_") for x in re.findall(r"\b(" + lab + r")\b", rest)} - {first})
        tagged = []
        for l in o.splitlines():
            m = re.match(r"(?i)\s*[*`#>\- ]*LABEL\s*:\s*\**\s*(" + lab + r")\b(.*)$", l)
            if m:
                tagged.append(None if other(m.group(1).upper().replace(" ", "_"), m.group(2)) else m.group(1).upper().replace(" ", "_"))
        if tagged:
            return tagged[-1]
        last = [l.strip(" *`#.-") for l in o.splitlines() if l.strip(" *`#.-")]
        if last and last[0].upper().replace(" ", "_") in LABELS:  # a first line that is exactly one label (Haiku 5.5 sometimes
            return last[0].upper().replace(" ", "_")  # appends an echo such as '<A id="...">' on later lines)
        m = re.match(r"(?i)(" + lab + r")\b(.*)$", last[-1]) if last else None
        if not m or other(m.group(1).upper().replace(" ", "_"), m.group(2)):
            return None
        return m.group(1).upper().replace(" ", "_")
    hits = [(m.start(), m.group(0)) for m in re.finditer("|".join(LABELS), t)]
    return min(hits)[1] if hits else None


# Backends
SRC_IN_SYSTEM = False  # --source-in-system: instructions + source go to --append-system-prompt, claim alone in the user turn


def call_claude(model, prompt):
    t0 = time.time()
    extra = []
    if SRC_IN_SYSTEM and "\n\nCLAIM: " in prompt:
        head, claim = prompt.rsplit("\n\nCLAIM: ", 1)
        extra, prompt = ["--append-system-prompt", head], "CLAIM: " + claim
    r = subprocess.run(["claude", "-p", "--model", model, "--output-format", "json", "--strict-mcp-config",
                        "--setting-sources", "project", "--no-session-persistence", "--tools", ""] + extra,
                       input=prompt, capture_output=True, text=True, timeout=600, cwd=tempfile.gettempdir())
    try:
        j = json.loads(r.stdout)
    except json.JSONDecodeError:
        return {"text": "", "error": (r.stderr or r.stdout)[-500:], "seconds": time.time() - t0, "in_tok": 0, "out_tok": 0, "cost": 0.0}
    u = j.get("usage", {})
    mu = j.get("modelUsage", {})
    return {"text": j.get("result", ""), "seconds": j.get("duration_ms", 0) / 1000,
            "in_tok": u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0) + u.get("cache_read_input_tokens", 0),
            "cached_tok": u.get("cache_read_input_tokens", 0), "out_tok": u.get("output_tokens", 0),
            "cost": j.get("total_cost_usd", 0.0), "model_id": ",".join(mu) if mu else model, "is_error": j.get("is_error"), "raw": j}


_KEYS = {}


def env_key(name):
    """Read one key from .env in the repository root into memory (never printed, logged or written)."""
    if name not in _KEYS:
        for l in open(os.path.join(MAIN, ".env"), encoding="utf-8"):
            if l.strip().startswith(name + "="):
                _KEYS[name] = l.split("=", 1)[1].strip().strip('"').strip("'")
        if not _KEYS.get(name):
            raise SystemExit(f"{name} not found in .env")
    return _KEYS[name]


def openai_key():
    return env_key("OPENAI_API_KEY")


_ANTH, _ANTH_LOCK = None, threading.Lock()
CLAUDE_EFFORT_RUN = {}  # system -> effort for this run (CLAUDE_EFFORT or --effort)


def anthropic_client():
    global _ANTH
    with _ANTH_LOCK:
        if _ANTH is None:
            import anthropic
            _ANTH = anthropic.Anthropic(api_key=env_key("ANTHROPIC_API_KEY"), max_retries=4, timeout=600)
    return _ANTH


def claude_cost(model, uncached, out, cache_read, cache_write):
    total_prompt = uncached + cache_read + cache_write
    pi, po, pr, pw = next(p for lim, p in CLAUDE_PRICE[model] if total_prompt <= lim)
    return (uncached * pi + out * po + cache_read * pr + cache_write * pw) / 1e6


def call_claude_api(system, req):
    import anthropic
    model, effort = CLAUDE_API_MODELS[system], CLAUDE_EFFORT_RUN.get(system, CLAUDE_EFFORT[system])
    t0 = time.time()
    try:
        with anthropic_client().messages.stream(model=model, max_tokens=CLAUDE_MAX_TOKENS, output_config={"effort": effort},
                                                system=req["system"], messages=req["messages"]) as st:
            m = st.get_final_message()
    except anthropic.APIError as e:  # after the SDK's own retries; the claim is not cached, so a re-run retries it
        msg = str(getattr(e, "message", e)).replace(env_key("ANTHROPIC_API_KEY"), "<redacted>")
        return {"text": "", "error": f"{type(e).__name__}: {msg[:300]}", "seconds": time.time() - t0,
                "in_tok": 0, "out_tok": 0, "cost": 0.0, "model_id": model, "effort": effort}
    u = m.usage
    unc, cr, cw, ot = u.input_tokens or 0, u.cache_read_input_tokens or 0, u.cache_creation_input_tokens or 0, u.output_tokens or 0
    refused = m.stop_reason == "refusal"
    sd = getattr(m, "stop_details", None)
    sd = sd.model_dump(mode="json") if hasattr(sd, "model_dump") else sd
    if refused:
        print(f"REFUSAL {model} category={(sd or {}).get('category')}", file=sys.stderr, flush=True)
    return {"text": "" if refused else "".join(b.text for b in m.content if b.type == "text"),
            "seconds": time.time() - t0, "in_tok": unc + cr + cw, "uncached_in_tok": unc, "cached_tok": cr, "cache_write_tok": cw,
            "out_tok": ot, "cost": claude_cost(model, unc, ot, cr, cw), "model_id": m.model, "effort": effort,
            "stop_reason": m.stop_reason, "stop_details": sd, "refused": refused,
            "raw": {"id": m.id, "model": m.model, "stop_reason": m.stop_reason, "stop_details": sd, "usage": u.model_dump(mode="json")}}


def call_openai(model, prompt, cache_key=None):
    if isinstance(prompt, dict):  # --prompt runs: instructions + source as `instructions` (cached prefix), claim as `input`
        instr, user = flat_request(prompt)
        body = {"model": model, "instructions": instr, "input": user, "reasoning": {"effort": OPENAI_EFFORT}, "max_output_tokens": 4000}
        if cache_key:
            body["prompt_cache_key"] = cache_key
    else:
        body = {"model": model, "input": prompt, "reasoning": {"effort": OPENAI_EFFORT}, "max_output_tokens": 4000}
    t0 = time.time()
    for attempt in range(4):
        req = urllib.request.Request("https://api.openai.com/v1/responses", data=json.dumps(body).encode(),
                                     headers={"Authorization": "Bearer " + openai_key(), "Content-Type": "application/json"})
        try:
            j = json.load(urllib.request.urlopen(req, timeout=300))
            break
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace").replace(openai_key(), "<redacted>")[:500]
            if e.code in (429, 500, 502, 503, 504) and attempt < 3:
                time.sleep(5 * (attempt + 1)); continue
            return {"text": "", "error": f"HTTP {e.code}: {msg}", "seconds": time.time() - t0, "in_tok": 0, "out_tok": 0, "cost": 0.0}
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:  # timeouts / resets: retry
            if attempt < 3:
                time.sleep(10 * (attempt + 1)); continue
            return {"text": "", "error": f"{type(e).__name__}: {str(e).replace(openai_key(), '<redacted>')[:300]}", "seconds": time.time() - t0, "in_tok": 0, "out_tok": 0, "cost": 0.0}
    parts = [c for o in j.get("output", []) if o.get("type") == "message" for c in o.get("content", [])]
    refused = any(c.get("type") == "refusal" for c in parts)
    text = "" if refused else "".join(c.get("text", "") for c in parts if c.get("type") == "output_text")
    u = j.get("usage", {})
    it, ot = u.get("input_tokens", 0), u.get("output_tokens", 0)
    ct = (u.get("input_tokens_details") or {}).get("cached_tokens", 0)
    pi, pc, po = OPENAI_PRICE[model]
    cost = ((it - ct) * pi + ct * pc + ot * po) / 1e6
    if refused:
        print(f"REFUSAL {model}", file=sys.stderr, flush=True)
    return {"text": text, "seconds": time.time() - t0, "in_tok": it, "cached_tok": ct, "uncached_in_tok": it - ct, "out_tok": ot,
            "reasoning_tok": (u.get("output_tokens_details") or {}).get("reasoning_tokens", 0),
            "cost": cost, "model_id": j.get("model", model), "effort": OPENAI_EFFORT, "refused": refused,
            "stop_reason": j.get("status", "") + (":" + str((j.get("incomplete_details") or {}).get("reason")) if j.get("incomplete_details") else ""),
            "raw": j}


_QWEN = None


def call_qwen(prompt):
    global _QWEN
    from mlx_lm import load, generate
    from mlx_lm.sample_utils import make_sampler
    if _QWEN is None:
        _QWEN = load(QWEN_REPO)
    m, tok = _QWEN
    if isinstance(prompt, dict):  # --prompt runs: system = instructions + source, user = claim
        instr, user = flat_request(prompt)
        msgs, mx = [{"role": "system", "content": instr}, {"role": "user", "content": user}], QWEN_MAX_NEW
    else:
        msgs, mx = [{"role": "user", "content": prompt}], 12
    p = tok.apply_chat_template(msgs, add_generation_prompt=True, tokenize=False)
    n_in = len(tok.encode(p))
    t0 = time.time()
    out = generate(m, tok, prompt=p, max_tokens=mx, sampler=make_sampler(temp=0.0))
    return {"text": out, "seconds": time.time() - t0, "in_tok": n_in, "out_tok": len(tok.encode(out)), "cost": 0.0, "model_id": QWEN_REPO}


def call(system, prompt, cache_key=None):
    if system in CLAUDE_API_MODELS:
        return call_claude_api(system, prompt)
    if system in CLAUDE_MODELS:
        return call_claude(CLAUDE_MODELS[system], prompt)
    if system in OPENAI_MODELS:
        return call_openai(OPENAI_MODELS[system], prompt, cache_key)
    if system == "qwen":
        return call_qwen(prompt)
    raise SystemExit(f"unknown system {system}")


# Run
def run(a):
    global SRC_IN_SYSTEM
    SRC_IN_SYSTEM = a.source_in_system
    claims = load_claims(a.claims)[: a.limit or None]
    run_id = a.run_id or f"{a.system}_{a.condition}"
    rdir = os.path.join(MAIN, "runs", run_id); os.makedirs(os.path.join(rdir, "raw"), exist_ok=True)
    max_chars = a.max_chars or MAX_CHARS.get(a.system, DEFAULT_MAX_CHARS)
    api = a.system in CLAUDE_API_MODELS
    prompt_spec = load_prompt(os.path.join(MAIN, a.prompt) if not os.path.isabs(a.prompt) else a.prompt) if a.prompt else None
    if prompt_spec and a.system in CLAUDE_MODELS:
        raise SystemExit("--prompt is not implemented for the claude -p (opus) path")
    if prompt_spec and prompt_spec["source_placement"] == "user" and not api:
        raise SystemExit("source_placement user is a Claude-API-only variant")
    if a.cost_cap < 0:  # negative cap from the calling batch script: no budget left
        print("STOPPED at the cost cap: no budget room left for this run", file=sys.stderr, flush=True)
        raise SystemExit(3)
    gen = api or bool(prompt_spec)   # shared request builder (build_claude_request) + strict parse
    global RETR_K
    if a.retrieval:
        if a.condition != "C2" or not a.k or not api:
            raise SystemExit("--retrieval needs --condition C2, --k and a Claude API system (E3: Haiku)")
        for l in open(a.retrieval, encoding="utf-8"):
            x = json.loads(l); RETRIEVED[x["claim_id"]] = x["passages"]
        RETR_K = a.k
    if api and a.effort:
        CLAUDE_EFFORT_RUN[a.system] = a.effort
    lock = threading.Lock()

    def plen(prompt):
        if isinstance(prompt, str):
            return len(prompt)
        blocks = prompt["system"] + [b for m in prompt["messages"] for b in (m["content"] if isinstance(m["content"], list) else [{"text": m["content"]}])]
        return sum(len(b["text"]) for b in blocks)

    fp = None
    if api:  # configuration fingerprint: a resumed run must not reuse records made with another model/prompt/effort/source
        fp = hashlib.sha256(json.dumps([a.system, CLAUDE_API_MODELS[a.system], a.condition, CLAUDE_EFFORT_RUN.get(a.system, CLAUDE_EFFORT[a.system]),
                                        CLAUDE_MAX_TOKENS, prompt_spec["text"] if prompt_spec else ASK, prompt_spec["source_placement"] if prompt_spec else "system",
                                        os.path.abspath(a.src_root), max_chars, BUILDER_VERSION]
                                       + ([a.retrieval and os.path.abspath(a.retrieval), a.k] if a.retrieval else [])).encode()).hexdigest()[:16]
    elif gen:  # same for the OpenAI and Qwen --prompt runs
        fp = hashlib.sha256(json.dumps([a.system, OPENAI_MODELS.get(a.system, QWEN_REPO), a.condition, OPENAI_EFFORT if a.system in OPENAI_MODELS else "greedy",
                                        QWEN_MAX_NEW if a.system == "qwen" else 4000, prompt_spec["text"], prompt_spec["source_placement"],
                                        os.path.abspath(a.src_root), max_chars, BUILDER_VERSION]
                                       + ([a.retrieval and os.path.abspath(a.retrieval), a.k] if a.retrieval else [])).encode()).hexdigest()[:16]
    psha = hashlib.sha256(prompt_spec["text"].encode()).hexdigest()[:12] if prompt_spec else ""
    spent = {"cost": 0.0, "stop": False}

    def build(c):
        if gen:
            return build_claude_request(c, a.condition, a.src_root, max_chars, prompt_spec)
        return build_prompt(c, a.condition, a.src_root, max_chars)

    def req_sha(prompt):  # hash of the exact request content (sources, retrieved passages, prompt, claim)
        return hashlib.sha256(json.dumps(prompt, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]

    def add_cost(x):  # under the lock
        spent["cost"] += x
        if a.cost_cap and spent["cost"] > a.cost_cap and not spent["stop"]:
            spent["stop"] = True
            print(f"COST CAP ${a.cost_cap} reached (${spent['cost']:.2f}); no new calls", file=sys.stderr, flush=True)

    # resumed records: check them and count their cost before any new call
    resumed = {}
    ep = os.path.join(rdir, "errors.jsonl")
    if not a.dry_run and os.path.exists(ep):  # cost of earlier failed / uncached attempts of this run
        add_cost(sum(json.loads(l).get("cost", 0) for l in open(ep, encoding="utf-8")))
    if not a.dry_run:
        for c in claims:
            f = os.path.join(rdir, "raw", f"{c['claim_id']}.json")
            if os.path.exists(f):
                old = json.load(open(f, encoding="utf-8"))
                if gen and (old.get("fingerprint") != fp or old.get("claim_text_sha") != hashlib.sha256(c["claim_text"].encode()).hexdigest()[:16]
                            or old.get("request_sha") != req_sha(build(c)[0])):
                    raise SystemExit(f"{f} was made with another configuration, request or claim text; use a new --run-id")
                resumed[c["claim_id"]] = old
        # every cached record of this run counts toward the cap, also those outside the selected claims
        add_cost(sum(json.load(open(f, encoding="utf-8")).get("cost", 0) for f in glob.glob(os.path.join(rdir, "raw", "*.json"))))

    def one(c):
        if c["claim_id"] in resumed:
            return resumed[c["claim_id"]]
        f = os.path.join(rdir, "raw", f"{c['claim_id']}.json")
        if spent["stop"]:
            return None
        prompt, trunc, src_chars = build(c)
        if a.dry_run:
            blocks = prompt["system"] + [b for m in prompt["messages"] for b in (m["content"] if isinstance(m["content"], list) else [{"text": m["content"]}])] if gen else [{"text": prompt}]
            return {"claim_id": c["claim_id"], "ann_id": c["ann_id"], "truncated": trunc, "src_chars": src_chars,
                    "blocks": [(len(b["text"]), hashlib.sha256(b["text"].encode()).hexdigest()[:10], "cache" if b.get("cache_control") else "-") for b in blocks],
                    "has_full_text": "<full_decision_text>" in "".join(b["text"] for b in blocks) or "FULL DECISION TEXT:" in "".join(b["text"] for b in blocks)}
        calls = []
        for _ in range(2):  # invalid outputs are retried once (prereg section 5); a refusal is not retried
            if spent["stop"]:
                break  # cap reached: no new attempt
            r = call(a.system, prompt, f"{c['ann_id']}|{a.condition}|{psha}|{a.k or 0}"); calls.append(r)
            with lock:
                add_cost(r["cost"])
            if parse_label(r["text"], strict=gen) or r.get("refused") or r.get("error"):
                break
        if not calls:
            return None
        refused = bool(calls[-1].get("refused"))
        capped = len(calls) == 1 and not (parse_label(calls[0]["text"], strict=gen) or calls[0].get("refused") or calls[0].get("error"))
        rec = {"claim_id": c["claim_id"], "ann_id": c["ann_id"], "system": a.system, "condition": a.condition,
               "gold": c.get("gold_label", ""), "label": "REFUSED" if refused else (parse_label(calls[-1]["text"], strict=gen) or "UNPARSEABLE"),
               "raw_text": calls[-1]["text"], "n_calls": len(calls), "truncated": trunc, "src_chars": src_chars,
               "prompt_chars": plen(prompt), "model_id": calls[-1].get("model_id", ""),
               "prompt_file": prompt_spec["path"] if prompt_spec else "", "fingerprint": fp, "request_sha": req_sha(prompt),
               "claim_text_sha": hashlib.sha256(c["claim_text"].encode()).hexdigest()[:16], "effort": calls[-1].get("effort", ""),
               "stop_reason": calls[-1].get("stop_reason", ""), "stop_details": calls[-1].get("stop_details"),
               "uncached_in_tok": sum(x.get("uncached_in_tok", 0) for x in calls),
               "cache_write_tok": sum(x.get("cache_write_tok", 0) for x in calls),
               "in_tok": sum(x["in_tok"] for x in calls), "cached_tok": sum(x.get("cached_tok", 0) for x in calls),
               "out_tok": sum(x["out_tok"] for x in calls), "reasoning_tok": sum(x.get("reasoning_tok", 0) for x in calls),
               "cost": sum(x["cost"] for x in calls), "seconds": sum(x["seconds"] for x in calls),
               "error": calls[-1].get("error", ""), "calls": calls}
        if capped:  # the invalid first attempt was not retried because of the cost cap: do not cache it (a re-run redoes it)
            rec["error"] = "cost cap before retry"
        with lock:
            if not rec["error"]:
                json.dump(rec, open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            else:  # not cached, so a re-run retries it; the attempts (and any cost already incurred) are kept here
                with open(os.path.join(rdir, "errors.jsonl"), "a", encoding="utf-8") as fh:
                    fh.write(json.dumps({k: v for k, v in rec.items() if k != "calls"} | {"time": time.strftime("%Y-%m-%d %H:%M:%S")},
                                        ensure_ascii=False) + "\n")
        return rec

    t0 = time.time()
    if a.system == "qwen":
        recs = [one(c) for c in claims]
    elif gen:
        # cache reuse: all claims of one announcement run consecutively in one worker (one run = one condition, so the
        # (announcement, condition) prefix is the same); the first claim writes the cache, the next ones read it
        groups = {}
        for c in claims:
            groups.setdefault(c["ann_id"], []).append(c)
        with cf.ThreadPoolExecutor(a.workers) as ex:
            done = dict((r["claim_id"], r) for g in ex.map(lambda g: [one(c) for c in g], groups.values()) for r in g if r is not None)
        recs = [done.get(c["claim_id"]) for c in claims]
    else:
        with cf.ThreadPoolExecutor(a.workers) as ex:
            recs = list(ex.map(one, claims))
    wall = time.time() - t0
    if not a.dry_run and any(r is None for r in recs):
        recs = [r for r in recs if r is not None]
        print(f"STOPPED at the cost cap: {len(recs)} of {len(claims)} claims done (cost ${spent['cost']:.2f})", file=sys.stderr)
    if a.dry_run:
        for r in recs:
            print(json.dumps(r, ensure_ascii=False))
        return
    cols = ["claim_id", "ann_id", "gold", "label", "raw_text", "model_id", "effort", "stop_reason", "in_tok", "uncached_in_tok",
            "cached_tok", "cache_write_tok", "out_tok", "reasoning_tok", "cost", "seconds", "truncated", "src_chars", "n_calls", "error"]
    with open(os.path.join(rdir, "predictions.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(cols)
        for r in recs:
            w.writerow([str(r.get(k, "")).replace("\n", " ")[:300] for k in cols])
    meta = {"run_id": run_id, "system": a.system, "condition": a.condition, "claims": os.path.relpath(a.claims, MAIN),
            "n": len(recs), "wall_seconds_last_invocation": round(wall, 1), "max_chars": max_chars,
            "openai_effort": OPENAI_EFFORT if a.system in OPENAI_MODELS else None, "source_in_system": a.source_in_system,
            "src_root": os.path.relpath(a.src_root, MAIN),
            "ask": prompt_spec["text"] if prompt_spec else ASK, "complete": len(recs) == len(claims),
            "prompt_file": prompt_spec["path"] if prompt_spec else "(built-in ASK)",
            "prompt_sha256": hashlib.sha256((prompt_spec["text"] if prompt_spec else ASK).encode()).hexdigest(),
            "retrieval": os.path.relpath(a.retrieval, MAIN) if a.retrieval else None, "k": a.k or None,
            "model_id": OPENAI_MODELS.get(a.system) or (QWEN_REPO if a.system == "qwen" else None)}
    if api:
        meta.update({"model_id": CLAUDE_API_MODELS[a.system], "effort": CLAUDE_EFFORT_RUN.get(a.system, CLAUDE_EFFORT[a.system]),
                     "max_tokens": CLAUDE_MAX_TOKENS, "prompt_file": prompt_spec["path"] if prompt_spec else "(built-in ASK)",
                     "prompt_sha256": hashlib.sha256((prompt_spec["text"] if prompt_spec else ASK).encode()).hexdigest(),
                     "source_placement": prompt_spec["source_placement"] if prompt_spec else "system",
                     "price_source": "Anthropic pricing table, 2026-10-06"})
    meta.update({"finished": time.strftime("%Y-%m-%d %H:%M:%S")})
    mp = os.path.join(rdir, "meta.json")
    old = json.load(open(mp)) if os.path.exists(mp) else {}
    meta["wall_seconds_total"] = round(old.get("wall_seconds_total", 0) + wall, 1)
    json.dump(meta, open(mp, "w"), indent=1)
    s = score(recs)
    print(f"{run_id}: n={len(recs)} macroF1={s['macro_f1']:.3f} acc={s['acc']:.3f} unparseable={s['unp']} refused={s['refused']} "
          f"cost=${sum(r['cost'] for r in recs):.3f} wall={wall/60:.1f} min errors={sum(1 for r in recs if r.get('error'))}")


def score(recs, min_n=10, gold=None):
    """gold: optional {claim_id: label} that overrides the gold stored in the records."""
    gg = {r["claim_id"]: (gold.get(r["claim_id"], "") if gold is not None else r["gold"]) for r in recs}
    g = [gg[r["claim_id"]] for r in recs if gg[r["claim_id"]]]
    p = [("SUPPORTED" if r["label"] in ("UNPARSEABLE", "REFUSED") else r["label"]) for r in recs if gg[r["claim_id"]]]  # prereg section 5: invalid outputs are scored as SUPPORTED
    labs = [l for l, n in Counter(g).items() if n >= min_n]
    f, rec = [], {}
    for c in sorted(set(g)):
        n_c = sum(x == c for x in g); rec[c] = sum(x == c and y == c for x, y in zip(g, p)) / n_c
    for c in labs:
        tp = sum(x == c and y == c for x, y in zip(g, p)); fp = sum(x != c and y == c for x, y in zip(g, p)); fn = sum(x == c and y != c for x, y in zip(g, p))
        pr = tp / (tp + fp) if tp + fp else 0; rc = tp / (tp + fn) if tp + fn else 0
        f.append(2 * pr * rc / (pr + rc) if pr + rc else 0)
    return {"macro_f1": sum(f) / len(f) if f else float("nan"), "acc": sum(x == y for x, y in zip(g, p)) / len(g) if g else float("nan"),
            "unp": sum(r["label"] == "UNPARSEABLE" for r in recs), "refused": sum(r["label"] == "REFUSED" for r in recs),
            "recall": rec, "labels": sorted(labs), "pred_dist": dict(Counter(r["label"] for r in recs))}


def summarize(a):
    rows = []
    for rid in a.run_ids:
        rdir = os.path.join(MAIN, "runs", rid)
        meta = json.load(open(os.path.join(rdir, "meta.json")))
        recs = [json.load(open(f, encoding="utf-8")) for f in sorted(glob.glob(os.path.join(rdir, "raw", "*.json")))]
        s = score(recs)
        extra = {}
        if a.gold2:
            g2 = {x["claim_id"]: x["gold_label"] for x in csv.DictReader(open(a.gold2, encoding="utf-8")) if x["gold_label"] != "UNASSESSABLE"}
            s2 = score(recs, min_n=a.gold2_min_n, gold=g2)
            extra = {"v1_macro_f1": round(s2["macro_f1"], 3), "v1_f1_labels": "+".join(s2["labels"]), "v1_accuracy": round(s2["acc"], 3),
                     **{f"v1_recall_{k}": f"{v:.2f} (n={sum(1 for r in recs if g2.get(r['claim_id']) == k)})" for k, v in sorted(s2["recall"].items())}}
        rows.append({"run_id": rid, "system": meta["system"], "condition": meta["condition"],
                     "model_id": ";".join(sorted({r["model_id"] for r in recs})), "n": len(recs),
                     "macro_f1": round(s["macro_f1"], 3), "f1_labels": "+".join(s["labels"]), "accuracy": round(s["acc"], 3),
                     "unparseable": s["unp"], "refused": s["refused"], "pred_dist": json.dumps(s["pred_dist"]),
                     "prompt_file": meta.get("prompt_file", ""), "effort": meta.get("effort") or meta.get("openai_effort") or "",
                     "cache_write_tokens": sum(r.get("cache_write_tok", 0) for r in recs),
                     "input_tokens": sum(r["in_tok"] for r in recs), "cached_input_tokens": sum(r["cached_tok"] for r in recs),
                     "output_tokens": sum(r["out_tok"] for r in recs), "reasoning_tokens": sum(r["reasoning_tok"] for r in recs),
                     "truncated": sum(bool(r["truncated"]) for r in recs),
                     "cost_usd": round(sum(r["cost"] for r in recs), 4),
                     "failed_attempt_cost_usd": round(sum(json.loads(l).get("cost", 0) for l in open(os.path.join(rdir, "errors.jsonl"), encoding="utf-8"))
                                                      if os.path.exists(os.path.join(rdir, "errors.jsonl")) else 0, 4),
                     "minutes": round(meta.get("wall_seconds_total", 0) / 60, 2),
                     "sec_per_claim_call": round(sum(r["seconds"] for r in recs) / max(1, len(recs)), 2), **extra})
    with open(os.path.join(MAIN, a.out), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    for r in rows:
        print(r)


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    r = sp.add_parser("run")
    r.add_argument("--system", required=True); r.add_argument("--condition", required=True, choices=["C0", "C1", "C2"])
    r.add_argument("--claims", default=os.path.join(PILOT, "adjudication/gold_labels.csv"))
    r.add_argument("--src-root", default=os.path.join(PILOT, "data/raw/announcements"))
    r.add_argument("--limit", type=int, default=0); r.add_argument("--workers", type=int, default=4); r.add_argument("--run-id", default="")
    r.add_argument("--source-in-system", action="store_true", help="opus (claude -p): put instructions+source in the system prompt so it is cached across claims of one announcement")
    r.add_argument("--prompt", default="", help="prompt file for every LLM system (prompts/main.txt, prompts/e4_v*.txt); default = built-in ASK")
    r.add_argument("--effort", default="", choices=["", "low", "medium", "high", "xhigh", "max"], help="Claude API systems: override CLAUDE_EFFORT")
    r.add_argument("--max-chars", type=int, default=0, help="source cap in characters (default: MAX_CHARS / DEFAULT_MAX_CHARS)")
    r.add_argument("--dry-run", action="store_true", help="build the requests and print block sizes/hashes; no model call")
    r.add_argument("--cost-cap", type=float, default=0, help="stop making new calls once this run's cost (incl. resumed records) exceeds this USD")
    r.add_argument("--retrieval", default="", help="E3: JSONL from scripts/e3_retrieve.py (claim_id, passages best first)")
    r.add_argument("--k", type=int, default=0, help="E3: number of retrieved passages")
    s = sp.add_parser("summarize"); s.add_argument("--out", default="runs/dev_choice/cost_test.csv"); s.add_argument("run_ids", nargs="+")
    s.add_argument("--gold2", default="", help="second gold CSV (e.g. pilot round-2 gold_labels_v1.csv) scored as extra v1_* columns")
    s.add_argument("--gold2-min-n", type=int, default=5)
    a = ap.parse_args()
    run(a) if a.cmd == "run" else summarize(a)


if __name__ == "__main__":
    main()
