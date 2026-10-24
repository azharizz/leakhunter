"""Generate the README and submission assets: banner, film excerpts (GIF), blurred GitLab screenshots.

usage: python3 submission/assets/generate-readme-assets.py --film SHOWREEL.mp4 --captures DIR --fonts DIR

--captures holds the GitLab captures (2x PNG) and their boxes.json; credential-shaped lines listed under
each capture's "_blur" are blurred exactly as in the film. Needs Playwright (Chromium), Pillow and ffmpeg.
"""
import argparse
import json
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageFilter
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
SHOTS = HERE.parent / "screenshots"
# name, film start (s), duration (s): excerpts of the Unspool showreel (picture only)
GIFS = [("unspool-loop", 88.9, 7.2), ("gate-blocks-the-leak", 105.6, 9.2), ("duo-fixes-the-mr", 117.6, 8.2),
        ("verified-and-live", 135.6, 6.6), ("typed-decision-model", 62.6, 8.8), ("canary-proves-the-leak", 75.2, 8.6),
        ("thirty-six-fixes", 157.8, 9.6), ("what-actually-leaves", 2.0, 7.4)]
# GitLab captures from the hands-off run (MR !44) and film stills of the Unspool app
CAPTURES = ["m44_mr", "m44_leakpipe", "m44_leaklog", "m44_note", "m44_commits", "m44_fixdiff", "m44_fixlog",
            "m44_merged", "m44_deploylog"]
STILLS = [("app-graph", 46.0), ("app-probes", 85.6), ("app-decision", 61.5), ("app-fixed", 146.5)]


def banner(fonts):
    html = (HERE / "src" / "readme-art.html").read_text().replace("url(FONTS/", f"url({Path(fonts).resolve().as_uri()}/")
    with tempfile.TemporaryDirectory() as tmp, sync_playwright() as p:
        page_file = Path(tmp) / "banner.html"
        page_file.write_text(html)
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 480}, device_scale_factor=2)
        page.goto(page_file.as_uri())
        page.wait_for_timeout(500)
        page.screenshot(path=str(Path(tmp) / "banner.png"))
        browser.close()
        Image.open(Path(tmp) / "banner.png").resize((1600, 480), Image.LANCZOS).save(HERE / "unspool-readme-banner.png", optimize=True)


def gif(film, name, start, dur):
    # the film's grain changes every frame; denoise it so the GIF only stores real motion
    frames = "fps=10,scale=720:-1:flags=lanczos,hqdn3d=6:4:9:6"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(start), "-t", str(dur), "-i", str(film), "-an", "-vf",
                    f"{frames},split[a][b];[a]palettegen=max_colors=96:stats_mode=diff[p];[b][p]paletteuse=dither=none:diff_mode=rectangle",
                    str(HERE / f"{name}.gif")], check=True)


def capture(captures, boxes, name):
    image = Image.open(Path(captures) / f"{name}.png").convert("RGB")
    scale = image.width / 1920
    for b in boxes.get(name, {}).get("_blur", []):
        box = tuple(int(round(v * scale)) for v in (b["x"] - 4, b["y"] - 2, b["x"] + b["w"] + 4, b["y"] + b["h"] + 2))
        image.paste(image.crop(box).filter(ImageFilter.GaussianBlur(10 * scale)), box)
    image.resize((1600, 900), Image.LANCZOS).save(SHOTS / f"gitlab-{name.removeprefix('m44_')}.jpg", quality=86)


def still(film, name, at):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(at), "-i", str(film), "-frames:v", "1", "-vf", "scale=1600:-1",
                    "-q:v", "3", str(SHOTS / f"{name}.jpg")], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--film", required=True)
    parser.add_argument("--captures", required=True)
    parser.add_argument("--fonts", required=True)
    args = parser.parse_args()
    SHOTS.mkdir(exist_ok=True)
    banner(args.fonts)
    for item in GIFS:
        gif(args.film, *item)
    boxes = json.loads((Path(args.captures) / "boxes.json").read_text())
    for name in CAPTURES:
        capture(args.captures, boxes, name)
    for item in STILLS:
        still(args.film, *item)


if __name__ == "__main__":
    main()
