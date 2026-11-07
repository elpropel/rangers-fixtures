#!/usr/bin/env python3
"""Fetch the confirmed starting XI for a fixture from BBC Sport and store it in lineups.json.

Usage:  python3 fetch_lineup.py YYYY-MM-DD [--publish]
        (picks the fixture on that date from the CSV in config.json)
Procedure:
  1. Open BBC Sport's monthly team fixtures page and find the match's link (/sport/football/live/<id>).
  2. Fetch that match page; BBC posts line-ups (~1 hour before kick-off). Prefer the structured
     Match Lineups blocks; fall back to the older "<Club>: A, B, C ... Substitutes: X, Y, Z." text.
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
    for r in csv.DictReader(open(D/CFG["csv"])):
        try: d = datetime.datetime.strptime(r["Date"], "%a %d %b %Y").date()
        except ValueError: continue
        if d.isoformat() == date: return r, d
    sys.exit(f"No fixture on {date} in CSV")

def opp_tokens(opp):
    """BBC often writes 'St. Mirren' while the CSV has 'St Mirren'."""
    toks = []
    for t in re.split(r"\s+", opp.strip()):
        t = t.strip(".,")
        if t and t.lower() not in {"fc", "afc"}:
            toks.append(t)
    return toks

def bbc_match_url(d, opp):
    month = get(f"https://www.bbc.co.uk/sport/football/teams/{TEAM_SLUG}/scores-fixtures/{d:%Y-%m}")
    toks = opp_tokens(opp)
    distinctive = [t for t in toks if len(t) >= 3]
    candidates = []
    for seg in month.split("<li")[1:]:
        seg = seg[:8000]
        if CLUB not in seg:
            continue
        flat_seg = seg.replace(".", "")
        if distinctive and not any(t.replace(".", "") in flat_seg for t in distinctive):
            continue
        for m in re.finditer(r'href="(/sport/football/live/[a-z0-9]+)"', seg):
            candidates.append("https://www.bbc.co.uk" + m.group(1))
    if candidates:
        return candidates[0]
    flat = month.replace(".", "")
    for t in distinctive:
        key = t.replace(".", "")
        idx = flat.find(key)
        while idx != -1:
            chunk = month[max(0, idx - 1500): idx + 1500]
            m = re.search(r'href="(/sport/football/live/[a-z0-9]+)"', chunk)
            if m:
                return "https://www.bbc.co.uk" + m.group(1)
            idx = flat.find(key, idx + 1)
    return None

def parse_legacy(t):
    names = lambda s: [n.strip(" .") for n in s.split(",") if n.strip(" .")]
    m = re.search(rf"{re.escape(CLUB)}\s*:\s*([^:]{{20,400}}?)\.\s*Substitutes\s*:\s*([^:]{{3,400}}?)\.", t)
    if not m: return None
    xi = names(m.group(1))
    if len(xi) != 11: return None
    return {"starting_xi": [{"name": n} for n in xi], "subs": [{"name": n} for n in names(m.group(2))], "formation": None}

def pipe_text(raw):
    t = html.unescape(re.sub(r"<script.*?</script>|<style.*?</style>", " ", raw, flags=re.S))
    t2 = re.sub(r"<[^>]+>", "|", t)
    # Collapse pipes and whitespace so "team,| |Rangers" becomes "team,|Rangers"
    t2 = re.sub(r"(?:\s*\|\s*)+", "|", t2)
    return t2

def parse_structured(raw):
    """Parse BBC's Match Lineups blocks (home/away team, Club ... Number N, Name, Role)."""
    t2 = pipe_text(raw)
    m = re.search(
        rf"(?:away|home)\|team,\|{re.escape(CLUB)}\|Manager:.*?(?=(?:away|home)\|team,\|(?!{re.escape(CLUB)}\b)|\Z)",
        t2,
        re.S,
    )
    if not m:
        m = re.search(
            rf"team,\|{re.escape(CLUB)}\|Manager:.*?(?=(?:away|home)\|team,\|(?!{re.escape(CLUB)}\b)|\Z)",
            t2,
            re.S,
        )
    if not m:
        return None
    block = m.group(0)
    formation = None
    fm = re.search(r"Formation:\|([0-9]+(?:\s*-\s*[0-9]+)+)", block)
    if fm:
        formation = re.sub(r"\s+", "", fm.group(1))
    xi = []
    for mm in re.finditer(
        r"Number\|\d+\|\d+,\s*([^|]+?),\s*(Goalkeeper|Defender|Defensive Midfielder|Midfielder|Attacking Midfielder|Striker|Forward)\|([^|]+)",
        block,
    ):
        short = mm.group(3).strip()
        long = mm.group(1).strip()
        name = short if short and short not in {"(c)", "Captain"} else long
        if name and name not in {"(c)", "Captain"}:
            xi.append(name)
        if len(xi) == 11:
            break
    if len(xi) != 11:
        return None
    # Prefer names from the pitch diagram (first 11) over the duplicated "Starting lineup" list
    subs = []
    for mm in re.finditer(r"Number\|\d+\|\d+,\s*([^|]+?),\s*Substitute\|([^|]+)", block):
        short = mm.group(2).strip()
        long = mm.group(1).strip()
        name = short or long
        if name:
            subs.append(name)
    return {
        "starting_xi": [{"name": n} for n in xi],
        "subs": [{"name": n} for n in subs],
        "formation": formation,
    }

def parse(raw):
    res = parse_structured(raw)
    if res:
        return res
    return parse_legacy(html.unescape(raw)) or parse_legacy(text(raw))

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
        res = parse(raw)
        if res:
            formation = res.pop("formation", None)
            entry = {
                "status": "confirmed",
                "formation": formation,
                "absences": [],
                "source_name": "BBC Sport",
                "source_url": url,
                "updated": now,
                **res,
            }
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
