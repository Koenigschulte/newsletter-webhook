#!/usr/bin/env python3
"""
Newsletter Generator — Hetzner Server
Ruft RSS-Feeds ab, baut HTML, sendet via Webhook.
Aufruf: python3 newsletter-generator.py ds|ki [--dry-run]
"""
import sys, os, json, datetime, urllib.request, urllib.error, re
import xml.etree.ElementTree as ET
from html import unescape

# ── Konfiguration ────────────────────────────────────────────────────────────

WEBHOOK_URL     = "https://newsletter.koeschu.com/send"
WEBHOOK_TOKEN   = os.environ.get("NEWSLETTER_WEBHOOK_TOKEN", "")
ANTHROPIC_KEY   = os.environ.get("ANTHROPIC_API_KEY", "")
RECIPIENT       = "alexander@koeschu.com"
MAX_ARTICLES    = 5
MAX_AGE_HOURS   = 48   # Nur Artikel der letzten 48 Stunden
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
        "feeds": [
            ("de", "https://netzpolitik.org/feed/"),
            ("de", "https://www.heise.de/security/news-atom.xml"),
            ("de", "https://www.golem.de/rss.php"),
            ("de", "https://www.spiegel.de/netzwelt/index.rss"),
            ("de", "https://www.sueddeutsche.de/rss/netzwelt"),
            ("de", "https://www.tagesschau.de/xml/rss2/"),
            ("en", "https://noyb.eu/en/rss.xml"),
            ("en", "https://edri.org/feed/"),
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
            "mistral", "meta llama", "ki-regulierung", "ki-gesetz",
            "china", "usa", "silicon valley", "sam altman", "elon musk",
        ],
        "feeds": [
            ("de", "https://t3n.de/tag/kuenstliche-intelligenz/feed/"),
            ("de", "https://www.heise.de/news-atom.xml"),
            ("de", "https://www.golem.de/rss.php"),
            ("de", "https://mixed.de/feed/"),
            ("de", "https://www.spiegel.de/netzwelt/index.rss"),
            ("de", "https://www.tagesschau.de/xml/rss2/"),
            ("de", "https://netzpolitik.org/feed/"),
        ],
    },
}

# ── RSS-Parsing ──────────────────────────────────────────────────────────────

