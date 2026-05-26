#!/usr/bin/env python3
"""
Newsletter Webhook Server
Empfängt HTML-Newsletter von Claude Remote-Agents und sendet sie per SMTP.
Läuft als Docker-Container auf dem Hetzner-Server.
"""
import os
import json
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from http.server import HTTPServer, BaseHTTPRequestHandler

WEBHOOK_TOKEN = os.environ.get("NEWSLETTER_WEBHOOK_TOKEN", "")
SMTP_HOST     = os.environ.get("SMTP_HOST", "smtp.office365.com")
SMTP_PORT     = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER     = os.environ.get("SMTP_USER", "")
SMTP_PASS     = os.environ.get("SMTP_PASS", "")


def send_mail(to: str, subject: str, html: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = SMTP_USER
    msg["To"]      = to
    msg.attach(MIMEText(html, "html", "utf-8"))
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
        s.ehlo(); s.starttls(); s.ehlo()
        s.login(SMTP_USER, SMTP_PASS)
        s.sendmail(SMTP_USER, to, msg.as_string())


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(fmt % args, flush=True)

    def do_GET(self):
        if self.path == "/health":
            self._json(200, {"ok": True})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/send":
            self._json(404, {"error": "not found"}); return

        try:
            length = int(self.headers.get("Content-Length", 0))
            body   = json.loads(self.rfile.read(length))
        except Exception:
            self._json(400, {"error": "invalid json"}); return

        if not WEBHOOK_TOKEN or body.get("token") != WEBHOOK_TOKEN:
            self._json(401, {"error": "unauthorized"}); return

        to      = body.get("to", "")
        subject = body.get("subject", "")
        html    = body.get("html", "")
        if not all([to, subject, html]):
            self._json(400, {"error": "missing: to, subject, html"}); return

        try:
            send_mail(to, subject, html)
            print(f"[OK] Gesendet: {subject!r} → {to}", flush=True)
            self._json(200, {"ok": True})
        except Exception as e:
            print(f"[ERR] {e}", flush=True)
            self._json(500, {"error": str(e)})

    def _json(self, code: int, data: dict):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"Newsletter Webhook läuft auf Port {port}", flush=True)
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()
