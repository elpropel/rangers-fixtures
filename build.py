#!/usr/bin/env python3
"""Regenerate index.html and rangers.ics from the fixtures CSV."""
import csv, hashlib, html, json, re, datetime, sys
from pathlib import Path
OUT = Path(__file__).parent
CFG = json.load(open(OUT/"config.json"))
CSV = Path(sys.argv[1] if len(sys.argv) > 1 else CFG["csv"])
CLUB = CFG["club_name"]
WEBCAL = "webcal://" + CFG["site_url"].split("://",1)[1] + CFG["ics_name"]
from urllib.parse import quote
rows = list(csv.DictReader(open(CSV)))
KO = "Kick-off (Isle of Man time)"
fx = []
for r in rows:
    try: d = datetime.datetime.strptime(r["Date"], "%a %d %b %Y").date()
    except ValueError: d = None
    t = r[KO] if r[KO] and r[KO] != "TBC" else None
    fx.append(dict(date=d.isoformat() if d else None, dateLabel=r["Date"], time=t, comp=r["Competition"],
                   opp=r["Opponent"], ha=r["Home/Away"], venue=r["Venue"], tv=r["TV"], tvsrc=r.get("TV Source",""), stream=r.get("Club stream","Club stream TBC") or "Club stream TBC", streamsrc=r.get("Club stream source",""), src=r["Source URL"]))
BADGES = json.load(open(OUT/"badges.json")) if (OUT/"badges.json").exists() else {}
def badge_url(team):
    b = BADGES.get(team) or BADGES.get(team.replace("St ", "St. ")) or BADGES.get(team.replace("St. ", "St "))
    return b["file"] if b and (OUT/b["file"]).exists() else None
def badge(team):
    u = badge_url(team)
    if u: return f'<img class="bd" src="{html.escape(u)}" alt="" loading="lazy">'
    ini = "".join(w[0] for w in team.replace(".", "").split()[:2]).upper()
    return f'<span class="bd" aria-hidden="true">{html.escape(ini)}</span>'
VER = hashlib.sha1((datetime.datetime.now().isoformat()).encode()).hexdigest()[:8]
TABS = [("fixtures", "./", "📅", "Fixtures"), ("results", "results.html", "🏆", "Results"), ("news", "news.html", "📰", "News")]
def nav(active):
    return '<nav class="tabs">' + "".join(f'<a href="{h}"{" class=on aria-current=page" if k == active else ""}><span aria-hidden="true">{i}</span>{t}</a>' for k, h, i, t in TABS) + "</nav>"
HEADS = {"fixtures": ("Fixtures " + CFG["season"], "All kick-offs in UK time"), "results": ("Results " + CFG["season"], "League table · newest results first"), "news": ("News", "Latest headlines · times UK")}
def with_nav(doc, active):
    doc = re.sub(r'<nav class="tabs">.*?</nav>', "", doc, flags=re.S)
    doc = re.sub(r'<header>.*?</header>', "", doc, count=1, flags=re.S)
    t, s = HEADS[active]
    hdr = f'<header><h1><img class="hc" src="crest.svg" alt="">{html.escape(t)}</h1><div>{html.escape(s)}</div></header>'
    doc = doc.replace("<body>", "<body>" + nav(active) + hdr, 1)
    doc = doc.replace("<head>", '<head><meta http-equiv="Cache-Control" content="no-cache"><meta http-equiv="Pragma" content="no-cache">', 1)
    doc = re.sub(r'(src|href)="((?:\./|results\.html|news\.html|crest\.svg|badges/[^"?]+|[a-z0-9-]+\.png|manifest\.webmanifest))"', lambda m: f'{m.group(1)}="{m.group(2)}?v={VER}"', doc)
    doc = doc.replace("url(crest.svg)", f"url(crest.svg?v={VER})")
    return doc