def parse_date(pub_str):
    """Parst Datum aus RSS/Atom-String, gibt datetime-Objekt zurück."""
    if not pub_str:
        return None
    s = pub_str.strip()
    formats = [
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S+00:00",
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S GMT",
        "%a, %d %b %Y %H:%M:%S +0000",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            dt = datetime.datetime.strptime(s[:len(fmt)+5].strip(), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
            return dt
        except Exception:
            continue
    return None


def is_recent(pub_raw):
    """Nur Artikel der letzten MAX_AGE_HOURS Stunden."""
    if not pub_raw:
        return True
    dt = parse_date(pub_raw)
    if dt is None:
        return True
    now = datetime.datetime.now(datetime.timezone.utc)
    age_hours = (now - dt).total_seconds() / 3600
    return age_hours <= MAX_AGE_HOURS


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
            title   = entry.findtext("atom:title", "", ns)
            link_el = entry.find("atom:link", ns)
            link    = link_el.get("href", "") if link_el is not None else ""
            summary = entry.findtext("atom:summary", "", ns) or entry.findtext("atom:content", "", ns) or ""
            pub_raw = entry.findtext("atom:published", "", ns) or entry.findtext("atom:updated", "", ns) or ""
            dt      = parse_date(pub_raw)
            pub_display = dt.strftime("%d.%m.%Y") if dt else pub_raw[:10]
            if title and link:
                articles.append({"title": unescape(title), "link": link,
                                  "summary": unescape(strip_tags(summary))[:1200],
                                  "pub": pub_display, "pub_raw": pub_raw})

        # RSS-Format
        for item in root.findall(".//item"):
            title   = item.findtext("title", "")
            link    = item.findtext("link", "")
            desc    = item.findtext("description", "")
            pub_raw = item.findtext("pubDate", "")
            dt      = parse_date(pub_raw)
            pub_display = dt.strftime("%d.%m.%Y") if dt else pub_raw[:10]
            if title and link:
                articles.append({"title": unescape(title), "link": link,
                                  "summary": unescape(strip_tags(desc))[:1200],
                                  "pub": pub_display, "pub_raw": pub_raw})
        return articles
    except Exception as e:
        log(f"  Feed-Fehler {url}: {e}")
        return []


def strip_tags(html):
    """Entfernt HTML-Tags."""
    return re.sub(r"<[^>]+>", "", html).strip()


def is_german(article):
    """Prüft ob Artikel auf Deutsch ist."""
    text = article["title"] + " " + article["summary"]
    if any(c in "äöüÄÖÜß" for c in text):
        return True
    words = set(text.lower().split())
    german_words = {"der", "die", "das", "und", "ist", "für", "von", "mit",
                    "bei", "auf", "des", "dem", "den", "wird", "hat", "auch",
                    "sich", "nach", "eine", "einen", "oder", "nicht", "wie"}
    return len(words & german_words) >= 2


BLOCKLIST = ["anzeige:", "sponsored:", "werbung:", "advertisement:", "deals:", "angebot:"]

def is_relevant(article, keywords):
    title_lower = article["title"].lower()
    # Werbeanzeigen rausfiltern
    if any(title_lower.startswith(bl) for bl in BLOCKLIST):
        return False
    # Mindestens 1 Keyword im Titel ODER 2+ Keywords im Gesamttext
    title_matches = sum(1 for kw in keywords if kw in title_lower)
    if title_matches >= 1:
        return True
    full_text = (article["title"] + " " + article["summary"]).lower()
    full_matches = sum(1 for kw in keywords if kw in full_text)
    return full_matches >= 2


def call_claude(prompt, max_tokens=600):
    """Ruft Claude API auf und gibt Antworttext zurück."""
    if not ANTHROPIC_KEY:
        return None
    try:
        payload = json.dumps({
            "model": "claude-haiku-4-5",
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }).encode()
        req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=payload, method="POST")
        req.add_header("x-api-key", ANTHROPIC_KEY)
        req.add_header("anthropic-version", "2023-06-01")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=20) as r:
            resp = json.loads(r.read())
            return resp["content"][0]["text"].strip()
    except Exception as e:
        log(f"  Claude API Fehler ({type(e).__name__}): {e}")
        return None


def enrich_article(title, summary, topic_context):
    """Erstellt Zusammenfassung, Erkenntnis und Problem auf Deutsch via Claude."""
    prompt = (
        f"Du schreibst einen Newsletter über {topic_context}.\n"
        f"Analysiere diesen Artikel und antworte NUR in diesem exakten Format:\n\n"
        f"ZUSAMMENFASSUNG: [4-5 Sätze: Was ist passiert? Wer ist beteiligt? Welche Details sind wichtig?]\n"
        f"ERKENNTNIS: [2-3 Sätze: Was bedeutet das strategisch? Was sollte der Leser mitnehmen?]\n"
        f"PROBLEM: [2-3 Sätze: Welches konkrete Problem oder Risiko steckt dahinter?]\n\n"
        f"Titel: {title}\n"
        f"Verfügbarer Text: {summary}"
    )
    result = call_claude(prompt, max_tokens=700)
    if not result:
        return {"zusammenfassung": summary, "erkenntnis": "", "problem": ""}
    z = re.search(r"ZUSAMMENFASSUNG:\s*([\s\S]+?)(?=ERKENNTNIS:|$)", result)
    e = re.search(r"ERKENNTNIS:\s*([\s\S]+?)(?=PROBLEM:|$)", result)
    p = re.search(r"PROBLEM:\s*([\s\S]+?)$", result)
    log(f"  ✓ Artikel angereichert: {title[:50]}")
    return {
        "zusammenfassung": z.group(1).strip() if z else summary,
        "erkenntnis":      e.group(1).strip() if e else "",
        "problem":         p.group(1).strip() if p else "",
    }


