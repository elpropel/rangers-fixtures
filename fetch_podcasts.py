#!/usr/bin/env python3
"""Fetch latest episodes from the podcast RSS feeds in config.json ('podcasts') into podcasts.json.
Usage: python3 fetch_podcasts.py [--publish]. Stores episode metadata + the feed's own enclosure URL
(audio is streamed from the publisher; nothing is re-hosted)."""
import datetime, email.utils, html, json, re, subprocess, sys, urllib.request
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo
from pathlib import Path
D = Path(__file__).parent
CFG = json.load(open(D/"config.json"))
IT = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"
UK = ZoneInfo("Europe/London")
def get(u): return urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0 (fixtures-bot)"}), timeout=30).read()
def dur(s):
    if not s: return None
    s = s.strip()
    if s.isdigit(): n = int(s)
    else:
        p = [int(x) for x in s.split(":") if x.isdigit()]; n = 0
        for x in p: n = n * 60 + x
    h, m = divmod(n // 60, 60)
    return f"{h}h {m:02d}m" if h else f"{m} min"
shows, eps = [], []
for s in CFG["podcasts"]:
    try: ch = ET.fromstring(get(s["feed"])).find("channel")
    except Exception as e: print(s["name"], "feed failed:", e); continue
    img = ch.find(IT + "image"); art = img.get("href") if img is not None else (ch.findtext("image/url") or None)
    shows.append({**s, "artwork": art})
    for it in ch.findall("item")[:15]:
        enc = it.find("enclosure")
        if enc is None or not (enc.get("type", "").startswith("audio")): continue
        pub = it.findtext("pubDate")
        try:
            dt = email.utils.parsedate_to_datetime(pub)
            if dt.tzinfo is None: dt = dt.replace(tzinfo=datetime.timezone.utc)
        except Exception: continue
        ei = it.find(IT + "image")
        eps.append({"show": s["name"], "title": html.unescape((it.findtext("title") or "").strip()), "published": dt.isoformat(),
                    "published_uk": dt.astimezone(UK).strftime("%a %d %b %Y, %H:%M ") + dt.astimezone(UK).tzname(),
                    "duration": dur(it.findtext(IT + "duration")), "audio": enc.get("url"), "type": enc.get("type"),
                    "artwork": ei.get("href") if ei is not None else art, "link": it.findtext("link")})
eps.sort(key=lambda e: e["published"], reverse=True)
eps = eps[: CFG.get("podcast_limit", 25)]
if not eps: sys.exit("No episodes; podcasts.json unchanged")
json.dump({"fetched": datetime.datetime.now(UK).strftime("%d %b %Y %H:%M %Z"), "shows": shows, "episodes": eps}, open(D/"podcasts.json", "w"), indent=1, ensure_ascii=False)
print(len(eps), "episodes from", len(shows), "shows; newest:", eps[0]["show"], "-", eps[0]["title"])
subprocess.run([sys.executable, str(D/"build.py")], check=True)
if "--publish" in sys.argv:
    subprocess.run(["git", "-C", str(D), "add", "-A"], check=True)
    if subprocess.run(["git", "-C", str(D), "diff", "--cached", "--quiet"]).returncode:
        subprocess.run(["git", "-C", str(D), "commit", "-qm", "Podcasts update"], check=True)
        subprocess.run(["git", "-C", str(D), "push", "-q"], check=True)
