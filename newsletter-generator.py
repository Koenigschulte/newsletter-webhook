#!/usr/bin/env python3
"""
Newsletter Generator — Hetzner Server
Ruft RSS-Feeds ab, baut HTML, sendet via Webhook.
Aufruf: python3 newsletter-generator.py ds   (Digitale Souveränität)
         python3 newsletter-generator.py ki   (Künstliche Intelligenz)
"""
import sys, os, json, datetime, urllib.request, urllib.error
import xml.etree.ElementTree as ET
from html import unescape

# ── Konfiguration ────────────────────────────────────────────────────────────

WEBHOOK_URL     = "https://newsletter.koeschu.com/send"
WEBHOOK_TOKEN   = os.environ.get("NEWSLETTER_WEBHOOK_TOKEN", "")
ANTHROPIC_KEY   = os.environ.get("ANTHROPIC_API_KEY", "")
RECIPIENT       = "alexander@koeschu.com"
MAX_ARTICLES    = 5
TIMEOUT         = 15
LOG             = "/var/log/newsletter.log"

# Secrets aus /etc/secrets.env laden (falls Token nicht als Env-Var gesetzt)
if not WEBHOOK_TOKEN:
    try:
        with open("/etc/secrets.env") as f:
            for line in f:
                line = line.strip()
                if line.startswith("NEWSLETTER_WEBHOOK_TOKEN="):
                    WEBHOOK_TOKEN = line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass

TOPICS = {
    "ds": {
        "subject_prefix": "🛡️ Digitale Souveränität – Daily Brief",
        "header_color": "#1a3a5c",
        "accent":       "#1a7ab5",
        "insight_bg":   "#eaf4fb",
        "keywords": [
            "souveränität", "sovereignty", "dsgvo", "gdpr", "datenschutz", "privacy",
            "palantir", "gaia-x", "cloud act", "surveillance", "überwachung",
            "digital rights", "eu ai act", "big tech", "whistleblow", "nsa",
            "geheimdienst", "datenpanne", "datenleck", "digitalgesetz", "dma", "dsa",
            "microsoft", "amazon", "google", "meta", "apple", "us-konzern",
            "digitale souveränität", "europäische cloud", "open source", "vendor lock",
            "datenspeicherung", "datenweitergabe", "schrems", "netzpolitik",
        ],
        # DE-Quellen + EN-Quellen (werden automatisch übersetzt)
        "feeds": [
            ("de", "https://netzpolitik.org/feed/"),                    # DE – beste Quelle für DS
            ("de", "https://www.heise.de/security/news-atom.xml"),      # DE
            ("de", "https://www.golem.de/rss.php"),                     # DE
            ("de", "https://www.spiegel.de/netzwelt/index.rss"),        # DE
            ("de", "https://www.sueddeutsche.de/rss/netzwelt"),         # DE
            ("de", "https://www.tagesschau.de/xml/rss2/"),              # DE – breite Abdeckung
            ("en", "https://noyb.eu/en/rss.xml"),                       # EN – EU Privacy → wird übersetzt
            ("en", "https://edri.org/feed/"),                           # EN – EU Digital Rights → wird übersetzt
        ],
    },
    "ki": {
        "subject_prefix": "🤖 Künstliche Intelligenz – Daily Brief",
        "header_color": "#1a1a2e",
        "accent":       "#7c3aed",
        "insight_bg":   "#f0eaff",
        "keywords": [
            "künstliche intelligenz", "artificial intelligence", " ki ", "ki,", " ai ",
            "llm", "gpt", "claude", "gemini", "copilot", "chatbot", "openai",
            "anthropic", "deep learning", "sprachmodell", "language model",
            "eu ai act", "roboter", "automation", "algorithmus", "machine learning",
            "ki-modell", "generative", "transformer", "nvidia", "deepseek",
            "openai", "mistral", "meta llama", "ki-regulierung", "ki-gesetz",
            "china", "usa", "silicon valley", "sam altman", "elon musk",
        ],
        # Deutschsprachige Quellen — berichten auf Deutsch über EU, USA und China
        "feeds": [
            ("de", "https://t3n.de/tag/kuenstliche-intelligenz/feed/"), # DE – KI-Fokus
            ("de", "https://www.heise.de/news-atom.xml"),               # DE – breite Technik
            ("de", "https://www.golem.de/rss.php"),                     # DE
            ("de", "https://mixed.de/feed/"),                           # DE – KI/XR
            ("de", "https://www.spiegel.de/netzwelt/index.rss"),        # DE
            ("de", "https://www.tagesschau.de/xml/rss2/"),              # DE – intl. KI-News auf DE
            ("de", "https://netzpolitik.org/feed/"),                    # DE – KI-Regulierung EU
        ],
    },
}

