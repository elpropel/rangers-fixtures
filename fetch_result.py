#!/usr/bin/env python3
"""Fetch final results from BBC Sport match pages into results.json.

Usage:
  python3 fetch_result.py YYYY-MM-DD [--publish]      # one match day
  python3 fetch_result.py --backfill YYYY-MM [--publish]  # every result from that month to now
Reads the structured match data BBC embeds in each match page (window.__INITIAL_DATA__).
Only status PostEvent with periodLabel FT/AET/pens is stored as final; nothing is invented and
fields BBC doesn't provide are left empty/null.
"""
import datetime, hashlib, json, re, subprocess, sys, urllib.request
from pathlib import Path
D = Path(__file__).parent
CFG = json.load(open(D/"config.json"))
CLUB = CFG["club_name"]
SLUG = CFG.get("bbc_team_slug", CLUB.lower().replace(" ", "-"))
UA = {"User-Agent": "Mozilla/5.0 (fixtures-bot)"}
BBC = "https://www.bbc.co.uk"

def get(u): return urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=30).read().decode("utf-8", "replace")

def month_links(ym):
    # BBC's ?filter=results page can lag behind; also scan the unfiltered month page.
    h = get(f"{BBC}/sport/football/teams/{SLUG}/scores-fixtures/{ym}?filter=results") + get(f"{BBC}/sport/football/teams/{SLUG}/scores-fixtures/{ym}")
    seen = []
    for l in re.findall(r'href="(/sport/football/live/[a-z0-9]+|/sport/football/[0-9]{6,})"', h):
        if l not in seen: seen.append(l)
    return [BBC + l for l in seen]

def events(url):
    h = get(url)
    m = re.search(r'window\.__INITIAL_DATA__\s*=\s*"(.*?)";</script>', h, re.S)
    if not m: return []
    data = json.loads(json.loads('"' + m.group(1) + '"'))
    out = []
    def walk(o):
        if isinstance(o, dict):
            if isinstance(o.get("home"), dict) and isinstance(o.get("away"), dict) and "periodLabel" in o and CLUB in (o["home"].get("fullName"), o["away"].get("fullName")):
                if o.get("urn") not in [e.get("urn") for e in out]: out.append(o)
            for v in o.values(): walk(v)
        elif isinstance(o, list):
            for v in o: walk(v)
    walk(data)
    return out

def month_summaries(ym):
    """Score-only fallback for matches BBC lists without a match page (e.g. friendlies)."""
    h = get(f"{BBC}/sport/football/teams/{SLUG}/scores-fixtures/{ym}?filter=results")
    h = re.sub(r"<script.*?</script>|<style.*?</style>", "", h, flags=re.S)
    out, day, comp = [], None, None
    for x in re.finditer(r'<h2[^>]*>([^<]+)</h2>|<h3[^>]*>([^<]+)</h3>|>([^<>]{3,140} at Full time[^<>]{0,160})<', h):
        a, b, c = x.groups()
        if a and re.match(r"\w+day \d", a): day = a
        elif a: comp = a
        if b and re.match(r"\w+day \d", b): day = b
        elif b: comp = b
        if c and day:
            m = re.match(r"(.+?) (\d+) , (.+?) (\d+) at Full time", c)
            if not m: continue
            dd = datetime.datetime.strptime(re.sub(r"(\d+)(st|nd|rd|th)", r"\1", day) + " " + ym[:4], "%A %d %B %Y").date().isoformat()
            out.append(dict(date=dd, comp=comp, home=m.group(1), hs=m.group(2), away=m.group(3), as_=m.group(4), summary=c))
    return out

def csv_lookup(date, opp_names):
    import csv
    for r in csv.DictReader(open(CFG["csv"])):
        try: d = datetime.datetime.strptime(r["Date"], "%a %d %b %Y").date().isoformat()
        except ValueError: continue
        if d == date and any(r["Opponent"].split()[0].lower() in n.lower() for n in opp_names if n):
            return r["Competition"], r["Opponent"]
    return None

