"""Builds worker.js: embeds the page, styles and icons into one file you can paste into Cloudflare."""
import base64, io, json, pathlib
from PIL import Image, ImageDraw, ImageFont

root = pathlib.Path(__file__).parent
src = root / "src"

def icon(size):
    s = size * 4  # draw large, scale down for smooth edges
    im = Image.new("RGB", (s, s), "#17201E")
    d = ImageDraw.Draw(im)
    d.ellipse([s*0.56, s*0.20, s*0.78, s*0.42], fill="#4DB6A9")  # sun
    back = [(0, s*0.70), (s*0.22, s*0.58), (s*0.45, s*0.66), (s*0.70, s*0.52), (s, s*0.62), (s, s), (0, s)]
    front = [(0, s*0.80), (s*0.30, s*0.68), (s*0.58, s*0.80), (s*0.82, s*0.72), (s, s*0.78), (s, s), (0, s)]
    d.polygon(back, fill="#B86E00")
    d.polygon(front, fill="#EBA43A")
    im = im.resize((size, size), Image.LANCZOS)
    buf = io.BytesIO(); im.save(buf, "PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode()

page = (src / "page.html").read_text().replace("{{STYLE}}", (src / "styles.css").read_text())
def og():
    W, H, k = 1200, 630, 2
    im = Image.new("RGB", (W*k, H*k), "#17201E")
    d = ImageDraw.Draw(im)
    d.ellipse([W*k*0.74, H*k*0.16, W*k*0.86, H*k*0.16 + W*k*0.12], fill="#4DB6A9")
    s = lambda pts: [(x*W*k, y*H*k) for x, y in pts]
    d.polygon(s([(0,.82),(.18,.73),(.40,.79),(.62,.69),(.84,.75),(1,.71),(1,1),(0,1)]), fill="#B86E00")
    d.polygon(s([(0,.92),(.26,.83),(.52,.92),(.76,.86),(1,.90),(1,1),(0,1)]), fill="#EBA43A")
    big = ImageFont.truetype(str(src/"fonts/big-shoulders-display-latin-800-normal.woff"), 150*k)
    small = ImageFont.truetype(str(src/"fonts/public-sans-latin-600-normal.woff"), 30*k)
    d.text((72*k, 60*k), "NOMAD", font=big, fill="#EDF0EC")
    d.text((72*k, 200*k), "OUTDOORS", font=big, fill="#EDF0EC")
    d.text((76*k, 372*k), "DRIVES  ·  WADIS  ·  CAMPS & CAMPFIRES", font=small, fill="#9AA9A5")
    im = im.resize((W, H), Image.LANCZOS)
    buf = io.BytesIO(); im.save(buf, "PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode()

icons = {"i180": icon(180), "i192": icon(192), "i512": icon(512), "og": og()}
worker = (src / "worker-src.js").read_text().replace("__HTML__", json.dumps(page)).replace("__HOME__", json.dumps((src / "home.html").read_text())).replace("__ICONS__", json.dumps(icons))
(root / "dist").mkdir(exist_ok=True)
(root / "dist" / "_worker.js").write_text(worker)
(root / "icon-preview.png").write_bytes(base64.b64decode(icons["i512"]))
(root / "og-preview.png").write_bytes(base64.b64decode(icons["og"]))
print("worker.js", len(worker), "bytes")
