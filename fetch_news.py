#!/usr/bin/env python3
"""
Soccer transfer news aggregator.

Pulls several free public RSS feeds, keeps only transfer-related stories,
then GROUPS them by subject: if lots of articles are about the same player,
that player shows up once as a collapsible section with all the article links
tucked inside. Stories with no clear player are grouped under their club.

Everything is sorted into three tiers:
    Manchester United  >  Premier League  >  other top-5 leagues / general

Pure Python standard library -- no pip installs required.
Runs on a daily schedule via GitHub Actions (see .github/workflows/update.yml).
"""

import hashlib
import html
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

# ---------------------------------------------------------------------------
# 1. SOURCES  (all free, no API key, no login)
# ---------------------------------------------------------------------------
FEEDS = [
    "https://news.google.com/rss/search?q=Manchester+United+transfer&hl=en-GB&gl=GB&ceid=GB:en",
    "https://news.google.com/rss/search?q=Premier+League+transfer&hl=en-GB&gl=GB&ceid=GB:en",
    "https://news.google.com/rss/search?q=football+transfer+done+deal&hl=en-GB&gl=GB&ceid=GB:en",
    "https://news.google.com/rss/search?q=La+Liga+OR+Serie+A+OR+Bundesliga+OR+Ligue+1+transfer&hl=en-GB&gl=GB&ceid=GB:en",
    "https://www.theguardian.com/football/transfer-window/rss",
    "https://www.theguardian.com/football/rss",
    "https://feeds.bbci.co.uk/sport/football/rss.xml",
    "https://www.skysports.com/rss/12040",
]

# ---------------------------------------------------------------------------
# 2. TRANSFER FILTER + CLUB / TIER RULES
# ---------------------------------------------------------------------------
TRANSFER_WORDS = [
    "transfer", "sign", "signs", "signed", "signing", "loan", "fee", "bid",
    "medical", "here we go", "joins", "join", "agree", "agreement", "deal",
    "contract", "swoop", "target", "linked", "links", "release clause",
    "sell", "sold", "buy", "move", "wages", "swap",
]

MAN_UTD = ["manchester united", "man utd", "man united", "man u ", "mufc",
           "old trafford", "red devils"]

# (keyword, display name, tier).  Tier 1 = Premier League, tier 2 = other top-5.
CLUBS = [
    ("manchester city", "Manchester City", 1), ("man city", "Manchester City", 1),
    ("arsenal", "Arsenal", 1), ("aston villa", "Aston Villa", 1),
    ("liverpool", "Liverpool", 1), ("chelsea", "Chelsea", 1),
    ("tottenham", "Tottenham", 1), ("spurs", "Tottenham", 1),
    ("newcastle", "Newcastle", 1), ("west ham", "West Ham", 1),
    ("brighton", "Brighton", 1), ("everton", "Everton", 1),
    ("nottingham forest", "Nottingham Forest", 1),
    ("crystal palace", "Crystal Palace", 1), ("brentford", "Brentford", 1),
    ("fulham", "Fulham", 1), ("bournemouth", "Bournemouth", 1),
    ("wolves", "Wolves", 1), ("wolverhampton", "Wolves", 1),
    ("leeds", "Leeds", 1), ("burnley", "Burnley", 1),
    ("sunderland", "Sunderland", 1), ("leicester", "Leicester", 1),
    ("ipswich", "Ipswich", 1), ("southampton", "Southampton", 1),
    ("sheffield united", "Sheffield United", 1), ("luton", "Luton", 1),
    ("real madrid", "Real Madrid", 2), ("barcelona", "Barcelona", 2),
    ("atletico", "Atletico Madrid", 2), ("sevilla", "Sevilla", 2),
    ("valencia", "Valencia", 2), ("villarreal", "Villarreal", 2),
    ("real betis", "Real Betis", 2), ("athletic bilbao", "Athletic Bilbao", 2),
    ("bayern", "Bayern Munich", 2), ("borussia dortmund", "Borussia Dortmund", 2),
    ("dortmund", "Borussia Dortmund", 2), ("leipzig", "RB Leipzig", 2),
    ("leverkusen", "Bayer Leverkusen", 2), ("juventus", "Juventus", 2),
    ("inter milan", "Inter Milan", 2), ("ac milan", "AC Milan", 2),
    ("napoli", "Napoli", 2), ("roma", "Roma", 2), ("lazio", "Lazio", 2),
    ("atalanta", "Atalanta", 2), ("fiorentina", "Fiorentina", 2),
    ("psg", "PSG", 2), ("paris saint-germain", "PSG", 2),
    ("marseille", "Marseille", 2), ("monaco", "Monaco", 2),
    ("lyon", "Lyon", 2), ("lille", "Lille", 2),
]