# ── RSS-Parsing ──────────────────────────────────────────────────────────────

def fetch_feed(url):
    """Lädt RSS/Atom-Feed, gibt Liste von Dicts zurück."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            data = r.read()
        root = ET.fromstring(data)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        articles = []

        # Atom-Format
        for entry in root.findall(".//atom:entry", ns):
            title = entry.findtext("atom:title", "", ns)
            link_el = entry.find("atom:link", ns)
            link = link_el.get("href", "") if link_el is not None else ""
            summary = entry.findtext("atom:summary", "", ns) or entry.findtext("atom:content", "", ns) or ""
            pub = entry.findtext("atom:published", "", ns) or entry.findtext("atom:updated", "", ns) or ""
            if title and link:
                articles.append({"title": unescape(title), "link": link,
                                  "summary": unescape(strip_tags(summary))[:1200], "pub": pub[:10]})

        # RSS-Format
        for item in root.findall(".//item"):
            title = item.findtext("title", "")
            link  = item.findtext("link", "")
            desc  = item.findtext("description", "")
            pub   = item.findtext("pubDate", "")[:16]
            if title and link:
                articles.append({"title": unescape(title), "link": link,
                                  "summary": unescape(strip_tags(desc))[:1200], "pub": pub})
        return articles
    except Exception as e:
        log(f"  Feed-Fehler {url}: {e}")
        return []


def strip_tags(html):
    """Entfernt HTML-Tags."""
    import re
    return re.sub(r"<[^>]+>", "", html).strip()


def is_german(article):
    """Prüft ob Artikel auf Deutsch ist (Umlaute oder typische deutsche Wörter)."""
    text = article["title"] + " " + article["summary"]
    german_chars = set("äöüÄÖÜß")
    if any(c in german_chars for c in text):
        return True
    # Typische deutsche Funktionswörter
    words = set(text.lower().split())
    german_words = {"der", "die", "das", "und", "ist", "für", "von", "mit",
                    "bei", "auf", "des", "dem", "den", "wird", "hat", "auch",
                    "sich", "nach", "eine", "einen", "oder", "nicht", "wie"}
    return len(words & german_words) >= 2


def translate_to_german(title, summary):
    """Übersetzt Titel und Zusammenfassung ins Deutsche via Claude Haiku."""
    if not ANTHROPIC_KEY:
        return title, summary
    try:
        prompt = (
            f"Übersetze folgendes ins Deutsche. Antworte NUR mit JSON, kein Text davor oder danach: "
            f'{{\"title\": \"...\", \"summary\": \"...\"}}\n\n'
            f"Titel: {title}\nZusammenfassung: {summary}"
        )
        payload = json.dumps({
            "model": "claude-3-5-sonnet-20241022",
            "max_tokens": 600,
            "messages": [{"role": "user", "content": prompt}],
        }).encode()
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload, method="POST"
        )
        req.add_header("x-api-key", ANTHROPIC_KEY)
        req.add_header("anthropic-version", "2023-06-01")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=20) as r:
            resp = json.loads(r.read())
            text = resp["content"][0]["text"].strip()
            # JSON aus Antwort extrahieren
            start = text.find("{")
            end   = text.rfind("}") + 1
            data  = json.loads(text[start:end])
            return data.get("title", title), data.get("summary", summary)
    except Exception as e:
        log(f"  ÜBERSETZUNG FEHLER ({type(e).__name__}): {e}")
        return title, summary


def is_relevant(article, keywords):
    text = (article["title"] + " " + article["summary"]).lower()
    return any(kw in text for kw in keywords)


# ── HTML-Builder ─────────────────────────────────────────────────────────────

CSS = """body{font-family:-apple-system,Arial,sans-serif;max-width:680px;margin:0 auto;background:#f0f4f8;color:#222}
.header{background:{header_color};color:white;padding:28px 24px;text-align:center}
.header h1{margin:0;font-size:22px}
.header p{margin:8px 0 0;opacity:.75;font-size:13px}
.content{padding:20px 16px}
.article{background:white;border-radius:10px;margin-bottom:18px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.08)}
.article-body{padding:16px 18px 18px}
.article-body h2{margin:0 0 10px;font-size:16px;line-height:1.4}
.article-body h2 a{color:{header_color};text-decoration:none}
.summary{color:#444;font-size:14px;line-height:1.65;margin:0 0 12px}
.insight{background:{insight_bg};border-left:3px solid {accent};padding:10px 14px;font-size:13px;color:#333;border-radius:0 6px 6px 0}
.read-more{display:inline-block;margin-top:12px;color:{accent};font-size:13px;text-decoration:none;font-weight:500}
.footer{text-align:center;padding:24px 16px;color:#999;font-size:12px;border-top:1px solid #e0e0e0}"""


def build_html(topic, articles, today):
    cfg = TOPICS[topic]
    css = CSS.replace("{header_color}", cfg["header_color"]) \
             .replace("{accent}", cfg["accent"]) \
             .replace("{insight_bg}", cfg["insight_bg"])

    cards = ""
    for a in articles:
        pub = f" · {a['pub']}" if a.get("pub") else ""
        summary = a["summary"] if a["summary"] else "Vollständigen Artikel lesen."
        cards += f"""
  <div class="article">
    <div class="article-body">
      <h2><a href="{a['link']}" target="_blank">{a['title']}</a></h2>
      <p class="summary">{summary}</p>
      <div class="insight">📅 Veröffentlicht{pub} — <a href="{a['link']}" target="_blank" style="color:inherit">{a['link'][:60]}…</a></div>
      <a class="read-more" href="{a['link']}" target="_blank">Weiterlesen →</a>
    </div>
  </div>"""

    prefix = cfg["subject_prefix"].replace("🛡️ ", "").replace("🤖 ", "").split(" –")[0]
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>{css}</style></head><body>
<div class="header">
  <h1>{cfg['subject_prefix'].split(' –')[0]}</h1>
  <p>Daily Brief · {today}</p>
</div>
<div class="content">{cards}
</div>
<div class="footer"><p>{prefix} Daily Brief · Täglich 8:00 Uhr</p></div>
</body></html>"""


# ── Versand ──────────────────────────────────────────────────────────────────

def send(subject, html):
    payload = json.dumps({
        "token":   WEBHOOK_TOKEN,
        "to":      RECIPIENT,
        "subject": subject,
        "html":    html,
    }).encode()
    req = urllib.request.Request(WEBHOOK_URL, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


# ── Logging ──────────────────────────────────────────────────────────────────

def log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2 or sys.argv[1] not in TOPICS:
        print("Aufruf: newsletter-generator.py ds|ki")
        sys.exit(1)

    topic = sys.argv[1]
    cfg   = TOPICS[topic]
    today = datetime.datetime.now().strftime("%d.%m.%Y")

    log(f"=== Newsletter '{topic}' startet ({today}) ===")

    if not WEBHOOK_TOKEN:
        log("FEHLER: NEWSLETTER_WEBHOOK_TOKEN nicht gesetzt")
        sys.exit(1)

    # Artikel sammeln — getrennt nach Sprache
    german_articles = []
    english_articles = []

    for lang, feed_url in cfg["feeds"]:
        log(f"  Lade [{lang.upper()}]: {feed_url}")
        articles = fetch_feed(feed_url)
        relevant = [a for a in articles if is_relevant(a, cfg["keywords"])]
        log(f"  → {len(articles)} Artikel, {len(relevant)} relevant")
        for a in relevant:
            if is_german(a):
                german_articles.append(a)
            else:
                # Artikel ist Englisch (egal welcher Feed) → übersetzen
                log(f"    Übersetze [{lang.upper()}]: {a['title'][:60]}…")
                a["title"], a["summary"] = translate_to_german(a["title"], a["summary"])
                german_articles.append(a)

    # Deutsche Artikel zuerst, englische nur als Lückenfüller
    combined = german_articles + english_articles

    # Deduplizieren (nach Link)
    seen = set()
    unique = []
    for a in combined:
        if a["link"] not in seen:
            seen.add(a["link"])
            unique.append(a)

    top = unique[:MAX_ARTICLES]
    log(f"  Gesamt: {len(unique)} relevante Artikel ({len(german_articles)} DE / {len(english_articles)} EN), nehme {len(top)}")

    if not top:
        log("WARNUNG: Keine relevanten Artikel gefunden — Newsletter wird nicht gesendet")
        sys.exit(0)

    # HTML bauen
    html    = build_html(topic, top, today)
    subject = f"{cfg['subject_prefix']} {today}"

    # Senden
    log(f"  Sende: '{subject}'")
    result = send(subject, html)
    log(f"  Ergebnis: {result}")
    log(f"=== Fertig ===")


if __name__ == "__main__":
    main()
