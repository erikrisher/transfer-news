#!/usr/bin/env python3
"""
Soccer transfer news aggregator.

Pulls several free public RSS feeds, keeps only transfer-related stories,
sorts them into three tiers (Manchester United > Premier League > other),
removes duplicates, and writes a single self-contained index.html page.

Pure Python standard library -- no pip installs required.
Runs on a daily schedule via GitHub Actions (see .github/workflows/update.yml).
"""

import html
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

# ---------------------------------------------------------------------------
# 1. SOURCES  (all free, no API key, no login)
# ---------------------------------------------------------------------------
# If any single feed is down on a given day, the script just skips it and
# carries on with the rest -- one broken source never breaks the page.
FEEDS = [
    # Google News is the most reliable + already transfer-focused via the query
    "https://news.google.com/rss/search?q=Manchester+United+transfer&hl=en-GB&gl=GB&ceid=GB:en",
    "https://news.google.com/rss/search?q=Premier+League+transfer&hl=en-GB&gl=GB&ceid=GB:en",
    "https://news.google.com/rss/search?q=football+transfer+done+deal&hl=en-GB&gl=GB&ceid=GB:en",
    "https://news.google.com/rss/search?q=La+Liga+OR+Serie+A+OR+Bundesliga+OR+Ligue+1+transfer&hl=en-GB&gl=GB&ceid=GB:en",
    # Major outlets (rock-solid RSS)
    "https://www.theguardian.com/football/transfer-window/rss",
    "https://www.theguardian.com/football/rss",
    "https://feeds.bbci.co.uk/sport/football/rss.xml",
    "https://www.skysports.com/rss/12040",
]

# ---------------------------------------------------------------------------
# 2. FILTERING + TIERING RULES
# ---------------------------------------------------------------------------
# Only keep a story if its title/summary mentions one of these transfer words.
TRANSFER_WORDS = [
    "transfer", "sign", "signs", "signed", "signing", "loan", "fee", "bid",
    "medical", "here we go", "joins", "join", "agree", "agreement", "deal",
    "contract", "swoop", "target", "linked", "links", "release clause",
    "sell", "sold", "buy", "move", "wages", "swap",
]

MAN_UTD = [
    "manchester united", "man utd", "man united", "man u ", "mufc",
    "old trafford", "red devils",
]

# Premier League clubs (kept broad so it survives promotions/relegations).
PREMIER_LEAGUE = [
    "premier league", "arsenal", "aston villa", "bournemouth", "brentford",
    "brighton", "chelsea", "crystal palace", "everton", "fulham", "liverpool",
    "manchester city", "man city", "newcastle", "nottingham forest",
    "tottenham", "spurs", "west ham", "wolves", "wolverhampton", "leeds",
    "burnley", "sunderland", "leicester", "ipswich", "southampton",
    "sheffield united", "luton",
]

# Other big clubs / leagues in the top 5 (La Liga, Serie A, Bundesliga, Ligue 1).
OTHER_TOP5 = [
    "la liga", "serie a", "bundesliga", "ligue 1", "real madrid", "barcelona",
    "atletico", "sevilla", "valencia", "villarreal", "real betis",
    "athletic bilbao", "bayern", "borussia dortmund", "dortmund", "leipzig",
    "leverkusen", "juventus", "inter milan", "ac milan", "milan", "napoli",
    "roma", "lazio", "atalanta", "fiorentina", "psg", "paris saint-germain",
    "marseille", "monaco", "lyon", "lille",
]

TIER_MAN_UTD, TIER_PL, TIER_OTHER = 0, 1, 2


def classify(text):
    """Return the tier for a story based on which clubs/leagues it mentions."""
    t = text.lower()
    if any(k in t for k in MAN_UTD):
        return TIER_MAN_UTD
    if any(k in t for k in PREMIER_LEAGUE):
        return TIER_PL
    if any(k in t for k in OTHER_TOP5):
        return TIER_OTHER
    return TIER_OTHER  # general transfer news still shown, in the bottom tier


def is_transfer(text):
    t = text.lower()
    return any(w in t for w in TRANSFER_WORDS)


# ---------------------------------------------------------------------------
# 3. FETCH + PARSE
# ---------------------------------------------------------------------------
def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read()


def parse_date(item):
    for tag in ("pubDate", "published", "updated"):
        el = item.find(tag)
        if el is not None and el.text:
            try:
                d = parsedate_to_datetime(el.text)
                if d.tzinfo is None:
                    d = d.replace(tzinfo=timezone.utc)
                return d
            except Exception:
                pass
    return datetime.now(timezone.utc)


def source_name(link):
    for host, name in [
        ("bbc", "BBC"), ("theguardian", "Guardian"), ("skysports", "Sky Sports"),
        ("news.google", "Google News"),
    ]:
        if host in link:
            return name
    # Google News wraps the real publisher inside the title as " - Publisher"
    return "News"


def collect():
    stories = []
    for url in FEEDS:
        try:
            raw = fetch(url)
            root = ET.fromstring(raw)
        except Exception as e:
            print(f"  skipped feed (error): {url}  ->  {e}")
            continue

        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            desc = (item.findtext("description") or "").strip()
            if not title or not link:
                continue
            blob = f"{title} {desc}"
            if not is_transfer(blob):
                continue
            stories.append({
                "title": title,
                "link": link,
                "date": parse_date(item),
                "tier": classify(blob),
                "source": source_name(url),
            })
    return stories


