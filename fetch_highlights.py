#!/usr/bin/env python3
"""Find official highlights videos for results in results.json and store them in highlights.json.
Usage: python3 fetch_highlights.py [--all] [--publish]
  default: only results without highlights yet; --all: re-check every result.
Method (no API key): official channels' RSS feeds (latest 15 each) + YouTube search page results,
filtered to the whitelisted official channels in config.json 'highlight_channels'. A video matches
a result only if its title mentions 'highlight', the opponent, and the correct score (either order)
or the match date. Embeddability is checked with YouTube oEmbed (401/403 = embedding disabled).
Nothing is downloaded or re-hosted; the page embeds YouTube's own player (youtube-nocookie.com)."""
import datetime, json, re, subprocess, sys, unicodedata, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
D = Path(__file__).parent
CFG = json.load(open(D/"config.json")); CLUB = CFG["club_name"]
CH = CFG["highlight_channels"]
UA = {"User-Agent": "Mozilla/5.0", "Accept-Language": "en-GB"}
def get(u):
    return urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=30).read().decode("utf-8", "replace")
def norm(s): return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()

def feed_videos():
    out = []
    for cid, name in CH.items():
        try: x = ET.fromstring(get(f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}"))
        except Exception: continue
        ns = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}
        for e in x.findall("a:entry", ns):
            out.append({"id": e.findtext("yt:videoId", namespaces=ns), "title": e.findtext("a:title", namespaces=ns), "channel_id": cid, "published": e.findtext("a:published", namespaces=ns)})
    return out

def search(q):
    h = get("https://www.youtube.com/results?search_query=" + urllib.parse.quote(q))
    m = re.search(r"var ytInitialData = (\{.*?\});</script>", h, re.S)
    if not m: return []
    out = []
    def walk(o):
        if isinstance(o, dict):
            if "videoRenderer" in o:
                v = o["videoRenderer"]; run = (v.get("ownerText", {}).get("runs") or [{}])[0]
                out.append({"id": v["videoId"], "title": "".join(r["text"] for r in v["title"]["runs"]),
                            "channel_id": run.get("navigationEndpoint", {}).get("browseEndpoint", {}).get("browseId"), "published": v.get("publishedTimeText", {}).get("simpleText")})
            for x in o.values(): walk(x)
        elif isinstance(o, list):
            for x in o: walk(x)
    walk(json.loads(m.group(1)))
    return out

def matches(v, r):
    if v["channel_id"] not in CH: return False
    t = norm(v["title"])
    if "highlight" not in t: return False
    if re.search(r"\b(u ?1[0-9]|u ?2[0-9]|under-?\d+|b team|women|wfc|swpl|legends)\b", t): return False
    d0 = datetime.date.fromisoformat(r["date"])
    if any(int(y) != d0.year for y in re.findall(r"\b(19\d\d|20\d\d)\b", t)): return False
    if not published_ok(v.get("published"), d0): return False
    h, a = r["home"], r["away"]
    opp = a["team"] if r["home_away"] == "Home" else h["team"]
    words = [w for w in re.split(r"[^a-z]+", norm(opp)) if len(w) > 3 and w not in ("united", "city", "saint")] or [norm(opp)]
    if not any(w in t for w in words) and norm(opp) not in t: return False
    hs, as_ = h["score"], a["score"]
    score = re.search(rf"\b{hs}\s*[-–]\s*{as_}\b", t) or re.search(rf"\b{as_}\s*[-–]\s*{hs}\b", t)
    d = datetime.date.fromisoformat(r["date"])
    date_ok = any(s in t for s in (d.strftime("%d %b %Y").lower(), d.strftime("%-d %b %Y").lower(), d.strftime("%d/%m/%y"), d.strftime("%d.%m.%y")))
    return bool(score or date_ok)

def published_ok(p, d):
    """Video must be published from the match day up to ~6 weeks after (approximate for relative times)."""
    if not p: return True
    today = datetime.date.today()
    m = re.match(r"(\d{4}-\d{2}-\d{2})", p)
    if m: pd = datetime.date.fromisoformat(m.group(1))
    else:
        m = re.search(r"(\d+)\s+(second|minute|min|hour|hr|day|week|month|year)", p)
        if not m: return True
        n, u = int(m.group(1)), m.group(2)
        days = {"second": 0, "minute": 0, "min": 0, "hour": 0, "hr": 0, "day": 1, "week": 7, "month": 30, "year": 365}[u] * n
        slack = {"month": 31, "year": 365, "week": 7}.get(u, 1)
        pd = today - datetime.timedelta(days=days)
        return (d - datetime.timedelta(days=slack)) <= pd <= (d + datetime.timedelta(days=42 + slack))
    return d - datetime.timedelta(days=1) <= pd <= d + datetime.timedelta(days=42)

def embeddable(vid):
    try:
        urllib.request.urlopen(urllib.request.Request("https://www.youtube.com/oembed?format=json&url=" + urllib.parse.quote(f"https://www.youtube.com/watch?v={vid}"), headers=UA), timeout=20)
        return True
    except urllib.error.HTTPError as e:
        return False if e.code in (401, 403) else None
    except Exception: return None

def main():
    res = json.load(open(D/"results.json"))
    hp = D/"highlights.json"; hl = json.load(open(hp)) if hp.exists() else {}
    feed = feed_videos()
    now = datetime.datetime.now().astimezone().strftime("%d %b %Y %H:%M %Z")
    for uid, r in res.items():
        if uid in hl and hl[uid].get("video_id") and "--all" not in sys.argv: continue
        h, a = r["home"]["team"], r["away"]["team"]
        d = datetime.date.fromisoformat(r["date"])
        cands = list(feed)
        for q in (f"{h} v {a} highlights {d:%B %Y}", f"{h} {r['home']['score']}-{r['away']['score']} {a} highlights"):
            try: cands += search(q)
            except Exception as e: print("search failed:", e)
        found = [v for v in cands if matches(v, r)]
        order = list(CH)  # prefer channels in config order (club first)
        found.sort(key=lambda v: order.index(v["channel_id"]))
        pick = None
        for v in found:
            emb = embeddable(v["id"])
            v["embeddable"] = emb
            if emb: pick = v; break
            pick = pick or v
        if pick:
            hl[uid] = {"date": r["date"], "video_id": pick["id"], "title": pick["title"], "channel": CH[pick["channel_id"]], "channel_id": pick["channel_id"],
                       "embeddable": pick["embeddable"], "url": f"https://www.youtube.com/watch?v={pick['id']}", "thumb": f"https://i.ytimg.com/vi/{pick['id']}/hqdefault.jpg", "checked": now}
        else:
            hl.setdefault(uid, {"date": r["date"], "video_id": None})["checked"] = now
        print(r["date"], h, "v", a, "->", (pick["channel"] if False else (CH[pick["channel_id"]] + " | " + pick["title"] + (" [embeddable]" if pick["embeddable"] else " [link-out]"))) if pick else "none found")
    json.dump(dict(sorted(hl.items(), key=lambda kv: kv[1]["date"], reverse=True)), open(hp, "w"), indent=1, ensure_ascii=False)
    subprocess.run([sys.executable, str(D/"build.py")], check=True)
    if "--publish" in sys.argv:
        subprocess.run(["git", "-C", str(D), "add", "-A"], check=True)
        if subprocess.run(["git", "-C", str(D), "diff", "--cached", "--quiet"]).returncode:
            subprocess.run(["git", "-C", str(D), "commit", "-qm", "Highlights update"], check=True)
            subprocess.run(["git", "-C", str(D), "push", "-q"], check=True)
if __name__ == "__main__": main()
