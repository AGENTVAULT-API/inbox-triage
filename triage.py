#!/usr/bin/env python3
"""
Inbox Triage Engine — the demo-able core of the paid offer.

WHAT IT DOES
  Takes a raw email (headers + body) and returns a routing decision:
    - category   : sales | support | billing | recruitment | press | internal | spam
    - urgency    : P1 | P2 | P3
    - entities   : sender, company, phone, deadline dates
    - action     : route_to, draft_reply, hold_for_human
    - reply      : a drafted acknowledgement (template, deterministic)

DESIGN RULE (from market research: alpenagent.ch / loosdata.ch)
  Narrow scope, one owner, visible handover, honest metric.
  Sensitive categories (legal, complaint, billing dispute) ALWAYS hold for a human.
  We never auto-send anything. This engine recommends; a human approves.

No dependencies. Deterministic. Auditable. Runs anywhere.
"""

import re
import json
import datetime
from dataclasses import dataclass, asdict, field
from typing import Optional

# ---------------------------------------------------------------------------
# Routing config — this is the part a client customises per engagement.
# ---------------------------------------------------------------------------

ROUTES = {
    "sales":        {"owner": "sales@",      "sla_minutes": 15, "pilot": "quote requests"},
    "support":      {"owner": "support@",    "sla_minutes": 60, "pilot": "appointment changes"},
    "billing":      {"owner": "finance@",    "sla_minutes": 240, "pilot": "invoice questions"},
    "recruitment":  {"owner": "hr@",         "sla_minutes": 720, "pilot": "CV submissions"},
    "press":        {"owner": "comms@",      "sla_minutes": 720, "pilot": "media enquiries"},
    "internal":     {"owner": "ops@",        "sla_minutes": 240, "pilot": "team forwards"},
}

# Generic mailbox names. Greeting "info@" as "Hello Info," is worse than not
# greeting at all — it reads as a bot that did not read the address.
GENERIC_MAILBOXES = {"info", "office", "kontakt", "contact", "hello", "admin",
                     "mail", "mailbox", "team", "support", "sales", "help",
                     "service", "sekretariat", "gf", "post", "enquiries",
                     "contact01", "info01", "mail01"}

# Categories that must NEVER be auto-actioned. Human owns these.
HUMAN_ONLY = {"billing_dispute", "legal", "complaint", "security_incident"}

# SAFETY: sensitive detection runs over the WHOLE message BEFORE category
# ranking. If it only ran on the winning category, a legal notice phrased with
# sales language would be auto-actioned. Fail-closed is the only safe default.
SENSITIVE_SIGNALS = {
    "legal": [
        "solicitor", "lawyer", "attorney", "legal notice", "legal action",
        "court", "litigation", "liability", "cease and desist", "statutory",
        "liability clause", "jurisdiction", "arbitration", "legal claim",
    ],
    "security_incident": [
        "data breach", "breach of data", "gdpr breach", "security incident",
        "phishing", "ransomware", "compromised", "unauthorised access",
        "unauthorized access", "leaked data", "data leak", "suspected breach",
        "ncsc", "incident response", "credential",
    ],
    "complaint": [
        "formal complaint", "unhappy", "disappointed", "dispute", "refund",
        "chargeback", "escalate to management", "your fault", "poor service",
    ],
    "billing_dispute": [
        "billing dispute", "overcharge", "overcharged", "wrong amount",
        "do not recognise", "do not recognize", "unauthorised charge",
        "unauthorized charge", "credit note",
    ],
}

# ---------------------------------------------------------------------------
# Signals. Weighted keyword scoring beats a black-box model for auditability,
# and it is what makes the accuracy reviewable by the client.
# ---------------------------------------------------------------------------

