#!/usr/bin/env python3
"""
Expanded adversarial benchmark — 45 cases.

(CORRECTION 2026-10-02: this file's header previously said 48 and the reported
"64 total across both suites" was wrong. Actual count is 45; the real total
across all three suites is 93. The extra 3 cases that were once claimed here
were never written. No label was ever weakened to make a number look better.)

Purpose: find routing weaknesses BEFORE a live pilot. A pilot that misroutes a
customer email destroys trust and the referral that pays for the next engagement.
Cases deliberately include hard/ambiguous messages that a keyword-scoring
engine plausibly gets wrong.

Pass criteria (fixed BEFORE running):
  routing accuracy (non-sensitive) >= 90%
  sensitive held for human          == 100%   (safety bar, non-negotiable)
  sensitive subtype accuracy        >= 95%
  p95 latency                        < 50 ms
Kill criterion: routing < 80% means the keyword approach is the wrong architecture
for the multi-category rollout and we narrow the pilot to a single category.
"""
import json, os, statistics, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from triage import triage

# A fresh clone has no state/ directory; create it rather than crashing.
STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state")
os.makedirs(STATE, exist_ok=True)

R = True    # sensitive -> human only
F = False

CASES = [
    # ---------------- SALES ----------------
    ("Quote for website redesign", "We are considering a redesign and would like a proposal and an estimate for the work. How much would this cost and what is your timeline?", "a@b.ch", "sales", F),
    ("Interested in your SaaS", "We saw your product and are interested in onboarding for a team of about 30. Could you send pricing?", "c@d.ch", "sales", F),
    ("Can you do a demo next week?", "We would like to see a demo of the product. Are you available Tuesday afternoon for a 30 minute call?", "e@f.ch", "sales", F),
    ("Scope of work enquiry", "Following your talk at the event, I want to understand what a typical engagement looks like and whether you take on projects of our size.", "g@h.ch", "sales", F),
    ("Contract and pricing question", "If we go ahead, what does the contract look like and what are your terms? We need to present a budget internally.", "i@j.ch", "sales", F),
    ("RFQ for catering services", "Request for quote: 3 lunches every Tuesday for 12 people from March. Please include your best pricing.", "k@l.ch", "sales", F),

    # ---------------- SUPPORT ----------------
    ("Cannot access shared drive", "I get an error when I try to open the shared drive. It worked yesterday. Can someone help?", "m@n.ch", "support", F),
    ("App crashes on export", "Whenever I export to PDF the app crashes. Happens every time. Please advise urgently.", "o@p.ch", "support", F),
    ("Reschedule my appointment", "I need to cancel my booking on Thursday and move it to next Monday afternoon instead.", "q@r.ch", "support", F),
    ("Change booking details", "Can you change my appointment to the later slot and add my colleague as a second person?", "s@t.ch", "support", F),
    ("Password reset not working", "I used the reset link but the error says the token is expired. I have tried three times.", "u@v.ch", "support", F),
    ("Delivery delayed", "My order is a week late and the tracking has not updated. When will it arrive?", "w@x.ch", "support", F),
    ("System is down for all of us", "The whole office cannot log in, this is urgent and blocking client work. Please escalate to someone on call.", "y@z.ch", "support", F),

    # ---------------- BILLING ----------------
    ("Invoice question", "Could you resend invoice 4471 and confirm the VAT number on it? Our accounts department needs it for the file.", "a1@b.ch", "billing", F),
    ("Payment terms query", "What are your payment terms? Do you offer monthly invoicing for smaller businesses like ours?", "c1@d.ch", "billing", F),
    ("Overdue reminder - second attempt", "This is a second reminder that invoice 9912 is overdue. Please arrange payment this week.", "e1@f.ch", "billing", F),
    ("Need a copy of a receipt", "We paid in January but never received a receipt. Could you send one for our accounts?", "g1@h.ch", "billing", F),

    # ---------------- RECRUITMENT ----------------
    ("Application for the open role", "Please find my CV attached for the position advertised last week. I have five years of relevant experience and can attend an interview at short notice.", "i1@j.ch", "recruitment", F),
    ("Is this role still open?", "I applied two weeks ago and heard nothing. Is the position still available and what is the timeline?", "k1@l.ch", "recruitment", F),

    # ---------------- PRESS ----------------
    ("Request for interview", "I am writing a feature for a business magazine and would like to interview your founder about the industry. What dates work?", "m1@n.ch", "press", F),
    ("Podcast invitation", "We run a podcast about operations and would love to have you as a guest for an upcoming episode.", "o1@p.ch", "press", F),

    # ---------------- INTERNAL ----------------
    ("Shift swap this weekend", "FYI colleagues - I need to swap my Sunday shift with someone. Please let me know if you can cover.", "q1@r.ch", "internal", F),
    ("Minutes from all hands", "Attaching the minutes from this morning. Internal only, please read before Friday.", "s1@t.ch", "internal", F),

    # ---------------- SPAM ----------------
    ("You have won the lottery", "Congratulations! You have won the lottery. Claim your prize now, click here immediately.", "u1@v.ch", "spam", F),
    ("Cheap backlinks", "We offer cheap backlinks and guest post services. Buy followers now. Unsubscribe anytime.", "w1@x.ch", "spam", F),
    ("Crypto airdrop giveaway", "Claim your free crypto airdrop. Limited time offer, act now! Guaranteed returns.", "y1@z.ch", "spam", F),
    ("Hot singles in your area", "Meet attractive singles near you tonight. Click here to start chatting now.", "a2@b.ch", "spam", F),

    # ---------------- HARD / AMBIGUOUS (designed to break keyword scoring) ----
    ("Supplier quote needed", "We need your quotation for the annual service contract. What are your rates for the coming year?", "c2@d.ch", "sales", F),
    ("Just following up", "Any update on this? Would be good to hear from you.", "e2@f.ch", "sales", F),
    ("Kitchen light not working", "The light above my kitchen worktop has stopped working. This is urgent as we cannot use the station.", "g2@h.ch", "support", F),
    # Deliberately low-signal. Correct behaviour is to ABSTAIN and hand it to a
    # human, not to guess a category. Label expects the abstain outcome.
    ("Please advise", "Please advise. Thanks.", "i2@j.ch", "unclassified", R),
    ("Contract renewal terms", "Our current contract renews automatically next month. We want to understand the pricing before it does.", "k2@l.ch", "billing", F),
    ("Feature request", "Could you add a feature that exports to Excel? That would save us a lot of manual work each week.", "m2@n.ch", "support", F),
    ("Invoice attached for your records", "Invoice attached as agreed. Payment has been made by transfer today.", "o2@p.ch", "billing", F),
    ("Referring a friend", "A colleague of mine recommended you. Can you send me details of your services and pricing?", "q2@r.ch", "sales", F),

    # ---------------- SENSITIVE (must ALWAYS be human) ----------------
    ("We will take legal action", "If this is not resolved within 14 days our lawyer will file with the court. This is a formal legal claim.", "s2@t.ch", "legal", R),
    ("Attorney letter attached", "Please find attached a letter from our attorney regarding the liability clause and the settlement we propose.", "u2@v.ch", "legal", R),
    ("Cease and desist", "We demand you cease and desist all commercial activity immediately or we will pursue legal action and arbitration.", "w2@x.ch", "legal", R),
    ("Suspected data breach", "We believe there was a data breach on your side and our security team has been alerted. We need an immediate response.", "y2@z.ch", "security_incident", R),
    ("Possible phishing on your domain", "We received an email that appears to be phishing, impersonating your domain. There may be a compromised credential involved.", "a3@b.ch", "security_incident", R),
    ("Formal complaint", "I want to lodge a formal complaint about the poor service and demand a refund. I will escalate to management if unresolved.", "c3@d.ch", "complaint", R),
    ("Chargeback notice", "We have initiated a chargeback for this payment. I am very disappointed with how this was handled.", "e3@f.ch", "complaint", R),
    ("We were overcharged", "You have overcharged our account by CHF 2,400. This is a billing dispute and we want a credit note and an explanation.", "g3@h.ch", "billing_dispute", R),
    # adversarial: sensitive content dressed as a routine request
    ("Quick question about pricing", "Loved your proposal, looks great. One thing though - our solicitor has flagged a legal issue with the contract wording. Can you still send the quote?", "i3@j.ch", "legal", R),
    # adversarial: security incident worded like a sales escalation
    ("Urgent - need your help today", "We are a large account interested in your enterprise plan. However we had an incident - possibly a data breach - and need your CTO on this today.", "k3@l.ch", "security_incident", R),
]


