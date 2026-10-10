#!/usr/bin/env python3
"""Fetch the latest headlines from the RSS feed in config.json (news_feed_url) into news.json.
Usage: python3 fetch_news.py [--publish]. Stores headline, the feed's own short excerpt (trimmed),
thumbnail URL, published time (UK), author and link. No article text is copied."""
import datetime, email.utils, html, json, re, subprocess, sys, urllib.request
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo
from pathlib import Path
D = Path(__file__).parent
CFG = json.load(open(D/"config.json"))
raw = urllib.request.urlopen(urllib.request.Request(CFG["news_feed_url"], headers={"User-Agent": "Mozilla/5.0 (fixtures-bot)"}), timeout=30).read()
root = ET.fromstring(raw)
M = "{http://search.yahoo.com/mrss/}"
items = []
for it in root.iter("item"):
    g = lambda t: (it.findtext(t) or "").strip()
    desc = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", g("description")))).strip()
    if len(desc) > 220: desc = desc[:217].rsplit(" ", 1)[0] + "…"
    th = it.find(M + "thumbnail"); mc = it.find(M + "content")
    thumb = th.get("url") if th is not None else (mc.get("url") if mc is not None else None)
    pub = g("pubDate"); uk = ""
    if pub:
        dt = email.utils.parsedate_to_datetime(pub).astimezone(ZoneInfo("Europe/London"))
        uk = dt.strftime("%a %d %b %Y, %H:%M ") + dt.tzname()
    link = re.sub(r"\?ref=rss$", "", g("link"))
    items.append({"title": html.unescape(g("title")), "link": link, "excerpt": desc, "thumb": thumb, "published": pub, "published_uk": uk, "author": (re.sub(r"\S+@\S+\s*\|?\s*", "", g("author")).strip() or None)})
items.sort(key=lambda n: email.utils.parsedate_to_datetime(n["published"]) if n["published"] else datetime.datetime.min.replace(tzinfo=datetime.timezone.utc), reverse=True)
items = items[: CFG.get("news_limit", 20)]
if not items: sys.exit("No items parsed; news.json unchanged")
json.dump({"source": CFG["news_source_name"], "feed_url": CFG["news_feed_url"], "fetched": datetime.datetime.now(ZoneInfo("Europe/London")).strftime("%d %b %Y %H:%M %Z"), "items": items},
          open(D/"news.json", "w"), indent=1, ensure_ascii=False)
print(len(items), "items; newest:", items[0]["published_uk"], "-", items[0]["title"])
subprocess.run([sys.executable, str(D/"build.py")], check=True)
if "--publish" in sys.argv:
    subprocess.run(["git", "-C", str(D), "add", "-A"], check=True)
    if subprocess.run(["git", "-C", str(D), "diff", "--cached", "--quiet"]).returncode:
        subprocess.run(["git", "-C", str(D), "commit", "-qm", "News update"], check=True)
        subprocess.run(["git", "-C", str(D), "push", "-q"], check=True)
