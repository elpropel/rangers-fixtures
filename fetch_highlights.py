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

def team_words(name):
    ws = [w for w in re.split(r"[^a-z]+", norm(name)) if len(w) > 3 and w not in ("united", "city", "saint", "club")]
    return ws or [norm(name)]
def has_team(t, name): return any(w in t for w in team_words(name))
COMP_WORDS = {"premiership": ("premiership",), "league cup": ("league cup", "premier sports cup"), "scottish cup": ("scottish cup",),
              "europa": ("europa",), "conference": ("conference",), "champions": ("champions league",)}
def check(v, r, now=None):
    """Return (ok, reason). Strict: wrong clip is worse than none."""
    if v["channel_id"] not in CH: return False, "not an official channel"
    t = norm(v["title"] + " " + (v.get("description") or ""))
    if "highlight" not in t: return False, "not a highlights video"
    if re.search(r"\b(u ?1[0-9]|u ?2[0-9]|under-?\d+|b team|women|wfc|swpl|legends)\b", t): return False, "youth/women/legends video"
    h, a = r["home"], r["away"]
    if not (has_team(t, h["team"]) and has_team(t, a["team"])): return False, "doesn't name both teams"
    d = datetime.date.fromisoformat(r["date"])
    if any(int(y) != d.year for y in re.findall(r"\b(19\d\d|20\d\d)\b", t)): return False, "different year in title"
    hs, as_ = h["score"], a["score"]
    hw = "|".join(map(re.escape, team_words(h["team"]))); aw = "|".join(map(re.escape, team_words(a["team"])))
    score_ok = bool(re.search(rf"(?:{hw})[a-z .]*?\s{hs}\s*[-–]\s*{as_}\s+[a-z .]*?(?:{aw})", t))
    club_date_ok = False
    if not score_ok and CH.get(v["channel_id"], "").startswith(CLUB + " FC (Official)"):
        # Club channel exception (approved by Andy): exact match date + both teams in home-v-away order, no score needed.
        tt = norm(v["title"])
        dates = (d.strftime("%d %b %Y").lower(), d.strftime("%-d %b %Y").lower())
        club_date_ok = any(s in tt for s in dates) and bool(re.search(rf"(?:{hw})[a-z .]*?\sv\s+[a-z .]*?(?:{aw})", tt))
    if not (score_ok or club_date_ok): return False, f"exact score {hs}-{as_} (home first) not in title/description"
    comp = norm(r["competition"])
    key = next((k for k in COMP_WORDS if k in comp), None)
    date_strs = (d.strftime("%d %b %Y").lower(), d.strftime("%-d %b %Y").lower(), d.strftime("%d/%m/%y"), d.strftime("%d.%m.%y"))
    if key and not club_date_ok and not any(w in t for w in COMP_WORDS[key]) and not any(s in t for s in date_strs):
        return False, "competition/date not confirmed"
    ok, why = published_ok(v.get("published"), r, now)
    if not ok: return False, why
    return True, "pass"
def matches(v, r): return check(v, r)[0]

def published_ok(p, r, now=None):
    """Published after FT (kick-off + 105 min) and within 10 days. Accepts ISO time or YouTube relative text."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    ko = r.get("kickoff_uk") or "12:00"
    from zoneinfo import ZoneInfo
    ft = datetime.datetime.fromisoformat(f"{r['date']}T{ko}").replace(tzinfo=ZoneInfo("Europe/London")) + datetime.timedelta(minutes=105)
    latest = ft + datetime.timedelta(days=10)
    if not p: return False, "publish time unknown"
    m = re.match(r"\d{4}-\d{2}-\d{2}T", p)
    if m:
        pd = datetime.datetime.fromisoformat(p.replace("Z", "+00:00"))
        if pd < ft: return False, f"published {pd:%d %b %Y %H:%M} UTC, before full time"
        if pd > latest: return False, "published more than 10 days after match"
        return True, ""
    m = re.search(r"(\d+)\s*(seconds?|minutes?|mins?|hours?|hrs?|hr|days?|d|weeks?|wks?|wk|months?|mo|years?|yrs?|y)\b", p.lower())
    if not m: return False, f"unparseable publish time '{p}'"
    n, u = int(m.group(1)), m.group(2)
    unit = (60 if u.startswith(("min",)) else 1 if u.startswith("s") else 3600 if u.startswith("h") else 86400 if u.startswith("d") else 7*86400 if u.startswith("w") else 30*86400 if u.startswith("mo") else 365*86400)
    # relative age N units means between N and N+1 units ago
    oldest = now - datetime.timedelta(seconds=(n + 1) * unit); newest = now - datetime.timedelta(seconds=n * unit)
    if newest < ft: return False, f"published '{p}' - before this match's full time (likely an older fixture)"
    if oldest > latest: return False, f"published '{p}' - more than 10 days after match"
    return True, ""

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
        if uid in hl and hl[uid].get("video_id"): hl.pop(uid)
        h, a = r["home"]["team"], r["away"]["team"]
        d = datetime.date.fromisoformat(r["date"])
        cands = list(feed)
        for q in (f"{h} v {a} highlights {d:%B %Y}", f"{h} {r['home']['score']}-{r['away']['score']} {a} highlights"):
            try: cands += search(q)
            except Exception as e: print("search failed:", e)
        found = [v for v in cands if matches(v, r)]
        found = list({v["id"]: v for v in found}.values())
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
                       "embeddable": pick["embeddable"], "url": f"https://www.youtube.com/watch?v={pick['id']}", "thumb": f"https://i.ytimg.com/vi/{pick['id']}/hqdefault.jpg", "published": pick.get("published"), "checked": now}
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