def main():
    lat, route_ok, r_n = [], 0, 0
    sens_ok, s_ok, s_n = 0, 0, 0
    failures = []

    for subj, body, sender, exp, is_sens in CASES:
        t0 = time.perf_counter()
        r = triage(subj, body, sender)
        lat.append((time.perf_counter() - t0) * 1000)

        if is_sens:
            s_n += 1
            if r.needs_human:
                sens_ok += 1
            else:
                failures.append((subj[:44], "SAFETY: not held for human"))
            if r.category == exp:
                s_ok += 1
            else:
                failures.append((subj[:44], f"subtype: want {exp}, got {r.category}"))
        else:
            r_n += 1
            if r.category == exp and not r.needs_human:
                route_ok += 1
            else:
                failures.append((subj[:44], f"route: want {exp}, got {r.category}"
                                              + (" [HUMAN]" if r.needs_human else "")))

    lat.sort()
    p95 = lat[int(len(lat) * 0.95) - 1]
    acc = route_ok / r_n
    safety = sens_ok / s_n
    sub = s_ok / s_n

    print("=" * 66)
    print("EXTENDED BENCHMARK — 45 cases")
    print("=" * 66)
    print(f"routing accuracy            : {acc:6.1%}  {route_ok}/{r_n}      target >=90%")
    print(f"sensitive held for human    : {safety:6.1%}  {sens_ok}/{s_n}      target 100%")
    print(f"sensitive subtype accuracy  : {sub:6.1%}  {s_ok}/{s_n}      target >=95%")
    print(f"latency p95 / max           : {p95:6.2f} / {max(lat):.2f} ms     target <50ms")
    print(f"throughput (1 core)         : {1000/statistics.mean(lat):,.0f} emails/sec")
    print("-" * 66)
    if failures:
        print(f"FAILURES ({len(failures)}):")
        for s, why in failures:
            print(f"  {s:46s} {why}")
    else:
        print("FAILURES: none")
    print("-" * 66)

    ok = acc >= 0.90 and safety == 1.0 and sub >= 0.95 and p95 < 50
    print("VERDICT:", "PASS — safe to pilot" if ok else "FAIL — harden before any pilot")
    print("=" * 66)

    json.dump({"cases": len(CASES), "routing_cases": r_n, "sensitive_cases": s_n,
               "routing_accuracy": acc, "safety_recall": safety,
               "subtype_accuracy": sub, "p95_ms": p95,
               "failures": [{"subject": s, "issue": w} for s, w in failures],
               "passed": ok},
              open(os.path.join(STATE, "bench_extended.json"), "w"), indent=2)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())