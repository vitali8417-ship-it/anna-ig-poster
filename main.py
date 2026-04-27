"""
main.py - direkt-importierbares Python-Interface

Falls Annas Hermes-Agent Python direkt ausfuehrt, kann er einfach:

    from main import post_feed, post_carousel, post_story, post_reel

    post_feed(image="content/post1.jpg",
              caption="Mein Tipp: ...",
              hashtags=["#marketing", "#personalbranding"])

Das ist die einfachste Schnittstelle - keine CLI, kein HTTP-Server.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

from instagram_publisher import InstagramPublisher

load_dotenv()
ROOT = Path(__file__).parent
CONFIG = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))

logging.basicConfig(level=CONFIG["logging"]["level"])
log = logging.getLogger("anna.posting")


def _publisher() -> InstagramPublisher:
    return InstagramPublisher(
        ig_business_account_id=os.environ["IG_BUSINESS_ACCOUNT_ID"],
        access_token=os.environ["IG_ACCESS_TOKEN"],
        imgur_client_id=os.getenv("IMGUR_CLIENT_ID") or None,
        dry_run=os.getenv("DRY_RUN", "true").lower() == "true",
    )


def _merge_hashtags(custom: list[str] | None) -> list[str]:
    blacklist = {h.lower() for h in CONFIG.get("hashtag_blacklist", [])}
    tags = list(custom) if custom else list(CONFIG.get("default_hashtags", []))
    seen, out = set(), []
    for t in tags:
        t = t if t.startswith("#") else f"#{t}"
        if t.lower() in blacklist or t.lower() in seen:
            continue
        seen.add(t.lower())
        out.append(t)
    return out


# ---- High-Level-API ------------------------------------------------------
def post_feed(image: str, caption: str = "", hashtags: list[str] | None = None) -> dict:
    return _publisher().post_feed_image(image, caption, _merge_hashtags(hashtags))


def post_carousel(images: list[str], caption: str = "", hashtags: list[str] | None = None) -> dict:
    return _publisher().post_carousel(images, caption, _merge_hashtags(hashtags))


def post_story(image: str) -> dict:
    return _publisher().post_story(image)


def post_reel(video: str, caption: str = "", hashtags: list[str] | None = None) -> dict:
    return _publisher().post_reel(video, caption, _merge_hashtags(hashtags))