TIER_MAN_UTD, TIER_PL, TIER_OTHER = 0, 1, 2

# Words that are capitalized but are NOT player names (clubs, leagues, generic).
GENERIC_STOP = {
    "transfer", "news", "deal", "deals", "loan", "fee", "bid", "medical",
    "contract", "agree", "agreement", "sign", "signing", "signs", "signed",
    "target", "targets", "move", "swoop", "swap", "wages", "clause", "release",
    "here", "go", "latest", "update", "updates", "report", "reports", "sources",
    "source", "exclusive", "confirmed", "official", "done", "eyeing", "eye",
    "eyes", "set", "could", "would", "want", "wants", "wanted", "join", "joins",
    "joining", "leave", "leaves", "leaving", "star", "ace", "boss", "manager",
    "coach", "striker", "midfielder", "defender", "goalkeeper", "winger",
    "forward", "summer", "winter", "window", "january", "february", "march",
    "april", "may", "june", "july", "august", "september", "october",
    "november", "december", "monday", "tuesday", "wednesday", "thursday",
    "friday", "saturday", "sunday", "champions", "europa", "uefa", "fifa",
    "world", "cup", "euro", "euros", "league", "premier", "liga", "serie",
    "bundesliga", "ligue", "england", "spain", "italy", "france", "germany",
    "portugal", "brazil", "argentina", "netherlands", "dutch", "spanish",
    "italian", "french", "german", "english", "british", "bbc", "sky",
    "sports", "guardian", "google", "athletic", "mirror", "sun", "express",
    "mail", "telegraph", "times", "standard", "goal", "football", "fabrizio",
    "romano", "new", "how", "why", "what", "when", "who", "revealed", "closing",
    "close", "talks", "talk", "verge", "brink", "reject", "rejects", "rejected",
    "accept", "accepts", "offer", "offers", "price", "valuation", "swap",
}
# add every word that appears in a club name so "Real Madrid", "Aston Villa"
# etc. are never mistaken for a player's name.
for _kw in MAN_UTD:
    GENERIC_STOP.update(_kw.split())
for _kw, _disp, _t in CLUBS:
    GENERIC_STOP.update(_kw.split())
    GENERIC_STOP.update(_disp.lower().split())


def is_transfer(text):
    t = text.lower()
    return any(w in t for w in TRANSFER_WORDS)


def detect_clubs(text):
    """Return a list of (display_name, tier) for EVERY club mentioned,
    in priority order (Man Utd first), de-duplicated. Empty list if none."""
    t = text.lower()
    found = []
    if any(k in t for k in MAN_UTD):
        found.append(("Manchester United", TIER_MAN_UTD))
    seen = {d for d, _ in found}
    for kw, disp, tier in CLUBS:
        if kw in t and disp not in seen:
            found.append((disp, tier))
            seen.add(disp)
    return found[:3]


# ---------------------------------------------------------------------------
# 3. PLAYER-NAME DETECTION  (free, no AI -- just capitalized-name patterns)
# ---------------------------------------------------------------------------
TOKEN_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ'’.\-]*")


def _is_name_word(tok):
    if len(tok) < 2 or not tok[0].isupper() or tok.isupper():
        return False
    core = tok.replace("'", "").replace("’", "").replace("-", "").replace(".", "")
    if not core.isalpha():
        return False
    return tok.lower().strip(".") not in GENERIC_STOP


def detect_names(title):
    """
    Return a list of (full_name, surname) for EVERY player named in the title,
    so an article about two players can be cross-listed under both.  A name =
    two or three capitalized words in a row that aren't clubs/leagues/generic.
    """
    tokens = TOKEN_RE.findall(title)
    alpha = [t for t in tokens if t.replace("'", "").replace("’", "")
             .replace("-", "").replace(".", "").isalpha()]
    name_flags = [_is_name_word(t) for t in tokens]

    # If almost every word is capitalized it's a Title-Case headline -> unreliable.
    if alpha:
        cap_ratio = sum(1 for t in alpha if t[:1].isupper()) / len(alpha)
        if cap_ratio > 0.85 and len(alpha) >= 5:
            return []

    names, run = [], []

    def flush():
        if len(run) >= 2:
            phrase = " ".join(run[:3])
            names.append((phrase, run[min(len(run) - 1, 2)].lower().strip(".-")))

    for tok, flag in zip(tokens, name_flags):
        if flag:
            run.append(tok)
        else:
            flush()
            run = []
    flush()

    # De-duplicate by surname (keep first spelling); cap at 3 names per headline.
    seen, out = set(), []
    for full, sn in names:
        if sn not in seen:
            seen.add(sn)
            out.append((full, sn))
    return out[:3]