def uid_for(f): return hashlib.sha1(f"{f['date']}|{f['comp']}|{f['opp']}".encode()).hexdigest()[:16] + "@" + CLUB.lower().replace(" ","-") + "-fixtures"
LU = json.load(open(OUT/"lineups.json")) if (OUT/"lineups.json").exists() else {}
for f in fx:
    if f["date"]:
        f["uid"] = uid_for(f); f["team"] = LU.get(f["uid"])
    f["oppBadge"] = badge_url(f["opp"]) if f["opp"] else None
def lineup_text(t):
    if not t or t.get("status") != "confirmed": return ""
    xi = ", ".join((f"{p['number']} " if p.get("number") else "") + p["name"] for p in t.get("starting_xi", []))
    subs = ", ".join((f"{p['number']} " if p.get("number") else "") + p["name"] for p in t.get("subs", []))
    return f"Line-up ({t.get('formation') or 'formation n/a'}): {xi}" + (f" | Subs: {subs}" if subs else "") + f" | Source: {t.get('source_url','')}"
today = datetime.date.today()
# ICS
def esc(s): return s.replace("\\","\\\\").replace(",","\\,").replace(";","\\;").replace("\n","\\n")
stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
L = ["BEGIN:VCALENDAR","VERSION:2.0","PRODID:-//Andy Mac//"+CFG["calendar_name"]+"//EN","CALSCALE:GREGORIAN","METHOD:PUBLISH",
     "X-WR-CALNAME:"+CFG["calendar_name"],"X-WR-TIMEZONE:Europe/London","REFRESH-INTERVAL;VALUE=DURATION:PT6H","X-PUBLISHED-TTL:PT6H",
     "BEGIN:VTIMEZONE","TZID:Europe/London",
     "BEGIN:DAYLIGHT","TZOFFSETFROM:+0000","TZOFFSETTO:+0100","TZNAME:BST","DTSTART:19700329T010000","RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU","END:DAYLIGHT",
     "BEGIN:STANDARD","TZOFFSETFROM:+0100","TZOFFSETTO:+0000","TZNAME:GMT","DTSTART:19701025T020000","RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU","END:STANDARD",
     "END:VTIMEZONE"]
