"""
Content Generator
=================
Erzeugt mit OpenAI:
  - Bild (DALL-E 3) - Pfad zur lokal gespeicherten Datei
  - Caption + Hashtags (GPT-4o)

Wird vom scheduler/main aufgerufen. Liefert ein dict zurueck:
  {
    "image_path": "generated/2026-04-27_18-00.png",
    "caption":    "...",
    "hashtags":   ["#...", ...],
    "theme":      "Cozy Home Vibes"
  }
"""
from __future__ import annotations

import json
import logging
import os
import random
from datetime import datetime
from pathlib import Path

import requests
from openai import OpenAI

logger = logging.getLogger(__name__)


class ContentGenerator:
    def __init__(self, config: dict, openai_api_key: str):
        self.config = config
        self.client = OpenAI(api_key=openai_api_key)
        self.output_dir = Path("generated")
        self.output_dir.mkdir(exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def generate(self, post_type: str = "feed_image") -> dict:
        """Erzeugt einen kompletten Post (Bild + Caption + Hashtags).

        post_type: feed_image | carousel | reel | story
        """
        theme = random.choice(self.config["content_themes"])
        logger.info("Generiere Post (type=%s, theme=%s)", post_type, theme)

        # 1. Caption + Bild-Prompt mit GPT-4o erzeugen
        caption_data = self._generate_caption(theme, post_type)

        # 2. Bild mit DALL-E 3 generieren
        image_path = self._generate_image(caption_data["image_prompt"], post_type)

        return {
            "image_path": str(image_path),
            "caption": caption_data["caption"],
            "hashtags": caption_data["hashtags"],
            "image_prompt": caption_data["image_prompt"],
            "theme": theme,
            "post_type": post_type,
        }

    # ------------------------------------------------------------------
    # Caption + Bild-Prompt
    # ------------------------------------------------------------------
    def _generate_caption(self, theme: str, post_type: str) -> dict:
        acc = self.config["account"]
        cap_cfg = self.config["caption_generation"]

        always_tags = self.config["hashtags"]["always_include"]
        blacklist = self.config["hashtags"]["blacklist"]

        system_prompt = (
            "Du bist Social-Media-Manager fuer einen Instagram-Account "
            f"in der Nische '{acc['niche']}'. "
            f"Zielgruppe: {acc['target_audience']}. "
            f"Tonalitaet: {acc['tone']}. "
            f"Sprache der Captions: {acc['language']}. "
            "Antworte AUSSCHLIESSLICH in gueltigem JSON, ohne Markdown-Codeblock."
        )

        user_prompt = f"""
Erzeuge fuer einen Instagram-{post_type}-Post zum Thema "{theme}" folgendes JSON:

{{
  "caption": "Caption-Text (max {cap_cfg['max_length']} Zeichen, mit Zeilenumbruechen, ohne Hashtags am Ende){' mit passenden Emojis' if cap_cfg['include_emoji'] else ''}{', endend mit einem subtilen Call-to-Action (z.B. Frage an die Community oder Save-Hint)' if cap_cfg['call_to_action'] else ''}.",
  "hashtags": ["#tag1", "#tag2", ...]  // genau {cap_cfg['hashtag_count']} Hashtags, Mix aus reichweitenstark und nischig, ohne diese: {blacklist},
  "image_prompt": "Detaillierter englischer Prompt fuer DALL-E 3, der ein {post_type}-Bild zum Thema beschreibt. Stil: {', '.join(self.config['image_generation']['style_keywords'])}. KEINE Personen mit erkennbaren Gesichtern. KEIN Text im Bild."
}}

Diese Hashtags MUESSEN enthalten sein: {always_tags}
""".strip()

        resp = self.client.chat.completions.create(
            model=cap_cfg["model"],
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.9,
        )
        raw = resp.choices[0].message.content
        data = json.loads(raw)

        # Sicherheits-Filter: blacklist entfernen
        data["hashtags"] = [
            h for h in data["hashtags"] if h.lower() not in [b.lower() for b in blacklist]
        ]
        # always_include sicher reinmischen
        for tag in always_tags:
            if tag.lower() not in [h.lower() for h in data["hashtags"]]:
                data["hashtags"].append(tag)

        return data

    # ------------------------------------------------------------------
    # Bild
    # ------------------------------------------------------------------
    def _generate_image(self, image_prompt: str, post_type: str) -> Path:
        img_cfg = self.config["image_generation"]

        # Bildgroesse je nach Post-Typ
        if post_type in ("story", "reel"):
            size = "1024x1792"  # 9:16 portrait
        else:
            size = img_cfg["size"]

        logger.info("DALL-E Prompt: %s", image_prompt[:120] + "...")

        resp = self.client.images.generate(
            model=img_cfg["model"],
            prompt=image_prompt,
            size=size,
            quality=img_cfg["quality"],
            style=img_cfg["style"],
            n=1,
        )
        url = resp.data[0].url

        # Bild herunterladen und speichern
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"{timestamp}_{post_type}.png"
        out_path = self.output_dir / filename

        img_data = requests.get(url, timeout=60).content
        out_path.write_bytes(img_data)
        logger.info("Bild gespeichert: %s", out_path)

        return out_path
