#!/usr/bin/env python3
"""Download club crests from English Wikipedia infoboxes into badges/ and map them in badges.json.
Edit ARTICLES (team name as BBC/CSV writes it -> Wikipedia article) in config.json 'badge_articles'."""
import json,urllib.request,urllib.parse,re,sys
from pathlib import Path
D=Path(__file__).parent
CFG=json.load(open(D/"config.json"))
UA={"User-Agent":"GrokBot-fixtures/1.0 (elpropel github pages)"}
def api(q): return json.load(urllib.request.urlopen(urllib.request.Request("https://en.wikipedia.org/w/api.php?"+urllib.parse.urlencode(q),headers=UA),timeout=30))
out=json.load(open(D/"badges.json")) if (D/"badges.json").exists() else {}
(D/"badges").mkdir(exist_ok=True)
for team,a in CFG["badge_articles"].items():
  if team in out and (D/out[team]["file"]).exists(): continue
  try:
    w=api(dict(action="parse",page=a,prop="wikitext",section=0,redirects=1,format="json"))["parse"]["wikitext"]["*"]
    m=re.search(r"\|\s*(?:image|logo|crest)\s*=\s*(?:\[\[)?(?:File:|Image:)?([^|\]\n{}]+\.(?:svg|png|jpg|gif))",w,re.I)
    if not m: print(team,"- no infobox crest (fallback)");continue
    fn=m.group(1).strip()
    ii=list(api(dict(action="query",titles="File:"+fn,prop="imageinfo",iiprop="url",iiurlwidth=96,format="json"))["query"]["pages"].values())[0]["imageinfo"][0]
    src=ii["url"].split("?")[0]; ext=src.rsplit(".",1)[1].lower()
    dl=src if ext=="svg" else ii["thumburl"].split("?")[0]; ext="svg" if ext=="svg" else dl.rsplit(".",1)[1].lower()
    slug=re.sub(r"[^a-z0-9]+","-",team.lower()).strip("-")
    (D/"badges"/f"{slug}.{ext}").write_bytes(urllib.request.urlopen(urllib.request.Request(dl,headers=UA),timeout=30).read())
    out[team]={"file":f"badges/{slug}.{ext}","source":ii["descriptionurl"].split("?")[0]}
    print(team,"->",fn)
  except Exception as e: print(team,"- ERROR",e,"(fallback)")
json.dump(out,open(D/"badges.json","w"),indent=1,ensure_ascii=False)
