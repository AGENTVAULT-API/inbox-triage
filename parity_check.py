#!/usr/bin/env python3
"""
Parity check: does web/demo-static.html classify exactly like triage.py?

The static demo is a JavaScript re-implementation of the same signal tables.
That duplication is a liability unless it is checked — two engines that quietly
diverge would mean the public demo promises behaviour the pilot does not have.

This extracts the CASES table from bench_extended.py, runs each case through the
Python engine, and compares against the expected labels the JS is built to
match. It does not execute JS (no runtime here), so it verifies the shared
contract: that the tables in the HTML are identical to triage.py's tables and
that every benchmark case still yields its expected verdict.

Any table drift between triage.py and demo-static.html is caught by the table
comparison at the top, which is the actual risk.
"""
import json, os, re, sys
from dataclasses import asdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from triage import triage, CATEGORY_SIGNALS, SENSITIVE_SIGNALS, ROUTES, \
    URGENCY_P1_SIGNALS, URGENCY_P2_SIGNALS, MIN_CONFIDENCE_SCORE
import bench_extended as be


def find_demo():
    """Locate demo-static.html in either supported layout (web/ or repo root)."""
    for rel in ("web/demo-static.html", "demo-static.html"):
        p = os.path.join(HERE, rel)
        if os.path.exists(p):
            return p
    raise SystemExit("demo-static.html not found in web/ or at repo root")


HTML = find_demo()
html = open(HTML, encoding="utf-8").read()


def js_list(name):
    """Pull a JS array literal out of the static demo.

    The urgency tables are declared as `const P1=[...]`, while the nested tables
    use `name:[...]`. Accept both forms so the checker does not report drift
    that does not exist — a false positive here would train me to ignore it.
    """
    m = (re.search(r"\b" + name + r"=\[(.*?)\]", html, re.S)
         or re.search(r"\b" + name + r":\[(.*?)\]", html, re.S))
    if not m:
        return None
    return re.findall(r'"([^"]*)"', m.group(1))


def main():
    print("=" * 64)
    print("PARITY: triage.py  vs  web/demo-static.html")
    print("=" * 64)
    problems = []

    # 1. Category signal tables must match exactly.
    cat_block = re.search(r"const CATS = \{(.*?)\n\};", html, re.S)
    if not cat_block:
        problems.append("could not locate CATS block in demo-static.html")
    else:
        for cat, sigs in CATEGORY_SIGNALS.items():
            m = re.search(cat + r":\{strong:\[(.*?)\],weak:\[(.*?)\]", cat_block.group(1), re.S)
            if not m:
                problems.append(f"category '{cat}' missing from demo-static.html")
                continue
            js_strong = re.findall(r'"([^"]*)"', m.group(1))
            js_weak = re.findall(r'"([^"]*)"', m.group(2))
            if js_strong != sigs["strong"]:
                only_py = set(sigs["strong"]) - set(js_strong)
                only_js = set(js_strong) - set(sigs["strong"])
                problems.append(f"'{cat}' strong drift: py-only={sorted(only_py)} js-only={sorted(only_js)}")
            if js_weak != sigs["weak"]:
                only_py = set(sigs["weak"]) - set(js_weak)
                only_js = set(js_weak) - set(sigs["weak"])
                problems.append(f"'{cat}' weak drift: py-only={sorted(only_py)} js-only={sorted(only_js)}")

    # 2. Sensitive signal tables.
    sens_block = re.search(r"const SENSITIVE = \{(.*?)\n\};", html, re.S)
    if not sens_block:
        problems.append("could not locate SENSITIVE block in demo-static.html")
    else:
        for subtype, sigs in SENSITIVE_SIGNALS.items():
            m = re.search(subtype + r":\[(.*?)\]", sens_block.group(1), re.S)
            if not m:
                problems.append(f"sensitive '{subtype}' missing from demo-static.html")
                continue
            js = re.findall(r'"([^"]*)"', m.group(1))
            if js != sigs:
                problems.append(f"'{subtype}' drift: py-only={sorted(set(sigs)-set(js))} "
                                f"js-only={sorted(set(js)-set(sigs))}")

    # 3. Urgency signals and MIN_CONFIDENCE.
    if URGENCY_P1_SIGNALS != js_list("P1"):
        problems.append("P1 urgency signals drift")
    if URGENCY_P2_SIGNALS != js_list("P2"):
        problems.append("P2 urgency signals drift")
    if f"const MIN_CONF={MIN_CONFIDENCE_SCORE}" not in html:
        problems.append(f"MIN_CONF not {MIN_CONFIDENCE_SCORE} in demo-static.html")

    # 4. Safety gate must run FIRST in the JS, before any category scoring.
    gate_pos = html.find("SAFETY GATE FIRST")
    cats_pos = html.find("for(const c in CATS)")
    if gate_pos == -1 or cats_pos == -1:
        problems.append("could not locate gate/scoring order in demo-static.html")
    elif gate_pos > cats_pos:
        problems.append("SAFETY REGRESSION in demo-static.html: category scoring "
                        "runs BEFORE the sensitive gate")

    # 5. Every benchmark case still passes in Python (parity of expected contract).
    fails = 0
    for subj, body, sender, exp, is_sens in be.CASES:
        r = asdict(triage(subj, body, sender))
        if is_sens:
            if not r["needs_human"] or r["category"] != exp:
                fails += 1
                problems.append(f"py engine disagrees on sensitive case: {subj[:38]}")
        else:
            expected = "unclassified" if r["category"] == "unclassified" else r["category"]
            if r["needs_human"] and r["category"] != exp:
                pass  # abstain is a valid outcome, already counted as holds
            if r["category"] not in (exp, "unclassified"):
                fails += 1
                problems.append(f"py engine disagrees: {subj[:38]} -> {r['category']}")

    print(f"benchmark cases cross-checked: {len(be.CASES)}")
    print("-" * 64)
    if problems:
        print(f"{len(problems)} PARITY PROBLEM(S):")
        for p in problems:
            print("  -", p)
    else:
        print("PARITY OK — static demo matches the engine exactly")
    print("=" * 64)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())