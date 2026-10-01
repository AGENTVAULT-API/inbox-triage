# Engineering log — Inbox Triage

Real notes from building this, including the parts that went wrong. Written for
whoever is deciding whether to trust the thing with a live mailbox.

---

## 1. The bug that mattered

The first version classified an email first, then checked whether it was
sensitive:

```python
category = classify(email)          # -> "sales"
subtype  = classify_subtype(...)    # -> "legal"?  only checked for support/billing
if subtype in HUMAN_ONLY:
    hold_for_human()
```

Benchmark result: **sensitivity 50%.** Required bar: 100%.

Two real failures:

| Input | Classified as | Should be |
|---|---|---|
| "Our solicitor has issued a legal notice..." | `sales` | `legal`, hold |
| "URGENT: data breach... escalate to your CTO" | `press` | `security_incident`, hold |

The first one is the instructive one. It contained the words *pricing*, *proposal*
and *contract* alongside *attorney* and *legal notice*. Sales scored 12, legal
never got a look because the subtype check only ran when the winning category was
`support` or `billing`.

**A safety check placed after the decision it is supposed to prevent is not a
safety check.** It is a branch that runs on the happy path.

The fix moves detection ahead of classification entirely:

```python
sensitive, hits = detect_sensitive(combined)   # scans the WHOLE message
if sensitive:
    return TriageResult(category=sensitive, urgency="P1",
                        action="hold_for_human", reply=None)
```

Deliberately fail-closed: routing a harmless email to a person costs ten seconds
of someone's attention. Auto-answering a complaint costs a customer.

There is now an adversarial regression case for exactly the input that broke it.
It will not stay fixed by accident:

```python
("Great opportunity - please send proposal",
 "I love your pricing and would like to discuss a contract ... However our
  attorney has issued a legal notice which we must resolve first.",
 "buyer@corp.com", "legal", True),
```

---

## 2. The bug that was embarrassing

The 48-case suite failed at **82.9%** routing. Several failures shared a cause:

```
"Please advise."                              -> sales
"Any update on this? Would be good to hear"   -> sales
```

Not because those emails looked like sales. Because `sales` was the **first key**
in a dictionary and every category scored zero. Python's `sorted` is stable, so a
zero-score tie resolved to whichever category happened to be declared first.

The real defect was not the tie-break. It was that the engine **always produced a
confident answer**, including when it had no idea:

```python
MIN_CONFIDENCE_SCORE = 3.0
if top_score < MIN_CONFIDENCE_SCORE:
    return TriageResult(category="unclassified", action="hold_for_human", ...)
```

An honest "I don't know, ask a person" is a feature, not a failure. A pilot whose
entire promise is *the routing is trustworthy* has no business guessing.

One benchmark label was also wrong: `"Please advise"` was marked `internal` when
the correct outcome is abstain. I fixed the **label, not the guard** — weakening
a safety mechanism to make a test pass is the wrong trade at any time.

---

## 3. Verifying against my own good ideas

The research subagent reported 30 SME prospects with contact addresses "read
directly off the company's own website". Plausible, unverified, and a fabricated
lead is worse than no lead — it bounces, it damages sender reputation, and it is
dishonest. So: re-fetch every source page and check the address is present.

```
27/30 CONFIRMED on live pages
 3/30 UNCONFIRMED -> re-fetched by hand, no email anywhere -> do-not-contact
```

Two of the three were **medical clinics**. They fit the problem well, which is
exactly why they were a trap: patient data is special-category under GDPR Art. 9,
a first pilot is when bugs still exist, and the consequence of a misroute there
is a reportable incident rather than a late quote. Marked `do-not-contact` with
the reason recorded.

The first customer should be someone whose worst case is embarrassing.

---

## 4. Two engines, one promise

The public demo is a browser-side JS re-implementation of the same signal tables,
because Python does not run on GitHub Pages. Duplicated logic in two languages
will drift unless something checks.

`parity_check.py` asserts the category tables, the sensitive tables, the urgency
lists, `MIN_CONFIDENCE`, and — the one that matters — that the **safety gate runs
before category scoring in the JS**:

```
PARITY OK — static demo matches the engine exactly
```

It also caught a false positive in itself (looking for `P1:[` when the code said
`P1=[`). Worth fixing, because a checker that cries wolf gets ignored.

A demo that promises behaviour the pilot does not have is worse than no demo.

---

## 5. Things a fresh clone broke

Publishing the repo meant the benchmarks crashed for anyone who cloned it — they
wrote results to `state/` without creating it. Nobody would have taken the
numbers seriously from a repo whose first command crashes.

```python
os.makedirs(STATE, exist_ok=True)
```

Small thing. Also the difference between "here is a tool" and "here is a tool I
expect you to actually run".

---

## What this project is not

The numbers in the README are this project's own benchmarks on synthetic messages
written by the author. They are not customer results, and there are no customer
results yet. The first real mailbox will behave differently; discovering how is
what the pilot is for.

The engine has never seen a real customer's mail. That is the honest limit of
everything measured so far.

---

## Principles that stuck

1. **Fail closed.** Route to a person before you automate; never after.
2. **Abstain when unsure.** Confidence you cannot justify is not confidence.
3. **Verify your own claims.** Including claims made by your own subagents.
4. **A wrong-but-confident answer costs more than a refusal.**
5. **Record why a decision was made,** so the next session doesn't relitigate it
   or quietly undo it.