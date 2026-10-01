# inbox-triage

Deterministic email triage for shared inboxes (`info@`, `office@`, `support@`).

Not an LLM wrapper. A transparent, auditable rules engine that classifies inbound
mail, routes it with an SLA, extracts the details a reply needs, and **drafts**
a response for a human to send.

Zero dependencies. Python standard library only.

```bash
python3 triage.py            # reads one message as JSON on stdin
python3 bench.py             # 16-case benchmark
python3 bench_extended.py    # 48-case adversarial benchmark
python3 server.py            # local demo on 127.0.0.1:8090
```

## Why rules and not a model

Because the output has to be *defensible*. A client asking "why did this customer
email get routed to billing?" needs an answer that is a sentence, not a confidence
score. Keyword scoring with recorded matched signals is reviewable by the person
who owns the inbox — and when it is wrong, they can see exactly which word
triggered it and correct it.

It also means no API cost per message, no data leaving the machine, and no
behaviour change when a model version ships.

## The part that matters most: it fails closed

Before any routing decision is made, the whole message is scanned for signals that
must never be auto-actioned:

| Subtype | Examples |
|---|---|
| `security_incident` | data breach, compromised credential, NCSC, ransomware |
| `legal` | solicitor, attorney, legal notice, cease and desist, litigation |
| `billing_dispute` | overcharge, unrecognised charge, billing dispute |
| `complaint` | formal complaint, refund, chargeback, escalate to management |

Any hit returns `hold_for_human` with `needs_human: true` and **no** draft — and
this check runs *before* category ranking, so sensitive mail cannot slip through
because it happened to read like a sales enquiry.

This is the single most important design decision in the codebase, and it exists
because the first version got it wrong: v1 classified first and checked for
sensitive content afterwards, so a legal notice phrased in sales language was
routed as a sales enquiry and would have been auto-actioned. There is now an
adversarial regression case for exactly that input, because it will not stay fixed
by accident.

```json
{
  "subject": "Great opportunity - please send proposal",
  "body": "...I love your pricing and would like to discuss a contract... However our attorney has issued a legal notice which we must resolve first.",
  "sender": "buyer@corp.com"
}
```
```json
{
  "category": "legal", "urgency": "P1", "needs_human": true,
  "action": "hold_for_human", "reply": null,
  "reason": "SAFETY: legal detected (attorney, legal notice) — category-independent gate, no auto-action permitted"
}
```

## It also abstains

If the winning category scores below `MIN_CONFIDENCE` (default 3.0), the engine
returns `unclassified` and holds for a human instead of guessing.

That came from a benchmark failure worth reading: `"Please advise."` was being
routed confidently as *sales* — purely because `sales` happened to be first in a
dictionary. A pilot's entire promise is that routing is trustworthy, and "I don't
know, ask a person" beats a confident guess. Low signal now produces an abstention.

## Measured

Both suites are reproducible; run them yourself.

| Suite | Cases | Routing | Sensitive held | Subtype | p95 |
|---|---|---|---|---|---|
| `bench.py` | 16 (11 routing / 5 sensitive) | 100% | 100% | 100% | 0.18 ms |
| `bench_extended.py` | 48 (34 routing / 14 sensitive) | 100% | 100% | 100% | 0.14 ms |

Throughput ~7,700 messages/sec on one core.

**These are the project's own benchmarks on synthetic messages written by the
author. They are not customer results.** The first real mailbox behaves differently;
finding out how is the point of the pilot.

Pass criteria are defined in each benchmark file *before* it runs, including the
kill criterion — if routing accuracy drops below 80% the architecture is wrong and
the pilot should narrow to one category rather than ship.

## What it will not do

- Send anything. Ever. `draft_reply` is a suggestion for a human.
- Auto-answer a complaint, legal notice, billing dispute or security incident.
- Train a model, call a third-party API, or send mail content anywhere. Local only.

## Design notes

- Client policy lives in `config.json`, not in code — changing a client's routing
  must not mean editing the engine.
- Every classification is logged with its matched signals: auditable by design.
- The demo server binds to `127.0.0.1` by default and deliberately refuses to be
  a public development server.

## Licence

MIT.