def translate_to_german(title, summary):
    """Übersetzt Titel und Zusammenfassung ins Deutsche via Claude."""
    if not ANTHROPIC_KEY:
        log("  Übersetzung: ANTHROPIC_API_KEY nicht gesetzt")
        return title, summary
    prompt = (
        f"Übersetze ins Deutsche. Antworte NUR in diesem exakten Format:\n"
        f"TITEL: [übersetzter Titel]\n"
        f"TEXT: [übersetzte Zusammenfassung]\n\n"
        f"Titel: {title}\nText: {summary}"
    )
    result = call_claude(prompt, max_tokens=800)
    if result:
        t_match = re.search(r"TITEL:\s*(.+)", result)
        s_match = re.search(r"TEXT:\s*([\s\S]+)", result)
        new_title   = t_match.group(1).strip() if t_match else title
        new_summary = s_match.group(1).strip() if s_match else summary
        log(f"  ✓ Übersetzt: {new_title[:60]}")
        return new_title, new_summary
    return title, summary


# ── HTML-Builder ─────────────────────────────────────────────────────────────

CSS = """body{font-family:-apple-system,Arial,sans-serif;max-width:680px;margin:0 auto;background:#f0f4f8;color:#222}
.header{background:{header_color};color:white;padding:28px 24px;text-align:center}
.header h1{margin:0;font-size:22px}
.header p{margin:8px 0 0;opacity:.75;font-size:13px}
.content{padding:20px 16px}
.article{background:white;border-radius:10px;margin-bottom:22px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.08)}
.article-body{padding:18px 20px 20px}
.article-body h2{margin:0 0 12px;font-size:17px;line-height:1.4}
.article-body h2 a{color:{header_color};text-decoration:none}
.section-label{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.6px;color:{accent};margin:14px 0 4px}
.summary{color:#333;font-size:14px;line-height:1.7;margin:0 0 4px}
.box{border-left:3px solid {accent};padding:10px 14px;font-size:13px;line-height:1.65;border-radius:0 6px 6px 0;margin-bottom:8px}
.box-erkenntnis{background:{insight_bg};color:#1a3a1a}
.box-problem{background:#fff4f4;color:#5a1a1a;border-color:#e05555}
.meta{color:#999;font-size:12px;margin-top:10px}
.read-more{display:inline-block;margin-top:8px;color:{accent};font-size:13px;text-decoration:none;font-weight:600}
.footer{text-align:center;padding:24px 16px;color:#999;font-size:12px;border-top:1px solid #e0e0e0}"""


