#!/usr/bin/env python3
"""Fetch the confirmed starting XI for a fixture from BBC Sport and store it in lineups.json.

Usage:  python3 fetch_lineup.py YYYY-MM-DD [--publish]
        (picks the fixture on that date from the CSV in config.json)
Procedure:
  1. Open BBC Sport's monthly team fixtures page and find the match's link (/sport/football/live/<id>).
  2. Fetch that match page; BBC posts a "LINE-UPS" entry (~1 hour before kick-off) of the form
     "<Club>: A, B, C ... Substitutes: X, Y, Z." We parse the club's entry only.
  3. If nothing is found, the fixture stays/gets status "pending". Players are never invented.
  4. Rebuild (build.py); with --publish also git commit + push.
Fallbacks (manual): rangers.co.uk team news article / @RangersFC "TEAM NEWS" post.
BBC's line-up text carries names only (no shirt numbers/positions/formation).
"""
import csv, datetime, html, json, re, subprocess, sys, urllib.request
from pathlib import Path
D = Path(__file__).parent
CFG = json.load(open(D/"config.json"))
CLUB = CFG["club_name"]
TEAM_SLUG = CFG.get("bbc_team_slug", CLUB.lower().replace(" ", "-"))
UA = {"User-Agent": "Mozilla/5.0 (fixtures-bot)"}

def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read().decode("utf-8", "replace")

def text(h):
    h = re.sub(r"<script.*?</script>|<style.*?</style>", " ", h, flags=re.S)
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " \n ", h)))

def find_fixture(date):
    for r in csv.DictReader(open(CFG["csv"])):
        try: d = datetime.datetime.strptime(r["Date"], "%a %d %b %Y").date()
        except ValueError: continue
        if d.isoformat() == date: return r, d
    sys.exit(f"No fixture on {date} in CSV")

def bbc_match_url(d, opp):
    month = get(f"https://www.bbc.co.uk/sport/football/teams/{TEAM_SLUG}/scores-fixtures/{d:%Y-%m}")
    for seg in month.split('<li')[1:]:
        seg = seg[:6000]
        if opp.split()[0] in seg and CLUB in seg:
            m = re.search(r'href="(/sport/football/(?:live/)?[a-z0-9]+)"', seg)
            if m: return "https://www.bbc.co.uk" + m.group(1)
    return None

def parse(t):
    names = lambda s: [n.strip(" .") for n in s.split(",") if n.strip(" .")]
    m = re.search(rf"{re.escape(CLUB)}\s*:\s*([^:]{{20,400}}?)\.\s*Substitutes\s*:\s*([^:]{{3,400}}?)\.", t)
    if not m: return None
    xi = names(m.group(1))
    if len(xi) != 11: return None          # sanity check: refuse anything that isn't 11 players
    return {"starting_xi": [{"name": n} for n in xi], "subs": [{"name": n} for n in names(m.group(2))]}

def main():
    date = sys.argv[1]; publish = "--publish" in sys.argv
    r, d = find_fixture(date)
    sys.path.insert(0, str(D))
    comp, opp = r["Competition"], r["Opponent"]
    import hashlib
    uid = hashlib.sha1(f"{d.isoformat()}|{comp}|{opp}".encode()).hexdigest()[:16] + "@" + CLUB.lower().replace(" ","-") + "-fixtures"
    lu = json.load(open(D/"lineups.json")) if (D/"lineups.json").exists() else {}
    now = datetime.datetime.now().astimezone().strftime("%d %b %Y %H:%M %Z")
    url = bbc_match_url(d, opp)
    entry = None
    if url:
        raw = get(url)
        res = parse(html.unescape(raw)) or parse(text(raw))
        if res:
            entry = {"status": "confirmed", "formation": None, "absences": [], "source_name": "BBC Sport", "source_url": url, "updated": now, **res}
    if entry is None:
        old = lu.get(uid, {})
        if old.get("status") == "confirmed":
            print("Already confirmed; leaving as is."); return
        entry = {"status": "pending", "source_url": url, "updated": now}
    lu[uid] = {"fixture": f"{d:%a %d %b %Y} {r['Kick-off (Isle of Man time)']} {CLUB} {'v' if r['Home/Away']!='Away' else '@'} {opp}", **entry}
    json.dump(lu, open(D/"lineups.json", "w"), indent=1, ensure_ascii=False)
    print(json.dumps(lu[uid], indent=1, ensure_ascii=False))
    subprocess.run([sys.executable, str(D/"build.py")], check=True)
    if publish:
        subprocess.run(["git", "-C", str(D), "add", "-A"], check=True)
        if subprocess.run(["git", "-C", str(D), "diff", "--cached", "--quiet"]).returncode:
            subprocess.run(["git", "-C", str(D), "commit", "-qm", f"Team news {date}: {entry['status']}"], check=True)
            subprocess.run(["git", "-C", str(D), "push", "-q"], check=True)

if __name__ == "__main__":
    main()
