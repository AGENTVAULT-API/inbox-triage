#!/usr/bin/env python3
"""
SECTOR BENCHMARK — 36 cases of REAL trades / SHK / Elektro vocabulary.

WHY THIS FILE EXISTS
  bench.py (16) and bench_extended.py (48) were both written by me, in English.
  Batch 01 went to Malerbetriebe, Sanitär/Heizung/Klima firms and Elektrobetriebe
  in CH/DE/AT. Their inboxes do not say "please advise" — they say "Störung",
  "Mahnung", "Angebot", "Termin verschoben", "Heizung bleibt kalt".

  The entire existing benchmark is English keyword space. An engine that scores
  100% on English and has never seen "Mahnung" is not 100% on anything real.
  This suite is the first test of the vocabulary the actual pilot clients use.

PASS CRITERIA (fixed BEFORE running, same bars as the extended suite):
  routing accuracy (non-sensitive) >= 85%   (not 90% — this vocabulary is new
         ground and a first pass is allowed to be imperfect; what matters is
         that every failure is found, understood and fixed, not that the
         number starts high)
  sensitive held for human         == 100%   (safety bar, non-negotiable)
  sensitive subtype accuracy       >= 95%
  p95 latency                       < 50 ms

Rule for this file: a case is only labelled after deciding what a careful human
at that trades firm would actually do with the mail. Labels are never written to
match current engine output. If the engine is wrong, the engine changes.
"""
import json, os, statistics, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from triage import triage

STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state")
os.makedirs(STATE, exist_ok=True)

R = True    # sensitive -> human only
F = False

