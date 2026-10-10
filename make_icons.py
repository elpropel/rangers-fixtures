#!/usr/bin/env python3
"""Render crest.svg into opaque home-screen/favicon PNGs (white background, ~10% padding)."""
import io, json, cairosvg
from pathlib import Path
from PIL import Image
D = Path(__file__).parent
cfg = json.load(open(D/"config.json"))
bg = cfg.get("icon_background", "#ffffff")
for name, size in [("apple-touch-icon.png",180),("icon-192.png",192),("icon-512.png",512),("favicon-32.png",32)]:
    pad = 0.10 if size > 32 else 0.04
    inner = round(size*(1-2*pad))
    crest = Image.open(io.BytesIO(cairosvg.svg2png(url=str(D/"crest.svg"), output_width=inner, output_height=inner))).convert("RGBA")
    im = Image.new("RGBA", (size,size), bg); im.alpha_composite(crest, ((size-inner)//2,)*2)
    im.convert("RGB").save(D/name)
print("icons done")
