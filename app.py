#!/usr/bin/env python3
"""
Newsletter Webhook Server
Empfängt HTML-Newsletter von Claude Remote-Agents und sendet sie per MS Graph API.
"""
import os
import json
import subprocess
import threading
import urllib.request
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler

WEBHOOK_TOKEN = os.environ.get("NEWSLETTER_WEBHOOK_TOKEN", "")
TENANT_ID     = os.environ.get("AZURE_TENANT_ID", "cb1ac70c-fe3c-4094-a440-1f2f407f820c")
CLIENT_ID     = os.environ.get("AZURE_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("AZURE_CLIENT_SECRET", "")
SENDER        = "alexander@koeschu.com"


def get_access_token() -> str:
    url  = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
    data = urllib.parse.urlencode({
        "grant_type":    "client_credentials",
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "scope":         "https://graph.microsoft.com/.default",
    }).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())["access_token"]


def send_mail(to: str, subject: str, html: str) -> None:
    token   = get_access_token()
    url     = f"https://graph.microsoft.com/v1.0/users/{SENDER}/sendMail"
    payload = json.dumps({
        "message": {
            "subject": subject,
            "body": {"contentType": "HTML", "content": html},
            "toRecipients": [{"emailAddress": {"address": to}}],
        }
    }).encode()
    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req) as resp:
        if resp.status not in (200, 202):
            raise RuntimeError(f"Graph API Fehler: {resp.status}")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(fmt % args, flush=True)

    def do_GET(self):
        if self.path == "/health":
            import os
            self._json(200, {
                "ok": True,
                "anthropic_key_set": bool(os.environ.get("ANTHROPIC_API_KEY", "")),
                "azure_client_id_set": bool(CLIENT_ID),
            })
        elif self.path == "/test-translate":
            # Testet ob die Anthropic API erreichbar ist
            import os, urllib.request, urllib.parse
            key = os.environ.get("ANTHROPIC_API_KEY", "")
            if not key:
                self._json(500, {"error": "ANTHROPIC_API_KEY nicht gesetzt"}); return
            try:
                payload = json.dumps({
                    "model": "claude-3-5-haiku-20241022",
                    "max_tokens": 100,
                    "messages": [{"role": "user", "content": "Übersetze ins Deutsche: 'Hello World'. Antworte nur mit der Übersetzung."}],
                }).encode()
                req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=payload, method="POST")
                req.add_header("x-api-key", key)
                req.add_header("anthropic-version", "2023-06-01")
                req.add_header("Content-Type", "application/json")
                with urllib.request.urlopen(req, timeout=15) as r:
                    resp = json.loads(r.read())
                    result = resp["content"][0]["text"]
                self._json(200, {"ok": True, "result": result})
            except Exception as e:
                self._json(500, {"error": str(e)})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        # --- /trigger: Newsletter-Generator als Hintergrundprozess starten ---
        if self.path == "/trigger":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body   = json.loads(self.rfile.read(length))
            except Exception:
                self._json(400, {"error": "invalid json"}); return

            if not WEBHOOK_TOKEN or body.get("token") != WEBHOOK_TOKEN:
                self._json(401, {"error": "unauthorized"}); return

            topic = body.get("topic", "")
            if topic not in ("ds", "ki"):
                self._json(400, {"error": "topic must be ds or ki"}); return

            def run():
                subprocess.run(["python3", "/app/newsletter-generator.py", topic])
            threading.Thread(target=run, daemon=True).start()
            self._json(200, {"ok": True, "topic": topic})
            return

        # --- /send: HTML-Newsletter direkt per Graph API verschicken ---
        if self.path == "/send":
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
            return

        self._json(404, {"error": "not found"})

    def _json(self, code: int, data: dict):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"Newsletter Webhook (MS Graph) läuft auf Port {port}", flush=True)
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()