def to_result(e, url):
    if e.get("status") != "PostEvent": return None
    pl = (e.get("periodLabel") or {}).get("value", "")
    if pl not in ("FT", "AET", "Pens", "PENS", "P", "After Pens") and "pen" not in pl.lower() and pl != "AET": return None
    d = datetime.datetime.strptime(e["date"], "%a %d %b %Y").date().isoformat()
    home, away = e["home"], e["away"]
    is_home = home.get("fullName") == CLUB
    opp = away if is_home else home
    tour = (e.get("tournament") or {}).get("name", "")
    stage = (e.get("stage") or {}).get("name", "")
    comp = e.get("tournamentDescriptionLabel") or tour
    m = csv_lookup(d, [opp.get("fullName"), opp.get("shortName")])
    uid_comp, uid_opp = m if m else (comp, opp.get("fullName"))
    uid = hashlib.sha1(f"{d}|{uid_comp}|{uid_opp}".encode()).hexdigest()[:16] + "@" + CLUB.lower().replace(" ", "-") + "-fixtures"
    def side(t):
        goals, reds = [], []
        for a in t.get("actions", []) or []:
            for x in a.get("actions", []):
                typ = x.get("type", ""); mins = (x.get("timeLabel") or {}).get("value", "")
                if "goal" in typ.lower() or typ.lower() in ("penalty",):
                    note = "pen" if "pen" in typ.lower() else ("og" if "own" in typ.lower() else "")
                    goals.append({"player": a.get("playerName"), "minute": mins, "type": note})
                elif "red" in typ.lower() or "second yellow" in typ.lower():
                    reds.append({"player": a.get("playerName"), "minute": mins, "type": typ})
        rs = t.get("runningScores") or {}
        return {"team": t.get("fullName"), "score": t.get("score"), "ht": rs.get("halftime"), "goals": goals, "reds": reds,
                "et": rs.get("extratime"), "pens": rs.get("penaltyShootout"), "agg": rs.get("aggregate")}
    h, a = side(home), side(away)
    friendly = "friendl" in (tour + comp).lower()
    return uid, {"date": d, "competition": comp, "friendly": friendly, "home": h, "away": a, "venue": (e.get("venue") or {}).get("name"),
                 "home_away": "Home" if is_home else "Away", "status": pl, "kickoff_uk": (e.get("time") or {}).get("displayTimeUK"), "summary": e.get("accessibleEventSummary"),
                 "attendance": (e.get("attendance") or {}).get("value"), "source_url": url,
                 "fetched": datetime.datetime.now().astimezone().strftime("%d %b %Y %H:%M %Z")}

def store(pairs):
    p = D/"results.json"
    res = json.load(open(p)) if p.exists() else {}
    n = 0
    for uid, r in pairs:
        res[uid] = r; n += 1
    json.dump(dict(sorted(res.items(), key=lambda kv: kv[1]["date"], reverse=True)), open(p, "w"), indent=1, ensure_ascii=False)
    return n

def collect(urls, only_date=None):
    out, seen = [], set()
    for u in urls:
        for e in events(u):
            r = to_result(e, u)
            if not r or e.get("urn") in seen: continue
            if only_date and r[1]["date"] != only_date: continue
            seen.add(e.get("urn")); out.append(r)
    return out

def main():
    args = [a for a in sys.argv[1:] if a != "--publish"]
    if args[0] == "--backfill":
        start = datetime.date.fromisoformat(args[1] + "-01"); today = datetime.date.today(); urls = []
        y, m = start.year, start.month
        while (y, m) <= (today.year, today.month):
            urls += month_links(f"{y}-{m:02d}"); m += 1
            if m == 13: y, m = y + 1, 1
        pairs = collect(urls)
        have = {(r["date"]) for _, r in pairs}
        y, m = start.year, start.month
        while (y, m) <= (today.year, today.month):
            ym = f"{y}-{m:02d}"
            for s in month_summaries(ym):
                if s["date"] in have: continue
                is_home = s["home"] == CLUB; opp = s["away"] if is_home else s["home"]
                uid = hashlib.sha1(f"{s['date']}|{s['comp']}|{opp}".encode()).hexdigest()[:16] + "@" + CLUB.lower().replace(" ", "-") + "-fixtures"
                blank = lambda t, sc: {"team": t, "score": sc, "ht": None, "goals": [], "reds": [], "et": None, "pens": None, "agg": None}
                pairs.append((uid, {"date": s["date"], "competition": s["comp"], "friendly": "friendl" in s["comp"].lower(),
                    "home": blank(s["home"], s["hs"]), "away": blank(s["away"], s["as_"]), "venue": None,
                    "home_away": "Home" if is_home else "Away", "status": "FT", "summary": s["summary"], "attendance": None,
                    "source_url": f"{BBC}/sport/football/teams/{SLUG}/scores-fixtures/{ym}?filter=results", "score_only": True,
                    "fetched": datetime.datetime.now().astimezone().strftime("%d %b %Y %H:%M %Z")}))
            m += 1
            if m == 13: y, m = y + 1, 1
    else:
        d = datetime.date.fromisoformat(args[0])
        pairs = collect(month_links(f"{d:%Y-%m}"), only_date=d.isoformat())
    n = store(pairs)
    for uid, r in pairs: print(r["date"], r["summary"], "|", r["status"])
    print(f"{n} final result(s) stored")
    subprocess.run([sys.executable, str(D/"build.py")], check=True)
    if "--publish" in sys.argv:
        subprocess.run(["git", "-C", str(D), "add", "-A"], check=True)
        if subprocess.run(["git", "-C", str(D), "diff", "--cached", "--quiet"]).returncode:
            subprocess.run(["git", "-C", str(D), "commit", "-qm", f"Results update {' '.join(args)}"], check=True)
            subprocess.run(["git", "-C", str(D), "push", "-q"], check=True)

if __name__ == "__main__":
    main()