CASES = [
    # ---------------- SALES: Angebotsanfragen (the core revenue email) -------
    ("Angebot Wärmepumpe", "Guten Tag, wir würden gerne für unser Einfamilienhaus in Aarau ein Angebot für den Einbau einer Wärmepumpe erhalten. Können Sie mir Kostenvoranschlag und Termine schicken?", "k.mueller@haustechnik-mueller.ch", "sales", F),
    ("Offerte für Umbau", "Guten Tag, ich plane einen Umbau im Bad und hätte gerne eine Offerte für Sanierung und Heizungsanlage. Wann könnten Sie vorbeikommen?", "b.kaufmann@badumbau-kaufmann.ch", "sales", F),
    ("Preisfrage Gaumen", "Grüezi, wie viel kostet eineOfferte-Stunde bei uns? Wir brauchen den Gaumen gezämmt und heissen. Bitte Preisliste und Konditionen.", "info@gaumen-service.ch", "sales", F),
    ("Anfrage Malerarbeiten Fassade", "Guten Tag, wir suchen einen Malerbetrieb für die Fassade eines 4-Zimmer-Hauses. Können Sie mir ein Angebot machen und Referenzen senden?", "bau@wohnverwlicht.ch", "sales", F),
    ("Elektroinstallation Umbau", "Hallo, ich brauche für einen Küchenumbau die Elektroinstallation erneuert. Bitte Offerte inklusive Material.", "g.frei@elektro-frei.ch", "sales", F),
    ("Angebot für Ladestation", "Guten Tag, ich möchte eine Wallbox/Ladestation installieren lassen. Können Sie mir ein Angebot und eine Offerte senden?", "hausverw@immo-zentrum.ch", "sales", F),

    # ---------------- SUPPORT: Störungsmeldungen (the daily reality) --------
    ("Heizung bleibt kalt", "Guten Tag, seit heute Morgen bleibt die Heizung kalt und es wird im Wohnzimmer langsam kalt. Wann kommt jemand vorbei?", "m.brugger@wohnhaus-brugger.ch", "support", F),
    ("Wasserhahn tropft", "Guten Tag, der Wasserhahn in der Küche tropft seit Tagen. Es ist dringend, wir brauchen das vor dem Wochenende behoben.", "s.meier@shk-meier.ch", "support", F),
    ("Sicherung ausgelöst", "Hallo, im Keller ist die Sicherung ausgelöst und im ganzen Haus ist kein Strom mehr. Dringend, bitte heute noch.", "e.muster@elektro-muster.ch", "support", F),
    ("Termin verschieben", "Guten Tag, der Termin am Donnerstag passt leider nicht mehr. Können wir den Termin auf nächsten Montag verschieben?", "k.mueller@haustechnik-mueller.ch", "support", F),
    ("Terminvergabe Neubesetzung", "Guten Tag, die Schlüsselübergabe wurde verschoben. Können Sie mir einen neuen Termin vorschlagen?", "woh@baugenossenschaft.ch", "support", F),
    ("Defektes Heizungsventil", "Guten Tag, das Thermostatventil im Schlafzimmer ist defekt und das Heizungsventil klemmt. Bitte um einen Termin.", "b.kaufmann@badumbau-kaufmann.ch", "support", F),
    ("Kein Warmwasser", "Guten Tag, wir haben seit zwei Tagen kein Warmwasser. Das Warmwasser funktioniert nicht mehr. Dringend bitte.", "info@shk-bern.ch", "support", F),

    # ---------------- BILLING: Rechnung / Mahnung ---------------------------
    ("Rechnung fehlt", "Guten Tag, wir haben die Arbeit ausgeführt, aber die Rechnung ist nie bei uns eingetroffen. Bitte senden Sie uns die Rechnung nochmals.", "verwaltung@immopartner-ag.ch", "billing", F),
    ("Zweite Mahnung", "Guten Tag, dies ist die zweite Mahnung. Die Rechnung ist weiterhin überfällig. Bitte überweisen Sie den Betrag bis zum Zahlungsziel.", "kreditoren@alpincorp.ch", "billing", F),
    ("Quittung für Buchhaltung", "Grüezi, wir brauchen eine Quittung für unsere Buchhaltung und den Beleg zur Rechnung für das letzte Quartal.", "admin@stiftung-lakeside.ch", "billing", F),
    ("Zahlung überwiesen", "Guten Tag, die Zahlung wurde heute überwiesen. Bitte bestätigen Sie den Eingang und schicken Sie die Rechnung mit dem bezahlten Betrag.", "b.kaufmann@badumbau-kaufmann.ch", "billing", F),

    # ---------------- RECRUITMENT: Bewerbung / Lehrling ---------------------
    ("Bewerbung Lehrling Sanitär", "Guten Tag, hiermit bewerbe ich mich um die ausgeschriebene Lehrstelle als Sanitärfachmann. Mein Lebenslauf ist beigefügt. Über eine Einladung zur Besichtigung freue ich mich.", "l.meier@web.de", "recruitment", F),
    ("Offene Stelle Elektriker", "Guten Tag, ist die Stelle als Elektriker bei Ihnen noch offen? Ich habe mich vor drei Wochen beworben und bisher nichts gehört.", "g.frei@elektro-frei.ch", "recruitment", F),
    ("Gesuch um Praktikum", "Guten Tag, ich mache mein Matura im Sommer und suche eine Praktikumsstelle. Hätten Sie eine Möglichkeit in Ihrem Betrieb?", "s.bernhard@gmx.ch", "recruitment", F),

    # ---------------- PRESS: Redaktion / Bericht ----------------------------
    ("Interviewanfrage Regionalzeitung", "Guten Tag, ich schreibe für das Regionalblatt einen Artikel über Handwerksbetriebe in der Region und würde Ihren Inhaber gern zu einem Interview bitten. Welche Termine sind möglich?", "redaktion@regionalblatt.ch", "press", F),
    ("Beitrag für Fachmagazin", "Guten Tag, unser Fachmagazin plant einen Beitrag über Sanierung und Wärmetechnik. Gäbe es einen kleinen Beitrag von Ihnen für das nächste Heft?", "redaktion@bau-magazin.ch", "press", F),

    # ---------------- INTERNAL: Schichtplan / Einsatz -----------------------
    ("Schichtplan diese Woche", "Grüezi zusammen, der Schichtplan für diese Woche ist fertig. Bitte schaut ihn an, und wer die Spätschicht am Donnerstag tauschen kann, meldet sich bei mir. Team, danke.", "dispo@haustechnik-mueller.ch", "internal", F),
    ("Interne Mitteilung", "Hallo Kollegen, nur zur Info: die Materialbestellung ist angekommen und im Lager. Bitte bei Bedarf entnehmen. Nicht weiterleiten.", "lager@shk-meier.ch", "internal", F),

    # ---------------- SPAM --------------------------------------------------
    ("SEO Angebot", "Wir bieten Ihnen günstige SEO Dienstleistungen, Backlinks und bezahlte Gastbeiträge. Jetzt Angebot sichern und Klicks steigern!", "seo@rank-boost.example", "spam", F),
    ("Gewinnspiel", "Herzlichen Glückwunsch, Sie haben ein Gewinnspiel gewonnen und einen Preis abgeholt. Jetzt Claim gewinnen und finanziell unabhängig werden!", "gewinn@preise.example", "spam", F),

    # ---------------- SENSITIVE: must ALWAYS be human -----------------------
    ("Mahnung mit Anwaltsschreiben", "Guten Tag, wir haben bereits zweimal gemahnt. Unser Anwalt hat Ihnen ein Anwaltsschreiben geschickt. Wenn nicht sofort gezahlt wird, klären wir das gerichtlich.", "m.brugger@wohnhaus-brugger.ch", "legal", R),
    ("Betrugsverdacht", "Guten Tag, ich glaube, es gab ein Datenleck bei Ihnen. Unser Rechner wurde kompromittiert und Passwörter wurden abgegriffen. Wir melden das intern.", "it@alpincorp.ch", "security_incident", R),
    ("Phishing in unserem Namen", "Guten Tag, wir haben eine Phishing-Mail erhalten, die Ihren Absender missbraucht. Ein Zugang wurde kompromittiert. Bitte um schnelle Reaktion.", "sicherheit@stiftung-lakeside.ch", "security_incident", R),
    ("Reklamation schlechte Arbeit", "Guten Tag, die Arbeit war wirklich schlecht, die Fassade ist fleckig. Ich fordere eine Rückerstattung und werde das an die Geschäftsleitung eskalieren.", "bau@wohnverwlicht.ch", "complaint", R),
    ("Rechnung zu hoch berechnet", "Guten Tag, Sie haben uns zu viel berechnet. Die Rechnung ist falsch, wir erkennen den Betrag nicht an und verlangen eine Gutschrift.", "woh@baugenossenschaft.ch", "billing_dispute", R),
    # adversarial: sensitive content in routine trades language
    ("Angebot mit Vertragsproblem", "Guten Tag, das Angebot sieht gut aus und wir sind interessiert. Nur eine Frage: Unser Anwalt hat beim Vertrag eine rechtliche Falle gefunden. Können Sie trotzdem senden?", "e.muster@elektro-muster.ch", "legal", R),
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
    print(f"SECTOR BENCHMARK — {len(CASES)} cases, DE/CH/AT trades + SHK + Elektro")
    print("=" * 66)
    print(f"routing accuracy            : {acc:6.1%}  {route_ok}/{r_n}      target >=85%")
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

    ok = acc >= 0.85 and safety == 1.0 and sub >= 0.95 and p95 < 50
    print("VERDICT:", "PASS — vocabulary holds" if ok else "FAIL — engine does not yet handle sector vocabulary")
    print("=" * 66)

    json.dump({"cases": len(CASES), "routing_cases": r_n, "sensitive_cases": s_n,
               "routing_accuracy": acc, "safety_recall": safety,
               "subtype_accuracy": sub, "p95_ms": p95,
               "failures": [{"subject": s, "issue": w} for s, w in failures],
               "passed": ok},
              open(os.path.join(STATE, "bench_sector.json"), "w"), indent=2)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
