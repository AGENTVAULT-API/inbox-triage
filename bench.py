#!/usr/bin/env python3
"""Accuracy + speed benchmark for the triage engine.

Success criteria for the demo (set BEFORE running):
  >= 85%  correct routing category on the labelled set
  100%   recall on HUMAN_ONLY subtypes (never auto-action sensitive mail)
  < 50ms  p95 latency per email
Kill criterion: if category accuracy < 70%, the rules approach is wrong and we
re-scope to a narrower pilot category rather than shipping a bad demo.
"""
import json, time, statistics, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from triage import triage

# The repo is meant to be cloned and run, so never assume a state/ directory
# exists — create it. A benchmark that crashes on a fresh clone instead of
# printing its results is a worse first impression than any result.
STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state")
os.makedirs(STATE, exist_ok=True)

CASES = [
    # (subject, body, sender, expected_category, expected_needs_human)
    ("Quote request for 40 units",
     "Hi, we need a quote for 40 units delivered to Zurich. What is your pricing "
     "and lead time? We would like to start next month. Regards, Peter Keller, "
     "Keller Logistik GmbH, phone 044 221 45 67", "peter@kellerlogistik.ch",
     "sales", False),

    ("Appointment change needed",
     "Hello, I need to reschedule my appointment for Friday to next Tuesday "
     "morning. Can you confirm? Also my phone is 079 123 45 67. Thanks, Anna",
     "anna.rei@example.ch", "support", False),

    ("Cannot log in since this morning",
     "Hi team, I cannot log into the portal since this morning. It shows an error. "
     "This is blocking our team. Please advise. Best, Marco",
     "marco@beispiel.ch", "support", False),

    ("Invoice 2026-118 payment query",
     "Hello, regarding invoice 2026-118 — could you send the receipt and confirm "
     "the payment terms and VAT number? Thanks, Finance",
     "finance@client.ch", "billing", False),

    # --- SENSITIVE CASES ---
    # The assertion is twofold and BOTH must hold:
    #   (1) needs_human is True  — never auto-actioned
    #   (2) the specific subtype is correct — so it reaches the right human
    # The business category (billing/support) is intentionally NOT asserted
    # here, because the safety gate overrides it by design.
    ("Overcharged on latest invoice",
     "I do not recognise this amount. You have overcharged me on the latest invoice "
     "and I want a credit note. This is a billing dispute and I am escalating.",
     "dispute@client.ch", "billing_dispute", True),

    ("We received a legal notice",
     "Our solicitor has issued a legal notice regarding the liability clause. "
     "Please direct all correspondence to our attorney.",
     "law@client.ch", "legal", True),

    ("Complaint about service",
     "I am very unhappy with the service. This is a formal complaint and I want "
     "a refund. I will be posting reviews otherwise.",
     "unhappy@client.ch", "complaint", True),

    ("URGENT: data breach, need response",
     "This is urgent. We believe there was a data breach on your side. We need an "
     "immediate response and an escalation to your CTO today.",
     "ciso@enterprise.com", "security_incident", True),

    # Adversarial: sensitive language wrapped in a sales request. The safety gate
    # must still win over the sales category. This is the exact failure the
    # first version of the engine had.
    ("Great opportunity - please send proposal",
     "Hi, I love your pricing and would like to discuss a contract and a proposal "
     "for our whole team. However our attorney has issued a legal notice which we "
     "must resolve first. Please send the quote.",
     "buyer@corp.com", "legal", True),

    # --- END SENSITIVE ---
    ("CV application — Sales role",
     "Dear HR, please find attached my CV and references for the advertised sales "
     "position. I am available for interview next week.",
     "candidate@mail.com", "recruitment", False),

    ("Interview request from journalist",
     "Hello, I am a journalist writing a feature on your industry and would like "
     "an interview with your founder for publication next month.",
     "reporter@press.com", "press", False),

    ("Limited time offer!!! Act now",
     "Congratulations you! Click here for a crypto giveaway. Guaranteed returns, "
     "unsubscribe at any time. Work from home and earn thousands.",
     "noreply@spam.biz", "spam", False),

    ("Re: invoice payment overdue reminder",
     "This is a payment reminder that invoice 1055 is overdue. Please arrange "
     "payment immediately to avoid further action.",
     "ar@vendor.ch", "billing", False),

    ("Guest post SEO backlinks offer",
     "We offer SEO services and guest post backlinks for your website. Buy "
     "followers cheap. Act now with our limited time offer.",
     "seo@spam.biz", "spam", False),

    ("Quick question about your services",
     "Hello, I have a question about your services for our team. Do you offer "
     "onboarding for companies our size? Best regards, Lukas",
     "l.keller@mid.ch", "sales", False),

    ("FYI rota for next month",
     "FYI team - here is the rota for next month, please check your shifts. "
     "Internal only. Minutes attached.",
     "ops@internal.ch", "internal", False),
]

