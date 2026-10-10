#!/usr/bin/env python3
"""Fetch the league table from BBC Sport (config.json league_table_url) into table.json.
Usage: python3 fetch_table.py [--publish]. Parses the page's HTML <table>; nothing is invented —
if the table can't be parsed the existing table.json is left untouched."""
import datetime, html, json, re, subprocess, sys, urllib.request
from pathlib import Path
D = Path(__file__).parent
CFG = json.load(open(D/"config.json"))
URL = CFG["league_table_url"]
h = urllib.request.urlopen(urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0 (fixtures-bot)"}), timeout=30).read().decode("utf-8", "replace")
i = h.find("<table"); t = h[i:h.find("</table>", i)]
cell = lambda c: html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c))).strip()
rows = []
for r in re.findall(r"<tr.*?</tr>", t, re.S)[1:]:
    raw = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", r, re.S)
    c = [cell(x) for x in raw]
    if len(c) < 9: continue
    m = re.match(r"(\d+)\s+(.+)", c[0])
    if not m: continue
    nums = [int(x) for x in c[1:9]]
    form = re.findall(r">([WDL])<", raw[9]) if len(raw) > 9 else []
    rows.append(dict(pos=int(m.group(1)), team=m.group(2).strip(), p=nums[0], w=nums[1], d=nums[2], l=nums[3],
                     gf=nums[4], ga=nums[5], gd=nums[6], pts=nums[7], form=form))
if len(rows) < 4: sys.exit("Table not parsed; leaving table.json unchanged")
up = re.search(r'Updated\\?":\\?"([^"\\]+)', h)
json.dump({"league": CFG.get("league_name"), "source_url": URL, "bbc_updated": up.group(1) if up else None,
           "fetched": datetime.datetime.now().astimezone().strftime("%d %b %Y %H:%M %Z"), "rows": rows},
          open(D/"table.json", "w"), indent=1, ensure_ascii=False)
for r in rows[:4]: print(r["pos"], r["team"], r["p"], r["pts"])
subprocess.run([sys.executable, str(D/"build.py")], check=True)
if "--publish" in sys.argv:
    subprocess.run(["git", "-C", str(D), "add", "-A"], check=True)
    if subprocess.run(["git", "-C", str(D), "diff", "--cached", "--quiet"]).returncode:
        subprocess.run(["git", "-C", str(D), "commit", "-qm", "League table update"], check=True)
        subprocess.run(["git", "-C", str(D), "push", "-q"], check=True)
