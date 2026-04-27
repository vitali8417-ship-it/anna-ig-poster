"""
HTTP-API fuer Annas Hermes-Agent
================================

Startet einen kleinen FastAPI-Server, ueber den Anna per HTTP posten kann.
So kann der Hermes-Agent posten, ohne Python-Code lokal auszufuehren.

Start:
    uvicorn api:app --host 127.0.0.1 --port 8765

Authentifizierung:
    Header  X-API-Key: <wert aus .env API_KEY>

Endpoints:
    POST /post/feed
        json: { "image_url" oder "image_b64", "caption", "hashtags": [...] }

    POST /post/carousel
        json: { "image_urls" oder "images_b64": [...], "caption", "hashtags": [...] }

    POST /post/story
        json: { "image_url" oder "image_b64" }

    POST /post/reel
        json: { "video_url", "caption", "hashtags": [...] }

    GET /health
"""
from __future__ import annotations

import base64
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from instagram_publisher import InstagramPublisher, PublishError

load_dotenv()

ROOT = Path(__file__).parent
CONFIG = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
logging.basicConfig(level=CONFIG["logging"]["level"])
log = logging.getLogger("api")

app = FastAPI(title="Annas Instagram Posting API", version="1.0.0")


# ---------------------------------------------------------------- auth
def _check_auth(x_api_key: Optional[str]) -> None:
    required = CONFIG.get("api", {}).get("api_key_required", True)
    if not required:
        return
    expected = os.getenv("API_KEY", "").strip()
    if not expected:
        raise HTTPException(500, "API_KEY in .env nicht gesetzt, aber api_key_required=true")
    if x_api_key != expected:
        raise HTTPException(401, "Ungueltiger oder fehlender X-API-Key")


def _publisher() -> InstagramPublisher:
    return InstagramPublisher(
        ig_business_account_id=os.environ["IG_BUSINESS_ACCOUNT_ID"],
        access_token=os.environ["IG_ACCESS_TOKEN"],
        imgur_client_id=os.getenv("IMGUR_CLIENT_ID") or None,
        dry_run=os.getenv("DRY_RUN", "true").lower() == "true",
    )


def _b64_to_tempfile(b64: str, suffix: str = ".jpg") -> str:
    raw = base64.b64decode(b64)
    f = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    f.write(raw)
    f.close()
    return f.name


# ---------------------------------------------------------------- models
class FeedPost(BaseModel):
    image_url: Optional[str] = Field(None, description="Oeffentlich erreichbare Bild-URL")
    image_b64: Optional[str] = Field(None, description="Bild base64-kodiert")
    caption: str = ""
    hashtags: list[str] = []


class CarouselPost(BaseModel):
    image_urls: Optional[list[str]] = None
    images_b64: Optional[list[str]] = None
    caption: str = ""
    hashtags: list[str] = []


class StoryPost(BaseModel):
    image_url: Optional[str] = None
    image_b64: Optional[str] = None


class ReelPost(BaseModel):
    video_url: str
    caption: str = ""
    hashtags: list[str] = []


# ---------------------------------------------------------------- endpoints
@app.get("/health")
def health():
    return {"status": "ok", "dry_run": os.getenv("DRY_RUN", "true")}


@app.post("/post/feed")
def post_feed(body: FeedPost, x_api_key: Optional[str] = Header(None)):
    _check_auth(x_api_key)
    if not body.image_url and not body.image_b64:
        raise HTTPException(400, "image_url oder image_b64 erforderlich")
    pub = _publisher()
    path = body.image_url if body.image_url and Path(body.image_url).exists() else None
    if body.image_b64:
        path = _b64_to_tempfile(body.image_b64)
    elif body.image_url and not path:
        # URL ist bereits oeffentlich -> wir umgehen Imgur und reichen sie direkt durch.
        # Dafuer rufen wir den internen Container-Endpoint an.
        try:
            cid = pub._create_image_container(body.image_url, pub._build_caption(body.caption, body.hashtags))
            return pub._publish(cid)
        except PublishError as e:
            raise HTTPException(502, str(e))
    try:
        return pub.post_feed_image(path, body.caption, body.hashtags)
    except PublishError as e:
        raise HTTPException(502, str(e))


@app.post("/post/carousel")
def post_carousel(body: CarouselPost, x_api_key: Optional[str] = Header(None)):
    _check_auth(x_api_key)
    paths: list[str] = []
    if body.images_b64:
        paths = [_b64_to_tempfile(b) for b in body.images_b64]
    elif body.image_urls:
        # Falls bereits oeffentliche URLs: direkt durchreichen
        pub = _publisher()
        try:
            child_ids = [pub._create_carousel_child(u) for u in body.image_urls]
            cid = pub._create_carousel_container(child_ids, pub._build_caption(body.caption, body.hashtags))
            return pub._publish(cid)
        except PublishError as e:
            raise HTTPException(502, str(e))
    else:
        raise HTTPException(400, "image_urls oder images_b64 erforderlich")

    try:
        return _publisher().post_carousel(paths, body.caption, body.hashtags)
    except PublishError as e:
        raise HTTPException(502, str(e))


@app.post("/post/story")
def post_story(body: StoryPost, x_api_key: Optional[str] = Header(None)):
    _check_auth(x_api_key)
    if not body.image_url and not body.image_b64:
        raise HTTPException(400, "image_url oder image_b64 erforderlich")
    pub = _publisher()
    if body.image_url:
        try:
            cid = pub._create_story_container(body.image_url)
            return pub._publish(cid)
        except PublishError as e:
            raise HTTPException(502, str(e))
    path = _b64_to_tempfile(body.image_b64)
    try:
        return pub.post_story(path)
    except PublishError as e:
        raise HTTPException(502, str(e))


@app.post("/post/reel")
def post_reel(body: ReelPost, x_api_key: Optional[str] = Header(None)):
    _check_auth(x_api_key)
    pub = _publisher()
    try:
        cid = pub._create_reel_container(body.video_url, pub._build_caption(body.caption, body.hashtags))
        pub._wait_for_finished(cid)
        return pub._publish(cid)
    except PublishError as e:
        raise HTTPException(502, str(e))
