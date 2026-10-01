#!/usr/bin/env python3
"""
Regenerate the JavaScript signal tables in web/demo-static.html FROM triage.py.

WHY THIS EXISTS
  The public demo is a hand-maintained JS copy of the engine's signal tables.
  When the sector vocabulary was added to triage.py, parity_check.py correctly
  reported 20 drift problems — the demo would have kept promising behaviour the
  pilot engine no longer had. Hand-copying ~200 keywords is how that drift comes
  back, so the tables are now generated from the single Python source of truth.

  Run after ANY change to CATEGORY_SIGNALS / SENSITIVE_SIGNALS / URGENCY_*_SIGNALS:
      python3 gen_demo_tables.py && python3 parity_check.py

WHAT IT DOES NOT TOUCH: the safety-gate ordering, the greeting logic, MIN_CONF,
ROUTES or the sample messages. It rewrites only the table literals, and refuses
to write if it cannot find every block it expects — a silent partial rewrite
would be worse than a failure.
"""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from triage import CATEGORY_SIGNALS, SENSITIVE_SIGNALS, URGENCY_P1_SIGNALS, \
    URGENCY_P2_SIGNALS

HTML = os.path.join(HERE, "web", "demo-static.html")
html = open(HTML, encoding="utf-8").read()

# The JS object key order must match the Python dict order exactly — parity_check
# compares lists element-by-element, so a reordered table is a real drift.
def js_array(items):
    return json.dumps(list(items), ensure_ascii=False)


def build_cats():
    lines = ["const CATS = {"]
    cats = list(CATEGORY_SIGNALS.items())
    for i, (cat, sigs) in enumerate(cats):
        comma = "," if i < len(cats) - 1 else ""
        lines.append(f'  {cat}:{{strong:{js_array(sigs["strong"])},'
                     f'weak:{js_array(sigs["weak"])}}}{comma}')
    lines.append("};")
    return "\n".join(lines)


def build_sensitive():
    # Order in the JS mirrors the Python priority order used by the gate loop:
    # security_incident, legal, billing_dispute, complaint.
    order = ["security_incident", "legal", "billing_dispute", "complaint"]
    missing = [k for k in order if k not in SENSITIVE_SIGNALS]
    if missing:
        raise SystemExit(f"REFUSING to write: missing sensitive keys {missing}")
    lines = ["const SENSITIVE = {"]
    for i, k in enumerate(order):
        comma = "," if i < len(order) - 1 else ""
        lines.append(f"  {k}:{js_array(SENSITIVE_SIGNALS[k])}{comma}")
    lines.append("};")
    return "\n".join(lines)


def replace_block(html, start_marker, end_marker, new_block):
    s = html.find(start_marker)
    if s == -1:
        raise SystemExit(f"REFUSING to write: start marker {start_marker!r} not found")
    e = html.find(end_marker, s)
    if e == -1:
        raise SystemExit(f"REFUSING to write: end marker {end_marker!r} not found")
    e += len(end_marker)
    return html[:s] + new_block + html[e:]


def main():
    orig = html
    doc = orig

    doc = replace_block(doc, "const CATS = {", "\n};", build_cats())
    doc = replace_block(doc, "const SENSITIVE = {", "\n};", build_sensitive())
    doc = replace_block(doc, "const P1=[", "];", f"const P1={js_array(URGENCY_P1_SIGNALS)};")
    doc = replace_block(doc, "const P2=[", "];", f"const P2={js_array(URGENCY_P2_SIGNALS)};")

    if doc == orig:
        print("no change — tables already match triage.py")
        return 0

    open(HTML, "w", encoding="utf-8").write(doc)
    n_kw = sum(len(s["strong"]) + len(s["weak"]) for s in CATEGORY_SIGNALS.values())
    n_sens = sum(len(v) for v in SENSITIVE_SIGNALS.values())
    print(f"regenerated demo-static.html from triage.py")
    print(f"  category keywords : {n_kw}")
    print(f"  sensitive keywords: {n_sens}")
    print(f"  urgency signals   : {len(URGENCY_P1_SIGNALS)} P1 / {len(URGENCY_P2_SIGNALS)} P2")
    return 0


if __name__ == "__main__":
    sys.exit(main())