def build_html(topic, articles, today):
    cfg = TOPICS[topic]
    css = CSS.replace("{header_color}", cfg["header_color"]) \
             .replace("{accent}", cfg["accent"]) \
             .replace("{insight_bg}", cfg["insight_bg"])

    cards = ""
    for a in articles:
        pub = f"{a['pub']}" if a.get("pub") else ""
        zusammenfassung = a.get("zusammenfassung") or a.get("summary") or "Vollständigen Artikel lesen."
        erkenntnis = a.get("erkenntnis", "")
        problem    = a.get("problem", "")
        erkenntnis_block = f'<div class="section-label">💡 Erkenntnis</div><div class="box box-erkenntnis">{erkenntnis}</div>' if erkenntnis else ""
        problem_block    = f'<div class="section-label">⚠️ Problem</div><div class="box box-problem">{problem}</div>' if problem else ""
        cards += f"""
  <div class="article">
    <div class="article-body">
      <h2><a href="{a['link']}" target="_blank">{a['title']}</a></h2>
      <div class="section-label">📋 Zusammenfassung</div>
      <p class="summary">{zusammenfassung}</p>
      {erkenntnis_block}
      {problem_block}
      <p class="meta">📅 {pub} — <a href="{a['link']}" target="_blank" style="color:#999">{a['link'][:55]}…</a></p>
      <a class="read-more" href="{a['link']}" target="_blank">Vollständigen Artikel lesen →</a>
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

DRY_RUN = "--dry-run" in sys.argv

def log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    # Im dry-run auf stderr damit stdout sauber für JSON bleibt
    if DRY_RUN:
        print(line, file=sys.stderr, flush=True)
    else:
        print(line, flush=True)
    try:
        with open(LOG, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    dry_run = DRY_RUN
    args = [a for a in sys.argv[1:] if not a.startswith("--")]

    if not args or args[0] not in TOPICS:
        print("Aufruf: newsletter-generator.py ds|ki [--dry-run]")
        sys.exit(1)

    topic = args[0]
    cfg   = TOPICS[topic]
    today = datetime.datetime.now().strftime("%d.%m.%Y")

    log(f"=== Newsletter '{topic}' startet ({today}) {'[DRY-RUN]' if dry_run else ''} ===")
    log(f"  ANTHROPIC_KEY: {'gesetzt' if ANTHROPIC_KEY else 'FEHLT'}")

    if not dry_run and not WEBHOOK_TOKEN:
        log("FEHLER: NEWSLETTER_WEBHOOK_TOKEN nicht gesetzt")
        sys.exit(1)

    # Artikel sammeln
    german_articles  = []
    english_articles = []

    for lang, feed_url in cfg["feeds"]:
        log(f"  Lade [{lang.upper()}]: {feed_url}")
        articles = fetch_feed(feed_url)
        relevant = [a for a in articles if is_relevant(a, cfg["keywords"]) and is_recent(a.get("pub_raw", ""))]
        log(f"  → {len(articles)} Artikel, {len(relevant)} relevant & aktuell (≤{MAX_AGE_HOURS}h)")
        for a in relevant:
            if is_german(a):
                german_articles.append(a)
            else:
                log(f"    Übersetze: {a['title'][:60]}…")
                a["title"], a["summary"] = translate_to_german(a["title"], a["summary"])
                german_articles.append(a)

    # Deduplizieren
    seen, unique = set(), []
    for a in german_articles:
        if a["link"] not in seen:
            seen.add(a["link"])
            unique.append(a)

    top = unique[:MAX_ARTICLES]
    log(f"  Gesamt: {len(unique)} Artikel, nehme {len(top)}")

    # Artikel mit Claude anreichern (Zusammenfassung, Erkenntnis, Problem)
    if ANTHROPIC_KEY:
        topic_context = "digitale Souveränität, Datenschutz und EU-Regulierung" if topic == "ds" else "Künstliche Intelligenz, LLMs und KI-Entwicklungen"
        for a in top:
            log(f"  Reichere an: {a['title'][:50]}…")
            enriched = enrich_article(a["title"], a["summary"], topic_context)
            a["zusammenfassung"] = enriched["zusammenfassung"]
            a["erkenntnis"]      = enriched["erkenntnis"]
            a["problem"]         = enriched["problem"]
    else:
        for a in top:
            a["zusammenfassung"] = a.get("summary", "")
            a["erkenntnis"]      = ""
            a["problem"]         = ""

    if not top:
        log("WARNUNG: Keine relevanten Artikel gefunden")
        if dry_run:
            print(json.dumps({"ok": False, "reason": "no articles", "topic": topic}))
        sys.exit(0)

    if dry_run:
        # Nur Vorschau ausgeben, keine Mail senden
        result = {
            "ok": True,
            "topic": topic,
            "article_count": len(top),
            "anthropic_key": bool(ANTHROPIC_KEY),
            "articles": [
                {"title": a["title"], "pub": a.get("pub",""), "pub_raw": a.get("pub_raw","")[:30], "link": a["link"][:60]}
                for a in top
            ]
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    # HTML bauen & senden
    html    = build_html(topic, top, today)
    subject = f"{cfg['subject_prefix']} {today}"
    log(f"  Sende: '{subject}'")
    result = send(subject, html)
    log(f"  Ergebnis: {result}")
    log(f"=== Fertig ===")


if __name__ == "__main__":
    main()