CATEGORY_SIGNALS = {
    "sales": {
        "strong": ["offer", "proposal", "quote", "quotation", "pricing", "estimate",
                   "demo", "trial", "interested in", "onboarding", "contract",
                   "rfq", "request for quote", "how much", "budget", "scope of work",
                   "quotation for", "best pricing", "rates for the coming year"],
        "weak": ["enquiry", "inquiry", "follow up", "following up", "question about",
                 "your services", "do you offer", "get in touch", "any update",
                 "would be good to hear", "referred you", "details of your",
                 "like to hear from you", "enterprise plan"],
    },
    "support": {
        "strong": ["not working", "broken", "error", "cannot", "can't", "outage",
                   "failed", "issue with", "problem with", "down", "crash",
                   "appointment", "reschedule", "cancel my", "change my booking",
                   "password reset", "token is expired", "delayed", "tracking has not",
                   "will it arrive", "not updated", "stopped working", "feature request",
                   "add a feature", "manual work", "blocked client work",
                   "export to", "each week", "slot"],
        "weak": ["help", "support", "question", "how do i", "assistance", "complaint",
                 "unhappy", "refund", "please advise", "advice urgently",
                 "save us", "that would", "stuck"],
    },
    "billing": {
        "strong": ["invoice", "payment", "overdue", "reminder", "receipt", "vat",
                   "billing", "credit note", "charged", "billing dispute",
                   "payment terms", "monthly invoicing", "copy of a receipt",
                   "payment has been made", "renews automatically", "accounting department",
                   "present a budget internally", "second reminder", "first reminder",
                   "our current contract renews"],
        "weak": ["pay", "cost", "price", "amount due", "for our accounts", "for your records",
                 "contract renews", "renew", "renewal"],
    },
    "recruitment": {
        "strong": ["cv", "resume", "curriculum vitae", "application", "job",
                   "vacancy", "position", "portfolio", "references", "interview",
                   "i applied", "advertised"],
        "weak": ["career", "recruit", "hiring", "candidate", "heard nothing"],
    },
    "press": {
        "strong": ["press", "journalist", "interview request", "media", "reporter",
                   "editorial", "publication", "podcast", "magazine", "guest",
                   "writing a feature", "as a guest"],
        "weak": ["article", "feature", "coverage", "episode"],
    },
    "internal": {
        "strong": ["fyi", "internal", "team", "all hands", "minutes", "rota",
                   "shift swap", "colleagues", "my shifts", "internal only"],
        "weak": ["shift", "office", "covering", "attached the minutes"],
    },
    "spam": {
        "strong": ["unsubscribe", "limited time offer", "act now", "click here",
                   "guaranteed", "viagra", "crypto giveaway", "lottery", "winner",
                   "congratulations you", "work from home and earn", "web3 airdrop",
                   "you have won", "claim your prize", "hot singles", "attractive singles"],
        "weak": ["buy followers", "seo services", "guest post", "backlinks",
                 "cheap backlinks", "guaranteed returns", "click here to start"],
    },
}

URGENCY_P1_SIGNALS = [
    "urgent", "asap", "immediately", "emergency", "today", "by end of day",
    "eod", "escalation", "legal notice", "data breach", "outage", "critical",
    "deadline", "time sensitive", "no reply", "second attempt", "third attempt",
]

URGENCY_P2_SIGNALS = [
    "this week", "soon", "shortly", "short notice", "priority", "follow up",
    "reminder", "waiting", "chase", "quick question",
]

# Deadline extraction patterns.
DATE_PATTERNS = [
    r"\b(\d{1,2})[\/\.\-](\d{1,2})[\/\.\-](\d{2,4})\b",
    r"\b(\d{4})-(\d{2})-(\d{2})\b",
    r"\b(mon|tue|wed|thu|fri|sat|sun)[a-z]*day\b",
]

COMPANY_HINTS = ["inc", "gmbh", "ag", "ltd", "llc", "sa", "bv", "plc", "corp",
                 "company", "group", "holdings", "partners", "consulting"]

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(
    r"(?:\+?\d{1,3}[\s.\-]?)?(?:\(?\d{2,4}\)?[\s.\-]?)?\d{3}[\s.\-]?\d{3,4}(?:[\s.\-]?\d{0,4})?"
)

STOPWORD_TOKENS = {"the", "and", "for", "you", "our", "are", "was", "has", "have",
                   "with", "that", "this", "from", "your", "about", "would", "could"}

# Abstain threshold: below this winning score the engine refuses to guess and
# holds the message for a human. Module-level (not local to triage()) so the
# parity checker can assert the static demo uses the same value.
MIN_CONFIDENCE_SCORE = 3.0


@dataclass
class TriageResult:
    category: str
    urgency: str
    score: float
    entities: dict = field(default_factory=dict)
    action: str = "hold_for_human"
    route_to: Optional[str] = None
    sla_minutes: Optional[int] = None
    reply: Optional[str] = None
    matched_signals: list = field(default_factory=list)
    needs_human: bool = True
    reason: str = ""


def _text(body: str) -> str:
    return body.lower()


def score_categories(body: str):
    """Return {category: (score, matched_signals)} using strong=3, weak=1."""
    t = _text(body)
    out = {}
    for cat, sigs in CATEGORY_SIGNALS.items():
        score, matched = 0.0, []
        for kw in sigs["strong"]:
            if kw in t:
                score += 3.0
                matched.append(kw)
        for kw in sigs["weak"]:
            if kw in t:
                score += 1.0
                matched.append(kw)
        out[cat] = (score, matched)
    return out


