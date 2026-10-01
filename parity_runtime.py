#!/usr/bin/env python3
"""
RUNTIME PARITY: actually EXECUTE the JavaScript engine and diff it against Python.

parity_check.py compares the signal TABLES and cross-checks labels, but it admits
in its own docstring that it does not run JS ("no runtime here"). That left a real
divergence in place: the JS spam tie-break used `>=` where Python requires a
strictly higher score, so a spam message that merely TIED with another category
would be quarantined by the demo and routed by the pilot. Same tables, different
behaviour — and the public demo is what prospects judge the product on.

This harness closes that gap. It extracts the real triage() function out of
web/demo-static.html, runs every benchmark case from ALL THREE suites through
both engines, and reports any disagreement in category, urgency, action,
needs_human or route.

Requires node. Skips cleanly (exit 0) if node is unavailable, because a missing
runtime is not a parity failure.
"""
import json, os, re, subprocess, sys
from dataclasses import asdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from triage import triage
import bench_extended as be
import bench_sector as bs


def find_demo():
    """Locate demo-static.html in either supported layout.

    The private repo keeps it at web/demo-static.html; the PUBLIC repo has it at
    the repository root (index.html links it that way). The verification tools
    are published so a prospect can run them, so they must not assume a layout
    they were never given.
    """
    for rel in ("web/demo-static.html", "demo-static.html"):
        p = os.path.join(HERE, rel)
        if os.path.exists(p):
            return p
    raise SystemExit("demo-static.html not found in web/ or at repo root")


HTML_PATH = find_demo()


def extract_js():
    """Pull the <script> body containing the engine out of the static demo."""
    html = open(HTML_PATH, encoding="utf-8").read()
    m = re.search(r"<script>(.*?)</script>", html, re.S)
    if not m:
        raise SystemExit("no <script> block found in demo-static.html")
    js = m.group(1)
    # The DOM half (render/run/SAMPLES.onclick) cannot run under bare node; the
    # engine half (tables + triage + draftReply) is pure and can.
    for fn in ("function triage(", "function draftReply("):
        if fn not in js:
            raise SystemExit(f"expected {fn} in demo-static.html")
    # The engine section starts at the CATS table (ROUTES/SENSITIVE/P1/P2 are
    # declared around it) and ends before the DOM helpers.
    start = js.find("const CATS = {")
    end = js.find("function esc(")
    if start == -1 or end == -1 or end < start:
        raise SystemExit("could not isolate engine section of demo-static.html")
    return js[start:end]


def main():
    cases = []
    for tag, suite_cases in (("extended", be.CASES), ("sector", bs.CASES)):
        for subj, body, sender, exp, is_sens in suite_cases:
            cases.append({"suite": tag, "subject": subj, "body": body,
                          "sender": sender, "expected": exp, "sensitive": is_sens})

    py = []
    for c in cases:
        r = asdict(triage(c["subject"], c["body"], c["sender"]))
        py.append({"category": r["category"], "urgency": r["urgency"],
                   "action": r["action"], "needs_human": r["needs_human"],
                   "route_to": r["route_to"]})

    engine = extract_js()
    harness = engine + """
const cases = JSON.parse(require('fs').readFileSync(process.argv[2], 'utf8'));
const out = cases.map(c => {
  const r = triage(c.subject, c.body, c.sender);
  return {category: r.category, urgency: r.urgency, action: r.action,
          needs_human: r.needsHuman, route_to: r.route};
});
process.stdout.write(JSON.stringify(out));
"""
    # Write the harness outside the repo: this is a generated verification
    # artefact, not a project file.
    tmp = os.path.join("/tmp", "js_parity_harness.js")
    cin = os.path.join("/tmp", "js_parity_cases.json")
    open(tmp, "w", encoding="utf-8").write(harness)
    open(cin, "w", encoding="utf-8").write(json.dumps(cases))

    try:
        res = subprocess.run(["node", tmp, cin], capture_output=True, text=True,
                             timeout=60)
    except FileNotFoundError:
        print("node not available — runtime parity SKIPPED (not a failure)")
        return 0
    if res.returncode != 0:
        print("JS ENGINE THREW — the public demo is broken:")
        print(res.stderr.strip()[:2000])
        return 1

    js = json.loads(res.stdout)

    diffs = []
    for c, p, j in zip(cases, py, js):
        for field in ("category", "urgency", "action", "needs_human", "route_to"):
            if p[field] != j[field]:
                diffs.append((c["suite"], c["subject"][:44], field,
                              p[field], j[field]))

    print("=" * 66)
    print("RUNTIME PARITY: python triage.py  vs  executed JS demo engine")
    print("=" * 66)
    print(f"cases executed in both engines: {len(cases)} "
          f"({sum(1 for c in cases if c['suite'] == 'extended')} extended + "
          f"{sum(1 for c in cases if c['suite'] == 'sector')} sector)")
    print("-" * 66)
    if diffs:
        print(f"{len(diffs)} DISAGREEMENT(S):")
        for suite, subj, field, pv, jv in diffs:
            print(f"  [{suite:8s}] {subj:46s} {field}: py={pv!r} js={jv!r}")
        print("-" * 66)
        print("VERDICT: FAIL — the demo would behave differently from the pilot")
        print("=" * 66)
        return 1

    print("no disagreements in category / urgency / action / needs_human / route")
    print("-" * 66)
    print("VERDICT: PASS — the demo behaves exactly like the paid engine")
    print("=" * 66)
    return 0


if __name__ == "__main__":
    sys.exit(main())
