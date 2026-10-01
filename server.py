#!/usr/bin/env python3
"""
Demo server for the Inbox Triage Engine.

Binds to LOCALHOST ONLY by default. This is a demo, not a production service,
and per the exposure policy it must not be reachable from the Internet without
explicit intent. To expose it deliberately: --host 0.0.0.0 (and only behind
TLS + auth, which is not configured here).

Usage:  python3 server.py [--host 127.0.0.1] [--port 8090]
"""
import argparse, json, os, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from triage import triage
from dataclasses import asdict

WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")

SAMPLES = [
    {"label": "Sales enquiry", "subject": "Quote request for 40 units",
     "body": "Hi, we need a quote for 40 units delivered to Zurich. What is your pricing "
             "and lead time? We would like to start next month. Regards, Peter Keller, "
             "Keller Logistik GmbH, phone 044 221 45 67", "sender": "peter@kellerlogistik.ch"},
    {"label": "Appointment change", "subject": "Appointment change needed",
     "body": "Hello, I need to reschedule my appointment for Friday to next Tuesday "
             "morning. Can you confirm? Also my phone is 079 123 45 67. Thanks, Anna",
     "sender": "anna.rei@example.ch"},
    {"label": "Urgent outage", "subject": "Cannot log in since this morning",
     "body": "Hi team, I cannot log into the portal since this morning. It shows an error. "
             "This is blocking our team. Please advise. Best, Marco",
     "sender": "marco@beispiel.ch"},
    {"label": "Billing query", "subject": "Invoice 2026-118 payment query",
     "body": "Hello, regarding invoice 2026-118 - could you send the receipt and confirm "
             "the payment terms and VAT number? Thanks, Finance",
     "sender": "finance@client.ch"},
    {"label": "Legal notice (human only)", "subject": "We received a legal notice",
     "body": "Our solicitor has issued a legal notice regarding the liability clause. "
             "Please direct all correspondence to our attorney.",
     "sender": "law@client.ch"},
    {"label": "Data breach (human only)", "subject": "URGENT: data breach, need response",
     "body": "This is urgent. We believe there was a data breach on your side. We need an "
             "immediate response and an escalation to your CTO today.",
     "sender": "ciso@enterprise.com"},
    {"label": "Spam", "subject": "Limited time offer!!! Act now",
     "body": "Congratulations you! Click here for a crypto giveaway. Guaranteed returns, "
             "unsubscribe at any time. Work from home and earn thousands.",
     "sender": "noreply@spam.biz"},
]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *a):
        sys.stderr.write("[demo] %s - %s\n" % (self.address_string(), fmt % a))

    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ("/", "/index.html"):
            return self._serve_file("demo.html", "text/html; charset=utf-8")
        if u.path == "/offer":
            return self._serve_file("offer.html", "text/html; charset=utf-8")
        if u.path == "/api/samples":
            return self._send(200, json.dumps(SAMPLES))
        if u.path == "/healthz":
            return self._send(200, json.dumps({"status": "ok"}))
        return self._send(404, json.dumps({"error": "not found"}))

    def _serve_file(self, name, ctype):
        p = os.path.join(WEB, name)
        if not os.path.exists(p):
            return self._send(404, json.dumps({"error": f"{name} missing"}))
        with open(p, "r", encoding="utf-8") as f:
            self._send(200, f.read(), ctype)

    def do_POST(self):
        if urlparse(self.path).path != "/api/triage":
            return self._send(404, json.dumps({"error": "not found"}))
        n = int(self.headers.get("Content-Length", 0))
        try:
            data = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return self._send(400, json.dumps({"error": "invalid json"}))
        if n > 100_000:
            return self._send(413, json.dumps({"error": "payload too large"}))
        r = triage(data.get("subject", ""), data.get("body", ""),
                   data.get("sender", ""))
        return self._send(200, json.dumps(asdict(r)))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8090)
    a = ap.parse_args()
    srv = ThreadingHTTPServer((a.host, a.port), Handler)
    print(f"[demo] Inbox Triage demo on http://{a.host}:{a.port}  (health: /healthz)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()