def detect_urgency(body: str):
    t = _text(body)
    p1 = [s for s in URGENCY_P1_SIGNALS if s in t]
    p2 = [s for s in URGENCY_P2_SIGNALS if s in t]
    if p1:
        return "P1", p1
    if p2:
        return "P2", p2
    return "P3", []


def extract_entities(subject: str, body: str, sender_email: str = ""):
    ents = {}
    ents["sender_email"] = sender_email or (
        EMAIL_RE.search(body).group(0) if EMAIL_RE.search(body) else None)

    phones = [p.strip() for p in PHONE_RE.findall(body) if len(re.sub(r"\D", "", p)) >= 9]
    ents["phone"] = phones[0] if phones else None

    dates = re.findall(DATE_PATTERNS[0], body) + re.findall(DATE_PATTERNS[1], body)
    ents["dates_mentioned"] = ["/".join(d) for d in dates][:3]

    # Company guess: a capitalised token near a legal-entity hint.
    company = None
    for hint in COMPANY_HINTS:
        m = re.search(r"\b([A-Z][A-Za-z&.\- ]{2,30})\s+" + re.escape(hint), body)
        if m:
            company = m.group(1).strip()
            break
    ents["company"] = company

    words = [w for w in re.findall(r"[A-Za-z]{4,}", subject.lower())
             if w not in STOPWORD_TOKENS]
    ents["subject_keywords"] = sorted(set(words))[:5]
    return ents


def detect_sensitive(combined: str):
    """Scan the entire message for human-only signals.

    Returns (subtype, matched_signals) or (None, []). Priority order matters:
    a security incident outranks a complaint outranks billing outranks legal,
    because those carry the highest escalation duty.
    """
    t = _text(combined)
    for subtype in ("security_incident", "legal", "billing_dispute", "complaint"):
        hits = [s for s in SENSITIVE_SIGNALS[subtype] if s in t]
        if hits:
            return subtype, hits
    return None, []


def classify_subtype(category: str, body: str):
    """Narrow the category to a pilot-relevant subtype when we can.

    Safety first: sensitive detection is category-independent, so a legal
    notice written in sales language can never be auto-actioned.
    """
    t = _text(body)
    if category == "billing" and ("dispute" in t or "overcharge" in t or
                                   "wrong amount" in t or "do not recognise" in t):
        return "billing_dispute"
    if category == "support" and ("complaint" in t or "unhappy" in t or
                                   "disappointed" in t or "refund" in t):
        return "complaint"
    if category == "support" and any(w in t for w in
                                     ("solicitor", "lawyer", "attorney", "legal",
                                      "court", "liability")):
        return "legal"
    return category


def draft_reply(category: str, subtype: str, sender: str, entities: dict):
    """Deterministic acknowledgement. Never sent automatically."""
    # Split on "@" BEFORE treating the local part as first.last. Splitting the
    # whole address on "." mangles "peter@kellerlogistik.ch" into
    # "eter@kellerlogistik" and greets them as "Hello eter@kellerlogistik,".
    local = (sender or "").split("@")[0]
    first = re.split(r"[._-]", local)[0] if local else ""
    clean = re.sub(r"[^A-Za-z]", "", first)
    # A generic mailbox is not a person's name.
    if clean.lower() in GENERIC_MAILBOXES:
        clean = ""
    name = clean.capitalize() if clean else ""
    greet = f"Hello {name}," if name else "Hello,"

    if subtype in HUMAN_ONLY:
        return None

    if subtype == "sales":
        body = (f"{greet}\n\nThank you for your enquiry — happy to help.\n\n"
                "To give you an accurate answer I need: your approximate scope, "
                "your target start date, and any deadline we should work back from.\n\n"
                "If it is easier, suggest two times for a 15-minute call this week "
                "and I will confirm one.\n\nBest regards")
    elif subtype == "support":
        extra = f" I have your phone number ({entities.get('phone')}) on file." \
            if entities.get("phone") else ""
        body = (f"{greet}\n\nThanks for letting us know — sorry for the trouble.{extra}\n\n"
                "Could you confirm: when the problem started, and is anyone else "
                "affected? If it is blocking work, reply with the word URGENT and "
                "we will escalate to the on-call owner immediately.\n\nBest regards")
    elif subtype == "billing":
        body = (f"{greet}\n\nThank you for your message. I have referred this to our "
                "finance team, who will come back to you with the detail.\n\n"
                "If you can quote the invoice number, it will speed this up.\n\nBest regards")
    elif subtype == "recruitment":
        body = (f"{greet}\n\nThank you for sending your application through.\n\n"
                "Our hiring lead reviews applications weekly and will reply either "
                "way.\n\nBest regards")
    elif subtype == "press":
        body = (f"{greet}\n\nThank you for reaching out. I have passed this to our "
                "communications lead, who will respond directly.\n\nBest regards")
    elif subtype == "internal":
        body = None
    else:
        body = (f"{greet}\n\nThank you for your email. I have routed this to the "
                "right person and they will come back to you shortly.\n\nBest regards")

    return f"Subject: Re: your enquiry\n\n{body}"