latencies, cat_ok, human_ok, human_total, subtype_ok = [], 0, 0, 0, 0
failures = []

for subj, body, sender, exp_cat, exp_human in CASES:
    t0 = time.perf_counter()
    r = triage(subj, body, sender)
    latencies.append((time.perf_counter() - t0) * 1000)

    # SAFETY assertion, checked first and independently: is any sensitive
    # message ever allowed through the gate?
    if exp_human:
        human_total += 1
        if r.needs_human:
            human_ok += 1
        else:
            failures.append((subj[:42], "SAFETY FAIL: sensitive mail not held for human"))
        if r.category == exp_cat:
            subtype_ok += 1
        else:
            failures.append((subj[:42],
                             f"subtype: expected {exp_cat}, got {r.category}"))
    else:
        ok = (r.category == exp_cat) and (not r.needs_human)
        cat_ok += ok
        if not ok:
            failures.append((subj[:42], f"expected {exp_cat}, got {r.category}"))

latencies.sort()
p95 = latencies[int(len(latencies) * 0.95) - 1]
# Non-sensitive cases only for routing accuracy, so sensitive subtypes don't
# inflate the score with cases measured by a different metric.
cat_acc = cat_ok / (len(CASES) - human_total)
safety_recall = (human_ok / human_total) if human_total else 1.0
subtype_acc = (subtype_ok / human_total) if human_total else 1.0

print("=" * 62)
print("TRIAGE ENGINE BENCHMARK")
print("=" * 62)
print(f"cases                      : {len(CASES)} ({len(CASES)-human_total} routing, "
      f"{human_total} sensitive)")
print(f"routing accuracy           : {cat_acc:.0%}  ({cat_ok}/{len(CASES)-human_total})"
      f"          target >=85%")
print(f"sensitive held for human   : {safety_recall:.0%}  ({human_ok}/{human_total})"
      f"        target 100%")
print(f"sensitive subtype accuracy : {subtype_acc:.0%}  ({subtype_ok}/{human_total})"
      f"         target 100%")
print(f"latency mean/p95/max       : {statistics.mean(latencies):.2f} / {p95:.2f} / "
      f"{max(latencies):.2f} ms        target p95 <50ms")
print(f"throughput                 : {1000/statistics.mean(latencies):,.0f} emails/sec")
print("-" * 62)
if failures:
    print("FAILURES:")
    for s, why in failures:
        print(f"  - {s:44s} {why}")
else:
    print("FAILURES: none")
print("-" * 62)

passes = cat_acc >= 0.85 and safety_recall == 1.0 and subtype_acc == 1.0 and p95 < 50
print("VERDICT:", "PASS - demo is credible" if passes else "FAIL - re-scope or fix")
print("=" * 62)

json.dump({"cases": len(CASES), "routing_cases": len(CASES) - human_total,
           "sensitive_cases": human_total, "routing_accuracy": cat_acc,
           "safety_recall": safety_recall, "subtype_accuracy": subtype_acc,
           "p95_ms": p95, "failures": failures, "passed": passes},
          open(os.path.join(STATE, "bench.json"), "w"), indent=2)