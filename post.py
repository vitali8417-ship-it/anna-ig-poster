"""
post.py - CLI fuer Anna
=======================

Anna (oder ein Hermes-Agent) ruft dieses Skript mit fertigem Content auf.

Beispiele:
  # Feed-Bild
  python post.py feed --image content/post1.jpg --caption "Mein Tipp: ..." \
    --hashtags "#marketing #personalbranding"

  # Karussell
  python post.py carousel --images content/1.jpg content/2.jpg content/3.jpg \
    --caption "5 Marketing-Mythen entlarvt" --hashtags-from default

  # Story
  python post.py story --image content/story.jpg

  # Reel
  python post.py reel --video content/reel.mp4 --caption "Behind the Scenes"

  # Caption als Datei einlesen (bei langen Texten)
  python post.py feed --image content/post1.jpg --caption-file content/post1.txt
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

from instagram_publisher import InstagramPublisher, PublishError

# ---------------------------------------------------------------- setup
load_dotenv()
ROOT = Path(__file__).parent
CONFIG = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))

logs_dir = ROOT / "logs"
logs_dir.mkdir(exist_ok=True)
logging.basicConfig(
    level=CONFIG["logging"]["level"],
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(logs_dir / "posting.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("post")


# ---------------------------------------------------------------- helpers
def _read_caption(args) -> str:
    if args.caption_file:
        return Path(args.caption_file).read_text(encoding="utf-8").strip()
    return args.caption or ""


def _read_hashtags(args) -> list[str]:
    """Hashtag-Quellen, in Reihenfolge:
    --hashtags-from default       -> nur die default_hashtags aus config
    --hashtags-from file:<pfad>   -> aus Datei (eine pro Zeile, mit oder ohne #)
    --hashtags "#a #b #c"         -> direkt aus CLI
    (none)                        -> default_hashtags
    """
    blacklist = {h.lower() for h in CONFIG.get("hashtag_blacklist", [])}

    if args.hashtags_from == "default":
        tags = list(CONFIG.get("default_hashtags", []))
    elif args.hashtags_from and args.hashtags_from.startswith("file:"):
        path = Path(args.hashtags_from[5:])
        tags = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            tags.append(line if line.startswith("#") else f"#{line}")
    elif args.hashtags:
        tags = []
        for token in args.hashtags.replace(",", " ").split():
            token = token.strip()
            if not token:
                continue
            tags.append(token if token.startswith("#") else f"#{token}")
    else:
        tags = list(CONFIG.get("default_hashtags", []))

    # Blacklist filtern, Duplikate raus, Reihenfolge bewahren
    seen = set()
    result = []
    for t in tags:
        low = t.lower()
        if low in blacklist or low in seen:
            continue
        seen.add(low)
        result.append(t)
    return result


def _build_publisher() -> InstagramPublisher:
    token = os.getenv("IG_ACCESS_TOKEN", "").strip()
    ig_id = os.getenv("IG_BUSINESS_ACCOUNT_ID", "").strip()
    imgur = os.getenv("IMGUR_CLIENT_ID", "").strip() or None
    dry = os.getenv("DRY_RUN", "true").lower() == "true"

    if not token or not ig_id:
        log.error("IG_ACCESS_TOKEN und IG_BUSINESS_ACCOUNT_ID muessen in .env stehen.")
        sys.exit(2)

    return InstagramPublisher(
        ig_business_account_id=ig_id,
        access_token=token,
        imgur_client_id=imgur,
        dry_run=dry,
    )


# ---------------------------------------------------------------- main
def main():
    parser = argparse.ArgumentParser(description="Postet Inhalte auf Annas Instagram-Account")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # gemeinsame Caption/Hashtag-Flags
    def _add_text_flags(p):
        p.add_argument("--caption", help="Caption-Text direkt")
        p.add_argument("--caption-file", help="Pfad zu einer Textdatei mit der Caption")
        p.add_argument("--hashtags", help="Hashtags als String, z.B. '#a #b'")
        p.add_argument(
            "--hashtags-from",
            help="'default' fuer config-defaults, 'file:<pfad>' fuer Datei",
        )

    p_feed = sub.add_parser("feed", help="Einzelnes Bild im Feed posten")
    p_feed.add_argument("--image", required=True, help="Pfad zum Bild")
    _add_text_flags(p_feed)

    p_car = sub.add_parser("carousel", help="Karussell (2-10 Bilder) posten")
    p_car.add_argument("--images", nargs="+", required=True, help="Pfade zu 2-10 Bildern")
    _add_text_flags(p_car)

    p_reel = sub.add_parser("reel", help="Reel (Video) posten")
    p_reel.add_argument("--video", required=True, help="Pfad zum mp4")
    _add_text_flags(p_reel)

    p_story = sub.add_parser("story", help="Story posten")
    p_story.add_argument("--image", required=True, help="Pfad zum Story-Bild")
    _add_text_flags(p_story)

    args = parser.parse_args()
    pub = _build_publisher()
    caption = _read_caption(args)
    tags = _read_hashtags(args)

    try:
        if args.cmd == "feed":
            res = pub.post_feed_image(args.image, caption, tags)
        elif args.cmd == "carousel":
            res = pub.post_carousel(args.images, caption, tags)
        elif args.cmd == "reel":
            res = pub.post_reel(args.video, caption, tags)
        elif args.cmd == "story":
            res = pub.post_story(args.image, caption)
        else:
            parser.error(f"Unbekanntes Kommando: {args.cmd}")
            return
    except PublishError as e:
        log.error("Posting fehlgeschlagen: %s", e)
        sys.exit(1)

    log.info("OK: %s", res)
    print(res)


if __name__ == "__main__":
    main()