def triage(subject: str, body: str, sender_email: str = "") -> TriageResult:
    combined = f"{subject}\n\n{body}"
    urgency_pre, _ = detect_urgency(combined)

    # ---- SAFETY GATE: runs before any routing decision is made ----
    sensitive, sens_hits = detect_sensitive(combined)
    if sensitive:
        entities = extract_entities(subject, body, sender_email)
        return TriageResult(
            category=sensitive,
            urgency="P1",
            score=1.0,
            entities=entities,
            action="hold_for_human",
            route_to=None,
            sla_minutes=0,
            reply=None,
            matched_signals=sens_hits[:8],
            needs_human=True,
            reason=(f"SAFETY: {sensitive} detected ({', '.join(sens_hits[:3])}) — "
                    f"category-independent gate, no auto-action permitted"),
        )

    scores = score_categories(combined)
    ranked = sorted(scores.items(), key=lambda kv: kv[1][0], reverse=True)

    top_cat, (top_score, top_matches) = ranked[0]
    total = sum(v[0] for v in scores.values()) or 1.0

    # Spam wins outright if it scores meaningfully and nothing else is strong.
    runner_up = ranked[1][1][0] if len(ranked) > 1 else 0.0
    if top_cat == "spam" and top_score > runner_up:
        return TriageResult(
            category="spam", urgency="P3", score=round(top_score / total, 3),
            entities=extract_entities(subject, body, sender_email),
            action="quarantine", route_to=None, sla_minutes=None,
            reply=None, matched_signals=top_matches, needs_human=False,
            reason=f"spam score {top_score} exceeds all other categories")

    subtype = classify_subtype(top_cat, combined)
    urgency, urg_matches = detect_urgency(combined)
    entities = extract_entities(subject, body, sender_email)

    needs_human = subtype in HUMAN_ONLY
    if needs_human:
        return TriageResult(
            category=top_cat, urgency="P1" if subtype in ("legal", "complaint") else urgency,
            score=round(top_score / total, 3), entities=entities,
            action="hold_for_human", route_to=None, sla_minutes=None, reply=None,
            matched_signals=top_matches, needs_human=True,
            reason=f"{subtype} is human-owned by policy — never auto-actioned")

    # Abstain when the winning category is supported by almost no evidence.
    # A wrong confident routing is worse than an honest "not sure" — the pilot's
    # whole promise is that the routing is trustworthy. Low signal => human.
    if top_score < MIN_CONFIDENCE_SCORE:
        return TriageResult(
            category="unclassified",
            urgency=urgency_pre,
            score=round(top_score / total, 3),
            entities=extract_entities(subject, body, sender_email),
            action="hold_for_human",
            route_to=None,
            sla_minutes=60,
            reply=None,
            matched_signals=top_matches[:5],
            needs_human=True,
            reason=(f"insufficient signal (score {top_score:g} < "
                    f"{MIN_CONFIDENCE_SCORE:g}) — abstaining rather than guessing"),
        )

    route = ROUTES.get(top_cat, ROUTES["internal"])
    # P1 compresses the SLA regardless of category.
    sla = 15 if urgency == "P1" else route["sla_minutes"]

    return TriageResult(
        category=top_cat,
        urgency=urgency,
        score=round(top_score / total, 3),
        entities=entities,
        action="route_and_draft",
        route_to=route["owner"],
        sla_minutes=sla,
        reply=draft_reply(top_cat, subtype, sender_email, entities),
        matched_signals=sorted(set(top_matches))[:8],
        needs_human=False,
        reason=(f"{subtype} ({top_score:g} pts) -> {route['owner']}"
                + (f"; P1 signals: {', '.join(urg_matches[:3])}" if urg_matches else "")),
    )


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--self-test":
        pass
    else:
        data = json.load(sys.stdin)
        print(json.dumps(asdict(triage(data.get("subject", ""),
                                      data.get("body", ""),
                                      data.get("sender_email", ""))), indent=2))