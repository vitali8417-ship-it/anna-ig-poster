"""
Instagram Publisher (Graph API v19.0)
=====================================

Veroeffentlicht Posts ueber die offizielle Instagram Graph API.

Voraussetzungen (siehe README):
  - Instagram BUSINESS-Account, verknuepft mit einer Facebook-Seite
  - Meta Developer App mit "Instagram Graph API" Produkt
  - Long-Lived Page Access Token
  - IG_BUSINESS_ACCOUNT_ID

Workflow (lt. Meta-Doku):
  1. POST /{ig-user-id}/media         -> erzeugt Container, gibt creation_id zurueck
  2. (Reels/Video) GET /{creation_id} -> auf status_code=FINISHED warten
  3. POST /{ig-user-id}/media_publish -> veroeffentlicht den Container

Bilder muessen oeffentlich erreichbar sein. Wir laden sie zu Imgur (kostenlos)
hoch und nutzen die zurueckgegebene URL. Stories werden via "media_type=STORIES"
veroeffentlicht.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)

GRAPH_VERSION = "v19.0"
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"


class PublishError(RuntimeError):
    pass


class InstagramPublisher:
    def __init__(
        self,
        ig_business_account_id: str,
        access_token: str,
        imgur_client_id: Optional[str] = None,
        dry_run: bool = False,
    ):
        self.ig_id = ig_business_account_id
        self.token = access_token
        self.imgur_client_id = imgur_client_id
        self.dry_run = dry_run

    # ==================================================================
    # Public API - eine Methode pro Post-Typ
    # ==================================================================
    def post_feed_image(self, image_path: str, caption: str, hashtags: list[str]) -> dict:
        full_caption = self._build_caption(caption, hashtags)
        if self.dry_run:
            return self._dry("feed_image", image_path, full_caption)

        image_url = self._upload_to_imgur(image_path)
        creation_id = self._create_image_container(image_url, full_caption)
        return self._publish(creation_id)

    def post_carousel(self, image_paths: list[str], caption: str, hashtags: list[str]) -> dict:
        full_caption = self._build_caption(caption, hashtags)
        if self.dry_run:
            return self._dry("carousel", image_paths, full_caption)

        if not 2 <= len(image_paths) <= 10:
            raise PublishError("Karussell braucht 2-10 Bilder")

        # 1. fuer jedes Bild einen Child-Container erzeugen
        child_ids = []
        for p in image_paths:
            url = self._upload_to_imgur(p)
            cid = self._create_carousel_child(url)
            child_ids.append(cid)

        # 2. Carousel-Container erzeugen
        creation_id = self._create_carousel_container(child_ids, full_caption)
        return self._publish(creation_id)

    def post_reel(self, video_path: str, caption: str, hashtags: list[str], cover_path: Optional[str] = None) -> dict:
        full_caption = self._build_caption(caption, hashtags)
        if self.dry_run:
            return self._dry("reel", video_path, full_caption)

        # Reels brauchen oeffentliche Video-URL. Imgur unterstuetzt das nur eingeschraenkt;
        # in der Praxis wird hier oft Catbox/Cloudinary/S3 genutzt.
        video_url = self._upload_video(video_path)
        creation_id = self._create_reel_container(video_url, full_caption)
        self._wait_for_finished(creation_id)
        return self._publish(creation_id)

    def post_story(self, image_path: str, caption: str = "") -> dict:
        # Stories ignorieren Captions/Hashtags weitgehend.
        if self.dry_run:
            return self._dry("story", image_path, caption)

        image_url = self._upload_to_imgur(image_path)
        creation_id = self._create_story_container(image_url)
        return self._publish(creation_id)

    # ==================================================================
    # Helpers
    # ==================================================================
    def _build_caption(self, caption: str, hashtags: list[str]) -> str:
        tags = " ".join(hashtags)
        return f"{caption}\n\n.\n.\n.\n{tags}"

    def _dry(self, kind: str, asset, caption: str) -> dict:
        logger.info("[DRY-RUN] %s | asset=%s | caption=%s...", kind, asset, caption[:80])
        return {"dry_run": True, "type": kind, "asset": str(asset), "caption_preview": caption[:200]}

    # ----- Container-Erzeugung -----
    def _create_image_container(self, image_url: str, caption: str) -> str:
        return self._post(f"/{self.ig_id}/media", {
            "image_url": image_url,
            "caption": caption,
        })["id"]

    def _create_carousel_child(self, image_url: str) -> str:
        return self._post(f"/{self.ig_id}/media", {
            "image_url": image_url,
            "is_carousel_item": "true",
        })["id"]

    def _create_carousel_container(self, child_ids: list[str], caption: str) -> str:
        return self._post(f"/{self.ig_id}/media", {
            "media_type": "CAROUSEL",
            "children": ",".join(child_ids),
            "caption": caption,
        })["id"]

    def _create_reel_container(self, video_url: str, caption: str) -> str:
        return self._post(f"/{self.ig_id}/media", {
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "share_to_feed": "true",
        })["id"]

    def _create_story_container(self, image_url: str) -> str:
        return self._post(f"/{self.ig_id}/media", {
            "image_url": image_url,
            "media_type": "STORIES",
        })["id"]

    # ----- Publish -----
    def _publish(self, creation_id: str) -> dict:
        return self._post(f"/{self.ig_id}/media_publish", {
            "creation_id": creation_id,
        })

    def _wait_for_finished(self, creation_id: str, timeout_s: int = 300) -> None:
        """Reels brauchen ein paar Sekunden zum Verarbeiten."""
        start = time.time()
        while time.time() - start < timeout_s:
            status = self._get(f"/{creation_id}", {"fields": "status_code"})
            code = status.get("status_code")
            logger.info("Reel-Container-Status: %s", code)
            if code == "FINISHED":
                return
            if code == "ERROR":
                raise PublishError(f"Reel-Container fehlgeschlagen: {status}")
            time.sleep(5)
        raise PublishError("Reel-Container Timeout")

    # ----- Image Upload (Imgur) -----
    def _upload_to_imgur(self, image_path: str) -> str:
        if not self.imgur_client_id:
            raise PublishError(
                "IMGUR_CLIENT_ID fehlt. Bilder muessen oeffentlich erreichbar sein. "
                "Trage einen Imgur Client-ID in .env ein oder ersetze _upload_to_imgur "
                "durch eine eigene Hosting-Loesung (S3, Cloudinary, ...)."
            )
        with open(image_path, "rb") as f:
            r = requests.post(
                "https://api.imgur.com/3/image",
                headers={"Authorization": f"Client-ID {self.imgur_client_id}"},
                files={"image": f},
                timeout=60,
            )
        r.raise_for_status()
        link = r.json()["data"]["link"]
        logger.info("Imgur upload: %s", link)
        return link

    def _upload_video(self, video_path: str) -> str:
        # Platzhalter - Anna sollte hier ihren bevorzugten Video-Host eintragen.
        # Fuer Reels empfiehlt Meta einen direkten Resumable Upload Endpoint.
        raise PublishError(
            "Video-Upload ist nicht implementiert. Optionen: "
            "(a) Catbox/Cloudinary/S3 als oeffentlichen Host, "
            "(b) Metas Resumable Upload via /{ig-user-id}/media?upload_type=resumable. "
            f"Video lokal: {video_path}"
        )

    # ----- HTTP -----
    def _post(self, endpoint: str, params: dict) -> dict:
        params = {**params, "access_token": self.token}
        r = requests.post(f"{GRAPH_BASE}{endpoint}", data=params, timeout=60)
        return self._handle(r)

    def _get(self, endpoint: str, params: dict) -> dict:
        params = {**params, "access_token": self.token}
        r = requests.get(f"{GRAPH_BASE}{endpoint}", params=params, timeout=30)
        return self._handle(r)

    @staticmethod
    def _handle(r: requests.Response) -> dict:
        try:
            data = r.json()
        except ValueError:
            r.raise_for_status()
            raise PublishError(f"Unerwartete Antwort: {r.text[:200]}")
        if not r.ok or "error" in data:
            err = data.get("error", {})
            raise PublishError(
                f"Graph API Fehler {r.status_code}: "
                f"{err.get('message', r.text[:200])} (code={err.get('code')})"
            )
        return data
