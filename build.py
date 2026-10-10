#!/usr/bin/env python3
"""Regenerate index.html and rangers.ics from the fixtures CSV."""
import csv, hashlib, html, json, datetime, sys
from pathlib import Path
CSV = Path(sys.argv[1] if len(sys.argv) > 1 else "/workspace/rangers_fixtures_2026-27.csv")
OUT = Path(__file__).parent
rows = list(csv.DictReader(open(CSV)))
KO = "Kick-off (Isle of Man time)"
fx = []
for r in rows:
    try: d = datetime.datetime.strptime(r["Date"], "%a %d %b %Y").date()
    except ValueError: d = None
    t = r[KO] if r[KO] and r[KO] != "TBC" else None
    fx.append(dict(date=d.isoformat() if d else None, dateLabel=r["Date"], time=t, comp=r["Competition"],
                   opp=r["Opponent"], ha=r["Home/Away"], venue=r["Venue"], tv=r["TV"], tvsrc=r.get("TV Source",""), src=r["Source URL"]))
today = datetime.date.today()
# ICS
def esc(s): return s.replace("\\","\\\\").replace(",","\\,").replace(";","\\;").replace("\n","\\n")
stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
L = ["BEGIN:VCALENDAR","VERSION:2.0","PRODID:-//Andy Mac//Rangers Fixtures//EN","CALSCALE:GREGORIAN","METHOD:PUBLISH",
     "X-WR-CALNAME:Rangers Fixtures","X-WR-TIMEZONE:Europe/London","REFRESH-INTERVAL;VALUE=DURATION:PT6H","X-PUBLISHED-TTL:PT6H",
     "BEGIN:VTIMEZONE","TZID:Europe/London",
     "BEGIN:DAYLIGHT","TZOFFSETFROM:+0000","TZOFFSETTO:+0100","TZNAME:BST","DTSTART:19700329T010000","RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU","END:DAYLIGHT",
     "BEGIN:STANDARD","TZOFFSETFROM:+0100","TZOFFSETTO:+0000","TZNAME:GMT","DTSTART:19701025T020000","RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU","END:STANDARD",
     "END:VTIMEZONE"]
for f in fx:
    if not f["date"]: continue
    title = (f"Rangers v {f['opp']}" if f["ha"] != "Away" else f"{f['opp']} v Rangers") + f" ({f['comp']})"
    uid = hashlib.sha1(f"{f['date']}|{f['comp']}|{f['opp']}".encode()).hexdigest()[:16] + "@rangers-fixtures"
    L += ["BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{stamp}", f"SUMMARY:{esc(title + ('' if f['time'] else ' - kick-off TBC'))}", f"LOCATION:{esc(f['venue'])}",
          f"DESCRIPTION:{esc('TV: '+f['tv']+(' (UK)' if f['tv']!='TV TBC' else '')+chr(10)+'Source: '+f['src'])}"]
    d = f["date"].replace("-","")
    if f["time"]:
        s = datetime.datetime.strptime(f["date"]+f["time"], "%Y-%m-%d%H:%M"); e = s + datetime.timedelta(hours=2)
        L += [f"DTSTART;TZID=Europe/London:{s:%Y%m%dT%H%M%S}", f"DTEND;TZID=Europe/London:{e:%Y%m%dT%H%M%S}"]
    else:
        n = (datetime.date.fromisoformat(f["date"]) + datetime.timedelta(days=1)).strftime("%Y%m%d")
        L += [f"DTSTART;VALUE=DATE:{d}", f"DTEND;VALUE=DATE:{n}"]
    L.append("END:VEVENT")