# ---------------------------------------------------------------------------
# 4. FETCH + PARSE
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
                return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d
            except Exception:
                pass
    return datetime.now(timezone.utc)


def source_name(url):
    for host, name in [("bbc", "BBC"), ("theguardian", "Guardian"),
                       ("skysports", "Sky Sports"), ("news.google", "Google News")]:
        if host in url:
            return name
    return "News"


MEDIA = "{http://search.yahoo.com/mrss/}"


def extract_image(item, desc):
    """Find a photo URL for a story from the RSS item, if the feed provides one."""
    best, best_w = None, -1
    for tag in (MEDIA + "content", MEDIA + "thumbnail"):
        for el in item.findall(tag):
            url = el.get("url")
            if not url:
                continue
            typ = el.get("type", "")
            if typ and not typ.startswith("image"):
                continue
            w = int(el.get("width") or 0)
            if w > best_w:
                best, best_w = url, w
    if best:
        return best
    enc = item.find("enclosure")
    if enc is not None and enc.get("type", "").startswith("image") and enc.get("url"):
        return enc.get("url")
    m = re.search(r'<img[^>]+src="([^"]+)"', desc or "")
    return m.group(1) if m else None


def collect():
    stories = []
    for url in FEEDS:
        try:
            root = ET.fromstring(fetch(url))
        except Exception as e:
            print(f"  skipped feed (error): {url}  ->  {e}")
            continue
        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            desc = (item.findtext("description") or "").strip()
            if not title or not link or not is_transfer(f"{title} {desc}"):
                continue
            stories.append({
                "title": title, "link": link, "date": parse_date(item),
                "source": source_name(url), "text": f"{title} {desc}",
                "image": extract_image(item, desc),
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
# 5. GROUP ARTICLES BY SUBJECT
# ---------------------------------------------------------------------------
def group_stories(stories):
    # First pass: detect all player names + all clubs + tier for each article.
    for s in stories:
        s["names"] = detect_names(s["title"])            # [(full, surname), ...]
        s["surnames"] = [sn for _, sn in s["names"]]
        s["clubs"] = detect_clubs(s["text"])             # [(display, tier), ...]
        s["tier"] = min((t for _, t in s["clubs"]), default=TIER_OTHER)

    # Learn known surnames + their best full-name label.
    fullname_for = {}
    for s in stories:
        for full, sn in s["names"]:
            fullname_for.setdefault(sn, Counter())[full] += 1
    known = set(fullname_for)

    # Second pass: rescue any KNOWN surname mentioned as a bare word (e.g. tabloid
    # Title-Case headlines, or "Rashford medical"), so those cross-list too.
    for s in stories:
        words = {w.lower().strip(".-") for w in TOKEN_RE.findall(s["title"])}
        for sn in known:
            if sn in words and sn not in s["surnames"]:
                s["surnames"].append(sn)

    # Build groups -- an article is added to EVERY player it names (cross-listed),
    # or to every club it mentions if no player was found.
    groups = {}

    def add(key, label, kind, story):
        groups.setdefault(key, {"label": label, "kind": kind, "arts": []})["arts"].append(story)

    for s in stories:
        if s["surnames"]:
            for sn in s["surnames"]:
                counts = fullname_for.get(sn)
                label = counts.most_common(1)[0][0] if counts else sn.title()
                add(("player", sn), label, "player", s)
        elif s["clubs"]:
            for disp, _tier in s["clubs"]:
                add(("club", disp), disp, "club", s)
        else:
            add(("general",), "General transfer news", "general", s)

    # Sort into tiers.  A group's tier = its highest-priority article.
    by_tier = {TIER_MAN_UTD: [], TIER_PL: [], TIER_OTHER: []}
    for g in groups.values():
        g["arts"].sort(key=lambda a: a["date"], reverse=True)
        g["tier"] = min(a["tier"] for a in g["arts"])
        g["latest"] = g["arts"][0]["date"]
        by_tier[g["tier"]].append(g)

    for tier in by_tier:
        by_tier[tier].sort(key=lambda g: (len(g["arts"]), g["latest"]), reverse=True)
    return by_tier


# ---------------------------------------------------------------------------
# 6. IMAGES: player thumbnails, club crests, colored-initials fallback
# ---------------------------------------------------------------------------
# Better search terms for the free crest lookup (TheSportsDB).
CREST_QUERY = {
    "Wolves": "Wolverhampton Wanderers", "PSG": "Paris Saint-Germain",
    "Inter Milan": "Inter Milan", "Tottenham": "Tottenham Hotspur",
    "West Ham": "West Ham United", "Atletico Madrid": "Atletico Madrid",
    "RB Leipzig": "RB Leipzig", "Bayer Leverkusen": "Bayer Leverkusen",
}


def avatar_color(name):
    """Stable, pleasant color derived from a name (for the initials badge)."""
    h = int(hashlib.md5(name.encode("utf-8")).hexdigest(), 16) % 360
    return f"hsl({h}, 45%, 48%)"


def initials_for(g):
    if g["kind"] == "general":
        return "TN"
    words = [w for w in re.split(r"[\s\-]+", g["label"]) if w and w[0].isalpha()]
    if len(words) >= 2:
        return (words[0][0] + words[1][0]).upper()
    return g["label"][:2].upper()


def get_crest(display, memo):
    """Look up a club crest URL from the free TheSportsDB API. Returns None on
    any failure so the tile falls back to clean initials -- never breaks."""
    if display in memo:
        return memo[display]
    query = CREST_QUERY.get(display, display)
    url = None
    try:
        api = ("https://www.thesportsdb.com/api/v1/json/3/searchteams.php?t="
               + urllib.parse.quote(query))
        req = urllib.request.Request(api, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=12) as r:
            teams = (json.loads(r.read()).get("teams") or [])
        if teams:
            url = teams[0].get("strBadge") or teams[0].get("strTeamBadge")
    except Exception:
        url = None
    memo[display] = url
    return url


def resolve_images(by_tier):
    memo = {}
    for groups in by_tier.values():
        for g in groups:
            g["initials"] = initials_for(g)
            g["color"] = avatar_color(g["label"])
            if g["kind"] == "club":
                g["img"], g["img_type"] = get_crest(g["label"], memo), "crest"
            elif g["kind"] == "player":
                g["img"] = next((a["image"] for a in g["arts"] if a.get("image")), None)
                g["img_type"] = "photo"
            else:
                g["img"], g["img_type"] = None, "photo"


# ---------------------------------------------------------------------------
# 7. BUILD THE HTML PAGE
# ---------------------------------------------------------------------------
def when(d):
    mins = int((datetime.now(timezone.utc) - d).total_seconds() // 60)
    if mins < 60:
        return f"{max(mins, 0)} min ago"
    if mins < 1440:
        return f"{mins // 60} hr ago"
    days = mins // 1440
    return f"{days} day{'s' if days != 1 else ''} ago"


def esc(x):
    return html.escape(x)


def render_tile(g):
    if g["img"]:
        cls = "crest" if g["img_type"] == "crest" else "photo"
        imgtag = (f'<img class="{cls}" src="{esc(g["img"])}" loading="lazy" '
                  f'alt="" onerror="this.remove()">')
    else:
        imgtag = ""
    thumb = (f'<span class="thumb" style="background:{g["color"]}">'
             f'{esc(g["initials"])}{imgtag}</span>')
    links = "".join(
        f'<a href="{esc(a["link"])}" target="_blank" rel="noopener">'
        f'<span class="lhead">{esc(a["title"])}</span>'
        f'<span class="lmeta">{esc(a["source"])} &middot; {when(a["date"])}</span></a>'
        for a in g["arts"][:12]
    )
    return (
        '<details class="tile"><summary>'
        f'{thumb}'
        f'<span class="tname">{esc(g["label"])}<small>{when(g["latest"])}</small></span>'
        f'<span class="badge">{len(g["arts"])}</span></summary>'
        f'<div class="links">{links}</div></details>'
    )


def render_column(title, sub, cls, groups):
    if not groups:
        body = '<div class="empty">Nothing new here yet.</div>'
    else:
        body = "\n".join(render_tile(g) for g in groups[:60])
    return (f'<section class="column {cls}"><div class="colhead">'
            f'<h2>{title}</h2><span class="sub">{sub}</span></div>{body}</section>')


def build_html(by_tier):
    updated = datetime.now(timezone.utc).strftime("%a %d %b %Y, %H:%M UTC")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Transfer News</title>
<style>
  :root {{ --bg:#e9e3d5; --tile:#ffffff; --ink:#20242c; --muted:#727889;
    --line:#eceef2; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--ink);
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
    padding:26px 18px 70px; }}
  .top {{ text-align:center; margin:0 auto 28px; }}
  h1 {{ font-size:27px; margin:0 0 6px; letter-spacing:.5px; }}
  .updated {{ color:var(--muted); font-size:13px; }}
  .board {{ display:grid; grid-template-columns:repeat(3,1fr); gap:22px;
    max-width:1240px; margin:0 auto; align-items:start; }}
  @media (max-width:920px) {{ .board {{ grid-template-columns:1fr; }} }}
  .colhead {{ text-align:center; margin-bottom:18px; }}
  .column h2 {{ margin:0; font-size:15px; letter-spacing:1.5px;
    text-transform:uppercase; display:inline-block; padding:0 0 5px;
    border-bottom:3px solid var(--accent); color:var(--accentText); }}
  .colhead .sub {{ display:block; color:var(--muted); font-size:12px; margin-top:7px; }}

  .utd    {{ --accent:#e01a2b; --accentText:#c0121f; --glow:224,26,43; }}
  .pl     {{ --accent:#b9c2d6; --accentText:#6b7488; --glow:150,168,205; }}
  .other  {{ --accent:#2b3a67; --accentText:#2b3a67; --glow:52,68,120; }}

  .tile {{ position:relative; background:var(--tile); border-radius:14px;
    margin-bottom:17px; border:1px solid rgba(0,0,0,.05);
    box-shadow:0 12px 22px -8px rgba(var(--glow),.55), 0 2px 5px rgba(0,0,0,.05); }}
  .tile::after {{ content:""; position:absolute; left:16px; right:16px; bottom:-3px;
    height:5px; border-radius:6px; background:var(--accent); filter:blur(3px);
    opacity:.85; }}
  .tile > summary {{ list-style:none; cursor:pointer; display:flex;
    align-items:center; gap:12px; padding:12px 14px; }}
  .tile > summary::-webkit-details-marker {{ display:none; }}
  .thumb {{ position:relative; width:46px; height:46px; flex:0 0 auto;
    border-radius:11px; overflow:hidden; display:flex; align-items:center;
    justify-content:center; color:#fff; font-weight:700; font-size:15px; }}
  .thumb img.photo {{ position:absolute; inset:0; width:100%; height:100%;
    object-fit:cover; }}
  .thumb img.crest {{ position:absolute; inset:0; width:100%; height:100%;
    object-fit:contain; background:#fff; padding:4px; }}
  .tname {{ flex:1; font-weight:600; font-size:14.5px; color:var(--ink);
    line-height:1.25; }}
  .tname small {{ display:block; font-weight:400; color:var(--muted);
    font-size:11.5px; margin-top:2px; }}
  .badge {{ flex:0 0 auto; background:#f0f1f5; color:#586074; border-radius:999px;
    padding:3px 10px; font-size:12px; font-weight:600; }}
  .links {{ padding:2px 16px 12px 72px; }}
  .links a {{ display:block; padding:9px 0; border-top:1px solid var(--line);
    text-decoration:none; }}
  .links a:hover .lhead {{ color:#000; }}
  .lhead {{ display:block; font-size:13px; line-height:1.4; color:var(--ink); }}
  .lmeta {{ display:block; font-size:11px; color:var(--muted); margin-top:2px; }}
  .empty {{ color:var(--muted); font-size:14px; text-align:center; padding:12px 0; }}
</style>
</head>
<body>
  <div class="top">
    <h1>&#9917; Transfer News</h1>
    <div class="updated">Updated {updated} &middot; tap a tile to see its stories</div>
  </div>
  <div class="board">
{render_column('Manchester United', 'top priority', 'utd', by_tier[TIER_MAN_UTD])}
{render_column('Premier League', 'the rest of the PL', 'pl', by_tier[TIER_PL])}
{render_column('Other &amp; General', 'La Liga, Serie A, Bundesliga, Ligue 1 &amp; more', 'other', by_tier[TIER_OTHER])}
  </div>
</body>
</html>"""


def main():
    print("Fetching feeds...")
    stories = dedupe(collect())
    print(f"Kept {len(stories)} transfer stories.")
    by_tier = group_stories(stories)
    resolve_images(by_tier)
    n_groups = sum(len(v) for v in by_tier.values())
    print(f"Grouped into {n_groups} subjects.")
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(build_html(by_tier))
    print("Wrote index.html")


if __name__ == "__main__":
    main()