for f in fx:
    if not f["date"]: continue
    title = (f"{CLUB} v {f['opp']}" if f["ha"] != "Away" else f"{f['opp']} v {CLUB}") + f" ({f['comp']})"
    uid = f["uid"]
    L += ["BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{stamp}", f"SUMMARY:{esc(title + ('' if f['time'] else ' - kick-off TBC'))}", f"LOCATION:{esc(f['venue'])}",
          f"DESCRIPTION:{esc('TV: '+f['tv']+(' (UK)' if f['tv']!='TV TBC' else '')+chr(10)+CFG['stream_name']+': '+f['stream']+chr(10)+'Watch: '+CFG['stream_url']+' | Subscribe: '+CFG['stream_subscribe_url']+chr(10)+'Source: '+f['src']+((chr(10)+lineup_text(f.get('team'))) if lineup_text(f.get('team')) else ''))}"]
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
<link rel="apple-touch-icon" href="apple-touch-icon.png"><link rel="icon" type="image/png" sizes="32x32" href="favicon-32.png"><link rel="icon" type="image/png" sizes="192x192" href="icon-192.png"><link rel="manifest" href="manifest.webmanifest"><meta name="apple-mobile-web-app-capable" content="yes"><meta name="mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-title" content="__APPT__"><meta name="theme-color" content="__THEME__">
<title>__FULL__ Fixtures __SEASON__</title><style>
html{scrollbar-gutter:stable}body{margin:0;font-family:system-ui,sans-serif;background:#f2f5fb;color:#0b1b3f}nav.tabs{position:sticky;top:0;z-index:10;display:grid;grid-template-columns:repeat(3,1fr);background:#0b2a66;padding-top:env(safe-area-inset-top);box-shadow:0 1px 4px #0004}nav.tabs a{display:flex;align-items:center;justify-content:center;gap:6px;height:48px;color:#cfe0ff;text-decoration:none;font-weight:600;font-size:.95rem;white-space:nowrap;overflow:hidden;border-bottom:3px solid transparent;box-sizing:border-box}nav.tabs a.on{color:#fff;border-bottom-color:#fff;background:#1b458f}
header{background:#1b458f;color:#fff;padding:0 12px;text-align:center;height:84px;box-sizing:border-box;display:flex;flex-direction:column;justify-content:center;overflow:hidden}header h1{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}header div{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:.85rem}h1{margin:0;font-size:1.4rem}
.wrap{max-width:720px;margin:auto;padding:12px}
.next{background:#0b2a66;color:#fff;border-radius:12px;padding:16px;margin-bottom:12px;border-left:6px solid #d0021b}
.cd{font-size:1.5rem;font-weight:700;margin:6px 0 2px}
.bar{display:flex;gap:8px;align-items:center;margin:0 0 12px;position:relative;z-index:5}
.bar select{flex:1;min-width:0;height:36px;padding:0 8px;border-radius:8px;border:1px solid #1b458f;color:#1b458f;background:#fff;font-size:.85rem}
details.menu{position:relative}details.menu summary{list-style:none;height:36px;display:flex;align-items:center;padding:0 12px;border-radius:8px;background:#1b458f;color:#fff;font-size:.85rem;font-weight:600;cursor:pointer;white-space:nowrap}details.menu summary::-webkit-details-marker{display:none}
.pop{position:absolute;right:0;top:42px;width:240px;background:#fff;border-radius:10px;box-shadow:0 4px 16px #0004;padding:8px;z-index:20}.pop a{display:block;padding:10px;border-radius:8px;color:#1b458f;text-decoration:none;font-weight:600;font-size:.9rem}.pop a:hover{background:#e3ebf9}.pop p{margin:6px 10px 2px;font-size:.75rem;color:#556}
.card{background:#fff;border-radius:10px;padding:12px;margin-bottom:8px;display:flex;justify-content:space-between;gap:8px;box-shadow:0 1px 3px #0002;font-size:.95rem}.card b.t{font-size:.95rem}.card small{font-size:.8rem}
.chips{display:flex;flex-wrap:wrap;gap:4px;margin-top:6px}
.b{display:inline-block;min-width:22px;text-align:center;border-radius:5px;padding:2px 6px;font-weight:700;color:#fff;font-size:.75rem;line-height:1.4}
.H{background:#1b458f}.A{background:#d0021b}.N{background:#666}.tbc{background:#fbe7a1;color:#5a4500;padding:2px 6px;border-radius:5px;font-size:.75rem}
small{color:#556}.nw{display:flex;gap:10px;text-decoration:none;color:inherit}.nw img{width:96px;height:64px;object-fit:cover;border-radius:6px;flex:none}.nw h3{margin:0 0 4px;font-size:.95rem;color:#0b2a66}img.bd,span.bd{width:22px;height:22px;object-fit:contain;vertical-align:middle;margin:0 4px}span.bd{display:inline-block;border-radius:50%;background:#c9d6ee;color:#1b458f;font-size:.6rem;line-height:22px;text-align:center;font-weight:700}.next span.bd{background:#fff}table.lt{width:100%;border-collapse:collapse;background:#fff;border-radius:10px;overflow:hidden;font-size:.85rem;box-shadow:0 1px 3px #0002}.lt th,.lt td{padding:5px 4px;text-align:center}.lt th{background:#1b458f;color:#fff}.lt td.tm{text-align:left}.lt tr.us td{background:#dbe6fb;font-weight:700}.lt tr:nth-child(even) td{border-top:1px solid #eef}.fm{display:inline-block;width:14px;height:14px;line-height:14px;border-radius:3px;color:#fff;font-size:.65rem;margin:0 1px}.fW{background:#1a8f3a}.fD{background:#888}.fL{background:#d0021b}@media(max-width:480px){.lt .hx{display:none}.lt{font-size:.8rem}}details.tn{margin-top:6px;font-size:.85rem}details.tn summary{cursor:pointer;font-weight:600;color:#1b458f}.next details.tn summary{color:#fff}.tnp{margin-top:6px;font-size:.85rem;font-style:italic}.tn ol{margin:4px 0;padding-left:20px}.tv,.rtv{display:inline-block;border-radius:5px;padding:2px 6px;font-size:.75rem;line-height:1.4;font-weight:600;text-decoration:none}.tv{background:#e3ebf9;color:#1b458f}.rtv{background:#1b458f;color:#fff}.next .tv{background:#fff;color:#0b2a66}.next .rtv{background:#d0021b;color:#fff}.cs{text-decoration:none;border:1px solid #1b458f}.tvt{background:#eee;color:#666;font-weight:400}
body::before{content:'';position:fixed;inset:0;background:url(crest.svg) center/min(80vw,80vh) no-repeat;opacity:.06;pointer-events:none;z-index:0}
.wrap,footer{position:relative;z-index:1}
.hc{height:40px;width:40px;vertical-align:middle;margin-right:8px}header h1{font-size:1.3rem;line-height:44px}header div{line-height:20px}footer{font-size:.85rem;color:#445;text-align:center;padding:16px}
</style></head><body><header><h1><img class="hc" src="crest.svg" alt="">Fixtures __SEASON__</h1><div>All kick-offs in UK time</div></header><nav class="tabs"><a href="./" class="on">Fixtures</a><a href="results.html">Results</a><a href="news.html">News</a></nav>
<div class="wrap"><div id="next"></div><div id="nexttn" class="next" style="margin-top:-8px;padding-top:4px;border-top-left-radius:0;border-top-right-radius:0"></div><div class="bar"><select id="f" aria-label="Competition"><option value="">All competitions</option></select>
<details class="menu"><summary>📅 Calendar</summary><div class="pop"><a href="__WEBCAL__">iPhone / Apple Calendar</a><a href="https://calendar.google.com/calendar/render?cid=__GCID__" target="_blank" rel="noopener">Google Calendar</a><p>Subscribe (don&rsquo;t import/download) so fixture changes update automatically.</p></div></details>
<details class="menu"><summary>▶ __SN2__</summary><div class="pop"><a href="__SU2__" target="_blank" rel="noopener">Watch on __SN2__</a><a href="__SUB__" target="_blank" rel="noopener">Subscribe to __SN2__</a></div></details></div><div id="list"></div></div>
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
const CLUB=__CLUB__,SN=__SN__,SU=__SU__;const title=f=>f.ha==='Away'?f.opp+' v '+CLUB:CLUB+' v '+f.opp;
const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const pl=p=>`${p.number?'<b>'+esc(p.number)+'</b> ':''}${esc(p.name)}${p.position?' <small>('+esc(p.position)+')</small>':''}`;
function tn(f,isNext){const t=f.team;
 if(t&&t.status==='confirmed'){return `<details class="tn"${isNext?' open':''}><summary>Team news: ${CLUB} XI confirmed${t.formation?' ('+esc(t.formation)+')':''}</summary><ol>${(t.starting_xi||[]).map(p=>'<li>'+pl(p)+'</li>').join('')}</ol>${(t.subs||[]).length?'<div><b>Subs:</b> '+t.subs.map(pl).join(', ')+'</div>':''}${(t.absences||[]).length?'<div><b>Absent:</b> '+t.absences.map(esc).join(', ')+'</div>':''}<small>Source: <a href="${esc(t.source_url)}">${esc(t.source_name||t.source_url)}</a>${t.updated?' · updated '+esc(t.updated):''}</small></details>`;}
 if(isNext)return '<div class="tnp">Team news: expected ~1 hour before kick-off</div>';return '';}
const CB=__CBADGE__;const bdg=(u,n)=>u?`<img class="bd" src="${esc(u)}?v=__VER__" alt="" loading="lazy">`:`<span class="bd">${esc(String(n||'?').replace(/[.]/g,'').split(' ').slice(0,2).map(w=>w[0]||'').join('').toUpperCase())}</span>`;
const vs=f=>{const us=bdg(CB,CLUB),th=bdg(f.oppBadge,f.opp);return f.ha==='Away'?th+esc(f.opp)+' v '+us+CLUB:us+CLUB+' v '+th+esc(f.opp);};
const ko=f=>f.time?f.time:'<span class="tbc">TBC</span>';
function render(){const c=sel.value;document.getElementById('list').innerHTML=up.filter(f=>!c||f.comp===c).map(f=>
 `<div class="card"><div><b class="t">${vs(f)}</b><br><small>${esc(f.comp)} · ${esc(f.venue)}</small><div class="chips"><span class="tv ${f.tv==='TV TBC'?'tvt':''}">📺 ${esc(f.tv)}</span><a class="rtv" href="${SU}" target="_blank" rel="noopener">▶ ${SN}: ${esc(f.stream)}</a></div>${tn(f,nx&&f.uid===nx.uid)}</div>
 <div style="text-align:right;white-space:nowrap"><span class="b ${ha(f)}">${ha(f)}</span><br>${f.dateLabel}<br>${ko(f)}</div></div>`).join('');}
const nx=up.find(f=>f.date);
sel.onchange=render;render();
function tick(){if(!nx)return;const ms=when(nx)-new Date();let s=Math.max(0,ms/1000|0);
 const t=nx.time?(ms<=0?'Under way / just played':`${s/86400|0}d ${(s%86400)/3600|0}h ${(s%3600)/60|0}m ${s%60}s`):'Kick-off TBC';
 document.getElementById('next').innerHTML=`<div class="next"><div style="font-size:.75rem;letter-spacing:.05em;opacity:.85">NEXT MATCH · ${esc(nx.comp).toUpperCase()}</div><div style="font-size:1.1rem;font-weight:700;margin:4px 0">${vs(nx)}</div>
 <div style="font-size:.85rem">${nx.dateLabel} · ${nx.time||'TBC'} UK · ${esc(nx.venue)}</div><div class="cd">${t}</div><div class="chips"><span class="tv">📺 ${esc(nx.tv)}</span><span class="rtv">▶ ${SN}: ${esc(nx.stream)}</span></div></div>`;}
document.querySelectorAll('details.menu').forEach(d=>d.addEventListener('toggle',()=>{if(d.open)document.querySelectorAll('details.menu').forEach(o=>{if(o!==d)o.open=false})}));document.addEventListener('click',ev=>{if(!ev.target.closest('details.menu'))document.querySelectorAll('details.menu').forEach(o=>o.open=false)});
tick();setInterval(tick,1000);if(nx)document.getElementById('nexttn').innerHTML=tn(nx,true);else document.getElementById('nexttn').remove();
</script></body></html>"""
page = page.replace("__DATA__", json.dumps(fx).replace("</", "<\\/")).replace("__UPDATED__", today.strftime("%d %b %Y")).replace("__FULL__", html.escape(CFG["club_full_name"])).replace("__SEASON__", CFG["season"]).replace("__WEBCAL__", WEBCAL).replace("__GCID__", quote(WEBCAL, safe="")).replace("__CLUB__", json.dumps(CLUB)).replace("__VER__", VER).replace("__CBADGE__", json.dumps(badge_url(CLUB))).replace("__APPT__", html.escape(CFG["app_title"])).replace("__THEME__", CFG["theme_color"]).replace("__SU2__", CFG["stream_url"]).replace("__SUB__", CFG["stream_subscribe_url"]).replace("__SN2__", html.escape(CFG["stream_name"])).replace("__SN__", json.dumps(CFG["stream_name"])).replace("__SU__", json.dumps(CFG["stream_url"]))
(OUT/"index.html").write_text(with_nav(page, "fixtures"))
# ---------- Results page ----------
RES = json.load(open(OUT/"results.json")) if (OUT/"results.json").exists() else {}
def e(s): return html.escape(str(s)) if s is not None else ""
def goals_html(side):
    return ", ".join(f"{e(g['player'])} {e(g['minute'])}{' (pen)' if g.get('type')=='pen' else ' (og)' if g.get('type')=='og' else ''}" for g in side["goals"])
def card(uid, r):
    h, a = r["home"], r["away"]
    us = h if r["home_away"] == "Home" else a; them = a if us is h else h
    try: w, l = int(us["score"]), int(them["score"])
    except (TypeError, ValueError): w = l = 0
    pw = None
    if us.get("pens") and them.get("pens"): pw = int(us["pens"]) > int(them["pens"])
    res = "W" if w > l or (w == l and pw) else "L" if w < l or (w == l and pw is False) else "D"
    extra = []
    if h.get("ht") is not None: extra.append(f"HT {e(h['ht'])}-{e(a['ht'])}")
    if r.get("status") in ("AET", "PENS") or (h.get("et") and r.get("status") != "FT"): extra.append("AET")
    if h.get("pens"): extra.append(f"Pens {e(h['pens'])}-{e(a['pens'])}")
    if h.get("agg") and uid in LAST_LEG: extra.append(f"Agg {e(h['agg'])}-{e(a['agg'])}")
    reds = [f"🟥 {e(x['player'])} {e(x['minute'])} ({e(t['team'])})" for t in (h, a) for x in t["reds"]]
    d = datetime.date.fromisoformat(r["date"]).strftime("%a %d %b %Y")
    lines = []
    if h["goals"]: lines.append(f"<div><small>⚽ {e(h['team'])}: {goals_html(h)}</small></div>")
    if a["goals"]: lines.append(f"<div><small>⚽ {e(a['team'])}: {goals_html(a)}</small></div>")
    if reds: lines.append("<div><small>" + "; ".join(reds) + "</small></div>")
    meta = [x for x in [e(r.get("venue")), f"Att {r['attendance']:,}" if r.get("attendance") else ""] if x]
    if r.get("score_only"): meta.append("score only (no BBC match page)")
    return (f'<div class="card"><div style="flex:1"><small>{e(r["competition"])} · {d}</small><br>'
            f'<b class="t">{badge(h["team"])}{e(h["team"])} {e(h["score"])} – {e(a["score"])} {e(a["team"])}{badge(a["team"])}</b>'
            f'<br><small>{" · ".join(extra)}</small>{"".join(lines)}<small>{" · ".join(meta)} · <a href="{e(r["source_url"])}">BBC Sport</a></small></div>'
            f'<div><span class="b {"H" if res=="W" else "A" if res=="L" else "N"}">{res}</span></div></div>')
LAST_LEG = set()
_seen = set()
for _u, _r in sorted(RES.items(), key=lambda kv: kv[1]["date"], reverse=True):
    if _r["home"].get("agg") is None: continue
    key = (_r["competition"].split(" - ")[0], frozenset((_r["home"]["team"], _r["away"]["team"])))
    if key not in _seen: _seen.add(key); LAST_LEG.add(_u)
TB = json.load(open(OUT/"table.json")) if (OUT/"table.json").exists() else None
def table_html():
    if not TB: return ""
    hd = '<tr><th>Pos</th><th style="text-align:left">Team</th><th>P</th><th class="hx">W</th><th class="hx">D</th><th class="hx">L</th><th class="hx">GF</th><th class="hx">GA</th><th>GD</th><th>Pts</th><th class="hx">Form</th></tr>'
    body = "".join(f'<tr class="{"us" if r["team"]==CLUB else ""}"><td>{r["pos"]}</td><td class="tm">{badge(r["team"])}{e(r["team"])}</td><td>{r["p"]}</td>'
        + "".join(f'<td class="hx">{r[k]}</td>' for k in ("w","d","l","gf","ga")) + f'<td>{r["gd"]:+d}</td><td><b>{r["pts"]}</b></td><td class="hx">'
        + "".join(f'<span class="fm f{x}">{x}</span>' for x in r.get("form", [])) + "</td></tr>" for r in TB["rows"])
    return (f'<h2 style="margin:4px 0 8px;color:#1b458f">{e(TB.get("league") or "League table")}</h2><table class="lt">{hd}{body}</table>'
            f'<p><small>Updated: {e(TB.get("bbc_updated") or TB.get("fetched"))} (BBC) · fetched {e(TB.get("fetched"))} · Source: <a href="{e(TB["source_url"])}">BBC Sport</a>. Form: last 6, oldest first.</small></p><h2 style="margin:12px 0 8px;color:#1b458f">Results</h2>')
items = sorted(RES.items(), key=lambda kv: kv[1]["date"], reverse=True)
comp_list = "".join(card(u, r) for u, r in items if not r.get("friendly"))
fr_list = "".join(card(u, r) for u, r in items if r.get("friendly"))
head = page.split("</style>")[0] + "</style></head>"
rpage = (head.replace("<title>", "<title>Results – ", 1) + '<body><header><h1><img class="hc" src="crest.svg" alt="">' + " Results " + e(CFG["season"]) +
    '</h1><div>Newest first · all competitions</div></header><nav class="tabs"><a href="./">Fixtures</a><a href="results.html" class="on">Results</a><a href="news.html">News</a></nav><div class="wrap">' + table_html() +
    (comp_list or "<p>No results yet.</p>") +
    (f'<details style="margin-top:12px"><summary><b>Pre-season friendlies ({sum(1 for _, r in items if r.get("friendly"))})</b></summary>{fr_list}</details>' if fr_list else "") +
    f'</div><footer>Source: BBC Sport match pages. Last updated: {today.strftime("%d %b %Y")}. Scorers/minutes as listed by BBC; blank where BBC has no data.</footer></body></html>')
(OUT/"results.html").write_text(with_nav(rpage, "results"))
# ---------- News page ----------
NW = json.load(open(OUT/"news.json")) if (OUT/"news.json").exists() else {"items": []}
def news_card(n):
    img = f'<img src="{e(n["thumb"])}" alt="" loading="lazy" referrerpolicy="no-referrer">' if n.get("thumb") else ""
    return (f'<div class="card"><a class="nw" href="{e(n["link"])}" target="_blank" rel="noopener">{img}<div><h3>{e(n["title"])}</h3>'
            f'<small>{e(n.get("excerpt",""))}</small><br><small>{e(n.get("published_uk",""))}{" · " + e(n["author"]) if n.get("author") else ""}</small></div></a></div>')
npage = (head.replace("<title>", "<title>News – ", 1) + '<body><header><h1><img class="hc" src="crest.svg" alt="">' + ' News</h1><div>Latest headlines · times UK</div></header>'
    '<nav class="tabs"><a href="./">Fixtures</a><a href="results.html">Results</a><a href="news.html" class="on">News</a></nav><div class="wrap">' +
    ("".join(news_card(n) for n in NW["items"]) or "<p>No news yet.</p>") +
    f'</div><footer>Source: <a href="{e(CFG["news_site_url"])}" target="_blank" rel="noopener">{e(CFG["news_source_name"])}</a> (RSS feed). Headlines and excerpts are theirs; tap a story to read it on their site. Fetched: {e(NW.get("fetched",""))}.</footer></body></html>')
(OUT/"news.html").write_text(with_nav(npage, "news"))
(OUT/"manifest.webmanifest").write_text(json.dumps({"name": CFG["app_title"], "short_name": CFG["short_name"], "start_url": "./", "scope": "./", "display": "standalone", "background_color": CFG["icon_background"], "theme_color": CFG["theme_color"], "icons": [{"src": "icon-192.png", "sizes": "192x192", "type": "image/png"}, {"src": "icon-512.png", "sizes": "512x512", "type": "image/png"}, {"src": "apple-touch-icon.png", "sizes": "180x180", "type": "image/png"}]}, indent=1))
try:
    import subprocess; subprocess.run([sys.executable, str(OUT/"make_icons.py")], check=True)
except Exception as e: print("icon render skipped:", e)
print(f"{len(fx)} fixtures -> index.html, rangers.ics")