(OUT/"rangers.ics").write_text("\r\n".join(L)+"\r\n")
# HTML
page = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Rangers Fixtures 2026/27</title><style>
body{margin:0;font-family:system-ui,sans-serif;background:#f2f5fb;color:#0b1b3f}
header{background:#1b458f;color:#fff;padding:16px;text-align:center}h1{margin:0;font-size:1.4rem}
.wrap{max-width:720px;margin:auto;padding:12px}
.next{background:#0b2a66;color:#fff;border-radius:12px;padding:16px;margin-bottom:12px;border-left:6px solid #d0021b}
.cd{font-size:1.6rem;font-weight:700;margin-top:6px}
.bar{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px}select,a.btn2{padding:10px;border-radius:8px;border:1px solid #1b458f;color:#1b458f;background:#fff;text-decoration:none}.note{font-size:.8rem;color:#445;margin:-4px 0 12px}
a.btn{padding:10px;border-radius:8px;border:1px solid #1b458f;font-size:1rem}
a.btn2{padding:10px;border-radius:8px;border:1px solid #1b458f;color:#1b458f;background:#fff;text-decoration:none}.note{font-size:.8rem;color:#445;margin:-4px 0 12px}
a.btn{background:#1b458f;color:#fff;text-decoration:none}
.card{background:#fff;border-radius:10px;padding:12px;margin-bottom:8px;display:flex;justify-content:space-between;gap:8px;box-shadow:0 1px 3px #0002}
.b{display:inline-block;min-width:22px;text-align:center;border-radius:5px;padding:2px 6px;font-weight:700;color:#fff;font-size:.8rem}
.H{background:#1b458f}.A{background:#d0021b}.N{background:#666}.tbc{background:#fbe7a1;color:#5a4500;padding:2px 6px;border-radius:5px;font-size:.8rem}
small{color:#556}.tv{display:inline-block;margin-top:4px;background:#e3ebf9;color:#1b458f;border-radius:5px;padding:2px 6px;font-size:.8rem;font-weight:600}.tvt{background:#eee;color:#666;font-weight:400}
body::before{content:'';position:fixed;inset:0;background:url(crest.svg) center/min(80vw,80vh) no-repeat;opacity:.06;pointer-events:none;z-index:0}
.wrap,footer{position:relative;z-index:1}
.hc{height:44px;vertical-align:middle;margin-right:8px}footer{font-size:.85rem;color:#445;text-align:center;padding:16px}
</style></head><body><header><h1><img class="hc" src="crest.svg" alt="">Rangers FC Fixtures 2026/27</h1><div>All times UK (Europe/London) &ndash; same as Isle of Man</div></header>
<div class="wrap"><div id="next"></div><div class="bar"><select id="f"><option value="">All competitions</option></select>
<a class="btn" href="webcal://elpropel.github.io/rangers-fixtures/rangers.ics">📅 Subscribe (auto-updates)</a> <a class="btn2" href="https://calendar.google.com/calendar/render?cid=webcal%3A%2F%2Felpropel.github.io%2Frangers-fixtures%2Frangers.ics">Google Calendar</a></div><p class="note">Please subscribe rather than import or download the file, or your calendar won&rsquo;t pick up fixture changes.</p><div id="list"></div></div>
<footer>Source: BBC Sport (bbc.co.uk/sport). Last updated: __UPDATED__. Fixtures subject to change; TBC = not yet confirmed.</footer>
<script>const FX=__DATA__;
const tz='Europe/London';
function when(f){if(!f.date)return null;const [y,m,d]=f.date.split('-').map(Number);const [h,mi]=(f.time||'00:00').split(':').map(Number);
 // Europe/London offset: BST between last Sun Mar and last Sun Oct
 const g=Date.UTC(y,m-1,d,h,mi);const off=new Intl.DateTimeFormat('en-GB',{timeZone:tz,timeZoneName:'shortOffset'}).formatToParts(new Date(g)).find(p=>p.type=='timeZoneName').value;
 const o=off==='GMT'?0:parseInt(off.slice(3));return new Date(g-o*3600e3);}
const now=new Date();const up=FX.filter(f=>!f.date||when(f).getTime()+2*3600e3>now-(f.time?0:864e5));
const sel=document.getElementById('f');[...new Set(up.map(f=>f.comp))].forEach(c=>sel.add(new Option(c,c)));
const ha=f=>f.ha==='Home'?'H':f.ha==='Away'?'A':'N';
const title=f=>f.ha==='Away'?f.opp+' v Rangers':'Rangers v '+f.opp;
const ko=f=>f.time?f.time:'<span class="tbc">TBC</span>';
function render(){const c=sel.value;document.getElementById('list').innerHTML=up.filter(f=>!c||f.comp===c).map(f=>
 `<div class="card"><div><b>${title(f)}</b><br><small>${f.comp} · ${f.venue}</small><br><span class="tv ${f.tv==='TV TBC'?'tvt':''}">📺 ${f.tv}</span></div>
 <div style="text-align:right;white-space:nowrap"><span class="b ${ha(f)}">${ha(f)}</span><br>${f.dateLabel}<br>${ko(f)}</div></div>`).join('');}
sel.onchange=render;render();
const nx=up.find(f=>f.date);
function tick(){if(!nx)return;const ms=when(nx)-new Date();let s=Math.max(0,ms/1000|0);
 const t=nx.time?(ms<=0?'Under way / just played':`${s/86400|0}d ${(s%86400)/3600|0}h ${(s%3600)/60|0}m ${s%60}s`):'Kick-off TBC';
 document.getElementById('next').innerHTML=`<div class="next"><div>NEXT MATCH · ${nx.comp}</div><div style="font-size:1.2rem;font-weight:700">${title(nx)}</div>
 <div>${nx.dateLabel} · ${nx.time||'TBC'} UK · ${nx.venue} · 📺 ${nx.tv}</div><div class="cd">${t}</div></div>`;}
tick();setInterval(tick,1000);
</script></body></html>"""
page = page.replace("__DATA__", json.dumps(fx).replace("</", "<\\/")).replace("__UPDATED__", today.strftime("%d %b %Y"))
(OUT/"index.html").write_text(page)
print(f"{len(fx)} fixtures -> index.html, rangers.ics")