def dedupe(stories):
    seen_titles, seen_links, out = set(), set(), []
    for s in sorted(stories, key=lambda x: x["date"], reverse=True):
        key = s["title"].lower()[:70]
        if key in seen_titles or s["link"] in seen_links:
            continue
        seen_titles.add(key)
        seen_links.add(s["link"])
        out.append(s)
    return out


# ---------------------------------------------------------------------------
# 4. BUILD THE HTML PAGE
# ---------------------------------------------------------------------------
def when(d):
    """Human-friendly 'x hours ago' style label."""
    delta = datetime.now(timezone.utc) - d
    mins = int(delta.total_seconds() // 60)
    if mins < 60:
        return f"{max(mins,0)} min ago"
    hours = mins // 60
    if hours < 24:
        return f"{hours} hr ago"
    days = hours // 24
    return f"{days} day{'s' if days != 1 else ''} ago"


def card(s):
    return f"""      <a class="card" href="{html.escape(s['link'])}" target="_blank" rel="noopener">
        <div class="headline">{html.escape(s['title'])}</div>
        <div class="meta">{html.escape(s['source'])} &middot; {when(s['date'])}</div>
      </a>"""


def section(title, subtitle, cls, items, limit):
    if not items:
        body = '<div class="empty">Nothing new here right now &mdash; check back later.</div>'
    else:
        body = "\n".join(card(s) for s in items[:limit])
    return f"""    <section class="tier {cls}">
      <h2>{title} <span class="sub">{subtitle}</span></h2>
{body}
    </section>"""


def build_html(stories):
    utd = [s for s in stories if s["tier"] == TIER_MAN_UTD]
    pl = [s for s in stories if s["tier"] == TIER_PL]
    other = [s for s in stories if s["tier"] == TIER_OTHER]
    updated = datetime.now(timezone.utc).strftime("%a %d %b %Y, %H:%M UTC")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Transfer News</title>
<style>
  :root {{
    --bg: #0b0d12; --card: #151922; --text: #e8ebf2; --muted: #8b93a7;
    --utd: #e01a2b; --pl: #ffffff;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; background: var(--bg); color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    padding: 20px 16px 60px;
  }}
  header {{ max-width: 760px; margin: 0 auto 8px; }}
  h1 {{ font-size: 26px; margin: 0 0 4px; letter-spacing: .5px; }}
  .updated {{ color: var(--muted); font-size: 13px; }}
  .legend {{ display: flex; gap: 16px; flex-wrap: wrap; font-size: 12px;
    color: var(--muted); margin: 12px 0 4px; }}
  .dot {{ display: inline-block; width: 10px; height: 10px; border-radius: 50%;
    margin-right: 5px; vertical-align: middle; }}
  main {{ max-width: 760px; margin: 0 auto; }}
  .tier {{ margin-top: 30px; }}
  .tier h2 {{ font-size: 17px; margin: 0 0 12px; text-transform: uppercase;
    letter-spacing: 1px; }}
  .tier h2 .sub {{ text-transform: none; letter-spacing: 0; color: var(--muted);
    font-weight: 400; font-size: 13px; margin-left: 6px; }}
  .card {{ display: block; background: var(--card); text-decoration: none;
    color: var(--text); padding: 14px 16px; border-radius: 10px;
    margin-bottom: 10px; border-left: 4px solid transparent;
    transition: transform .08s ease; }}
  .card:hover {{ transform: translateX(3px); }}
  .headline {{ font-size: 15px; line-height: 1.4; font-weight: 500; }}
  .meta {{ color: var(--muted); font-size: 12px; margin-top: 6px; }}
  .empty {{ color: var(--muted); font-size: 14px; padding: 8px 0; }}

  /* Manchester United -- red neon glow */
  .utd .card {{ border-left-color: var(--utd);
    box-shadow: 0 0 14px rgba(224,26,43,.32); }}
  .utd h2 {{ color: var(--utd); }}
  /* Premier League -- white neon glow */
  .pl .card {{ border-left-color: var(--pl);
    box-shadow: 0 0 14px rgba(255,255,255,.22); }}
  .pl h2 {{ color: var(--pl); }}
  /* Everything else -- calm, no glow */
  .other .card {{ border-left-color: #38405a; }}
  .other h2 {{ color: var(--muted); }}
</style>
</head>
<body>
  <header>
    <h1>&#9917; Transfer News</h1>
    <div class="updated">Updated {updated}</div>
    <div class="legend">
      <span><span class="dot" style="background:var(--utd)"></span>Man Utd</span>
      <span><span class="dot" style="background:var(--pl)"></span>Premier League</span>
      <span><span class="dot" style="background:#38405a"></span>Other / general</span>
    </div>
  </header>
  <main>
{section('&#128308; Manchester United', 'top priority', 'utd', utd, 25)}
{section('&#9898; Premier League', 'the rest of the PL', 'pl', pl, 40)}
{section('&#127758; Other Top-5 Leagues &amp; General', 'La Liga, Serie A, Bundesliga, Ligue 1 &amp; more', 'other', other, 40)}
  </main>
</body>
</html>"""


def main():
    print("Fetching feeds...")
    stories = dedupe(collect())
    print(f"Kept {len(stories)} transfer stories.")
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(build_html(stories))
    print("Wrote index.html")


if __name__ == "__main__":
    main()
