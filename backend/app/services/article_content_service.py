from __future__ import annotations

import json
import logging
import os
import re
import uuid
from pathlib import Path
from typing import Any

import httpx

from app.config import settings
from app.schemas.content import (
    ArticleContentResponse,
    ImageGenerateResponse,
    ImagePrompt,
    TtsVoice,
    VoiceoverResponse,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _compact(value: str | None) -> str:
    return " ".join((value or "").split()).strip()


def _extract_article_text(article: dict[str, Any]) -> str:
    """En zengin metin kaynağını döner: content_text > content_snippet > summary > title."""
    for field in ("content_text", "content_snippet", "summary", "title"):
        text = _compact(str(article.get(field) or ""))
        if text and len(text) > 60:
            return text[:settings.ANALYSIS_TEXT_CHAR_LIMIT]
    return _compact(str(article.get("title") or ""))


# ---------------------------------------------------------------------------
# LLM Prompt
# ---------------------------------------------------------------------------

_SCHEMA = {
    "video_plan": {
        "title": "Short punchy video title (max 8 words)",
        "master_format": "9:16",
        "duration_seconds": 45,
        "pacing_hint": "fast",
        "audience_mode": "sound_off_first",
        "source_visibility": "none",
        "scenes": [
            {
                "scene_id": "scene-1",
                "purpose": "hook",
                "duration_seconds": 12,
                "layout_hint": "headline",
                "headline": "Short bold headline (max 8 words) that will appear large on screen",
                "body": "1-2 factual sentences the viewer will read — actual news text, NOT a production note",
                "key_figures": ["Real Person Name", "Organization Name"],
                "key_data": "The single most striking number or fact, e.g. '9 people charged'",
                "supporting_points": [],
                "asset_ids": [],
            },
            {
                "scene_id": "scene-2",
                "purpose": "explain",
                "duration_seconds": 12,
                "layout_hint": "split",
                "headline": "New detail headline",
                "body": "A NEW piece of information not mentioned in scene 1",
                "key_figures": ["Person Name"],
                "key_data": "",
                "supporting_points": ["Concrete fact 1", "Concrete fact 2"],
                "asset_ids": [],
            },
            {
                "scene_id": "scene-3",
                "purpose": "detail",
                "duration_seconds": 11,
                "layout_hint": "stat",
                "headline": "Key number or consequence",
                "body": "Context or implication of the main fact",
                "key_figures": [],
                "key_data": "The most striking quantitative fact from the article",
                "supporting_points": [],
                "asset_ids": [],
            },
            {
                "scene_id": "scene-4",
                "purpose": "takeaway",
                "duration_seconds": 10,
                "layout_hint": "minimal",
                "headline": "What's next or why it matters",
                "body": "Forward-looking or consequence statement",
                "key_figures": [],
                "key_data": "",
                "supporting_points": [],
                "asset_ids": [],
            },
        ],
    },
    "voiceover": (
        "Full narration script that a news anchor would read aloud. "
        "Natural flow, 40–60 seconds reading time. "
        "Must cover: what happened, who is involved, key facts, and what happens next."
    ),
    "image_prompts": [
        {
            "scene_id": "scene-1",
            "label": "Scene 1 background image",
            "prompt": "Detailed English image generation prompt compatible with DALL-E / Midjourney",
            "style": "cinematic",
        }
    ],
}

_INSTRUCTIONS = """You are an experienced social media news commentator.
Read the article below and generate YouTube Shorts / Instagram Reels content.

STRICT RULES:
1. scene.body = text the viewer will READ on screen — not a production note, not a design brief.
   Write it as a real news sentence: "Nine people, including rappers Pooh Shiesty and Big30, have been federally charged..."
2. voiceover = natural anchor narration. 40–60 seconds reading time. Engaging, human, like a podcast host.
3. key_figures = ONLY real names of people, teams, companies, or government agencies found in the article.
   NEVER use generic words like "Dallas", "Studio", "Evidence", "Eight", "Earth", "Finding".
4. key_data = the most striking single fact with a number: "9 charged", "$2.3B loss", "3–1 final score".
   If no clear number exists, use an empty string.
5. NEVER use ellipsis (...). NEVER truncate text. Write complete sentences.
6. Each scene must introduce NEW information — no repeating scene 1 in scene 2.
7. Use 1–4 scenes. If the story is simple, 1–2 scenes is enough.
   Do NOT pad with filler scenes.
8. image_prompts: English prompts ready for DALL-E 3 / Midjourney. Be specific and visual.
9. Match the language of the article (English article → English output).
10. layout_hint choices: headline, split, stat, timeline, quote, comparison, minimal, full-bleed
    purpose choices: hook, explain, detail, context, comparison, takeaway, close

Return ONLY valid JSON matching the schema. No markdown, no commentary."""


def _build_prompt(article: dict[str, Any]) -> str:
    article_text = _extract_article_text(article)
    article_meta = {
        "title": _compact(str(article.get("title") or "")),
        "source_name": _compact(str(article.get("source_name") or "")),
        "category": _compact(str(article.get("category") or "general")),
        "published_at": _compact(str(article.get("published_at") or "")),
        "tags": article.get("tags") or [],
        "language": _compact(str(article.get("language") or "en")),
        "url": _compact(str(article.get("url") or "")),
        "image_url": _compact(str(article.get("image_url") or "")),
        "article_text": article_text,
    }

    return (
        f"{_INSTRUCTIONS}\n\n"
        f"Article:\n{json.dumps(article_meta, ensure_ascii=False)}\n\n"
        f"Return JSON exactly matching this schema:\n{json.dumps(_SCHEMA, ensure_ascii=False)}"
    )


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------

class ContentGenerationError(Exception):
    pass


async def _call_ollama(prompt: str) -> dict[str, Any]:
    payload = {
        "model": settings.OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0.75,
            "top_p": 0.90,
            "repeat_penalty": 1.05,
        },
    }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(2000.0, connect=5.0)) as client:
            response = await client.post(f"{settings.OLLAMA_BASE_URL}/api/generate", json=payload)
            response.raise_for_status()
    except Exception as exc:
        raise ContentGenerationError(f"Ollama isteği başarısız: {exc}") from exc

    raw = _compact(response.json().get("response", ""))
    # Strip potential markdown fences
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ContentGenerationError(f"LLM JSON parse hatası: {exc}\nRaw: {raw[:300]}") from exc


# ---------------------------------------------------------------------------
# Payload builder
# ---------------------------------------------------------------------------

def _build_remotion_payload(article: dict[str, Any], llm: dict[str, Any]) -> dict[str, Any]:
    """LLM çıktısını Remotion PromptVideo.tsx ile uyumlu payload'a çevirir."""
    video_plan = llm.get("video_plan") or {}
    scenes_raw = video_plan.get("scenes") or []

    scenes = []
    for s in scenes_raw:
        scenes.append(
            {
                "scene_id": _compact(s.get("scene_id") or ""),
                "purpose": _compact(s.get("purpose") or "hook"),
                "duration_seconds": int(s.get("duration_seconds") or 10),
                "layout_hint": _compact(s.get("layout_hint") or "headline"),
                "headline": _compact(s.get("headline") or ""),
                "body": _compact(s.get("body") or ""),
                "key_figures": [_compact(f) for f in (s.get("key_figures") or []) if _compact(f)],
                "key_data": _compact(s.get("key_data") or ""),
                "supporting_points": [_compact(p) for p in (s.get("supporting_points") or []) if _compact(p)],
                "source_line": "",
                "asset_ids": s.get("asset_ids") or [],
                "visual_direction": "",
                "motion_direction": "",
                "transition_from_previous": "fade",
            }
        )

    total_duration = sum(s["duration_seconds"] for s in scenes) or int(video_plan.get("duration_seconds") or 45)
    category = _compact(str(article.get("category") or "general"))
    image_url = _compact(str(article.get("image_url") or ""))

    visual_assets = []
    if image_url:
        visual_assets.append(
            {
                "asset_id": "asset-article-hero",
                "url": image_url,
                "kind": "article_image",
                "source_name": _compact(str(article.get("source_name") or "")),
                "alt_text": _compact(str(article.get("title") or "")),
            }
        )

    video_title = _compact(str(video_plan.get("title") or article.get("title") or ""))
    # Build a summary from the first scene's body, falling back to the article title
    first_body = next((s["body"] for s in scenes if s["body"]), "")
    summary_text = first_body or video_title
    source_name = _compact(str(article.get("source_name") or ""))
    all_key_figures: list[str] = list({f for s in scenes for f in s["key_figures"]})[:4]
    key_data_text = next((s["key_data"] for s in scenes if s["key_data"]), "")
    narrative = [s["body"] for s in scenes if s["body"]][:3]

    return {
        # ── Root-level fields required by parseRemotionPayload() ──────────────
        "headline": video_title,
        "summary": summary_text,
        "durationSeconds": total_duration,
        "category": category,
        "keyPoints": narrative[1:],           # scene 2+ bodies as key points
        "whyItMatters": narrative[-1] if len(narrative) > 1 else summary_text,
        "sources": [source_name] if source_name else [],
        "promptText": video_title,
        "formatHint": "Editorial motion-graphics short",
        "storyAngle": video_title,
        "visualBrief": "Readable motion graphics with labeled facts and clear visual hierarchy.",
        "motionTreatment": "Clean panel choreography and subtle kinetic typography.",
        "transitionStyle": "Shape wipes and restrained motion transitions.",
        "tone": "Urgent and factual",
        "sceneSequence": [s["headline"] for s in scenes if s["headline"]],
        "designKeywords": ["editorial motion", "clear typography"],
        "mustInclude": [],
        "avoid": ["Publisher logos", "Unsupported claims"],
        # ─────────────────────────────────────────────────────────────────────
        "sourceCount": 1,
        "articleCount": 1,
        "videoPlan": {
            "title": video_title,
            "audience_mode": "sound_off_first",
            "master_format": "9:16",
            "duration_seconds": total_duration,
            "pacing_hint": _compact(str(video_plan.get("pacing_hint") or "fast")),
            "source_visibility": "none",
            "scenes": scenes,
        },
        "videoContent": {
            "headline": video_title,
            "narrative": narrative,
            "key_figures": all_key_figures,
            "key_data": key_data_text,
            "source_line": source_name,
            "duration_seconds": total_duration,
        },
        "visualAssets": visual_assets,
        "storyboard": {
            "visual_thesis": video_title,
            "scenes": [
                {
                    "scene_type": s["purpose"],
                    "duration_seconds": s["duration_seconds"],
                    "layout_hint": s["layout_hint"],
                    "kicker": s["purpose"].upper(),
                    "headline": s["headline"],
                    "body": s["body"],
                    "source_line": "",
                    "asset_ids": s["asset_ids"],
                    "bullet_points": s["supporting_points"],
                    "stats": (
                        [{"label": "Key data", "value": s["key_data"]}]
                        if s["key_data"]
                        else []
                    ),
                    "chips": s["key_figures"],
                    "visual_elements": [],
                }
                for s in scenes
            ],
        },
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def generate_article_content(article: dict[str, Any]) -> ArticleContentResponse:
    """Ham article JSON → LLM → ArticleContentResponse."""
    prompt = _build_prompt(article)
    llm_output = await _call_ollama(prompt)

    remotion_payload = _build_remotion_payload(article, llm_output)

    voiceover = _compact(str(llm_output.get("voiceover") or ""))

    raw_prompts = llm_output.get("image_prompts") or []
    image_prompts: list[ImagePrompt] = []
    for ip in raw_prompts:
        if isinstance(ip, dict):
            image_prompts.append(
                ImagePrompt(
                    scene_id=_compact(str(ip.get("scene_id") or "")),
                    label=_compact(str(ip.get("label") or "")),
                    prompt=_compact(str(ip.get("prompt") or "")),
                    style=_compact(str(ip.get("style") or "cinematic")),
                )
            )

    return ArticleContentResponse(
        remotion_payload=remotion_payload,
        voiceover=voiceover,
        image_prompts=image_prompts,
    )


# ---------------------------------------------------------------------------
# TTS
# ---------------------------------------------------------------------------

def _audio_dir() -> Path:
    path = Path(settings.TTS_AUDIO_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


async def generate_voiceover(text: str, provider: str, voice_id: str) -> VoiceoverResponse:
    audio_id = str(uuid.uuid4())
    audio_dir = _audio_dir()
    output_path = audio_dir / f"{audio_id}.mp3"

    if provider == "edge_tts":
        try:
            import edge_tts  # type: ignore[import]
        except ImportError as exc:
            raise ContentGenerationError("edge-tts yüklü değil. `pip install edge-tts` komutunu çalıştırın.") from exc

        try:
            voice = voice_id or "en-US-AriaNeural"
            communicate = edge_tts.Communicate(text, voice=voice)
            await communicate.save(str(output_path))
        except Exception as exc:
            raise ContentGenerationError(f"Edge TTS ses üretimi başarısız: {exc}") from exc

    elif provider == "elevenlabs":
        if not settings.ELEVENLABS_API_KEY:
            raise ContentGenerationError(
                "ELEVENLABS_API_KEY ayarlanmamış. .env dosyasına ELEVENLABS_API_KEY ekleyin."
            )
        try:
            from elevenlabs.client import ElevenLabs  # type: ignore[import]
        except ImportError as exc:
            raise ContentGenerationError("elevenlabs yüklü değil. `pip install elevenlabs` komutunu çalıştırın.") from exc

        try:
            client = ElevenLabs(api_key=settings.ELEVENLABS_API_KEY)
            effective_voice_id = voice_id or "21m00Tcm4TlvDq8ikWAM"  # Rachel (default)
            audio_bytes = client.text_to_speech.convert(
                voice_id=effective_voice_id,
                text=text,
                model_id="eleven_multilingual_v2",
            )
            with open(output_path, "wb") as f:
                for chunk in audio_bytes:
                    f.write(chunk)
        except ContentGenerationError:
            raise
        except Exception as exc:
            raise ContentGenerationError(f"ElevenLabs ses üretimi başarısız: {exc}") from exc
    else:
        raise ContentGenerationError(f"Bilinmeyen TTS provider: {provider}")

    # Rough duration estimate: ~150 words/min
    word_count = len(text.split())
    duration = round(word_count / 150 * 60, 1)

    return VoiceoverResponse(
        audio_url=f"/static/audio/{audio_id}.mp3",
        duration_seconds=duration,
        provider=provider,
    )


async def get_available_voices(provider: str) -> list[TtsVoice]:
    if provider == "edge_tts":
        try:
            import edge_tts  # type: ignore[import]
            voices_data = await edge_tts.list_voices()
            return [
                TtsVoice(
                    id=v["ShortName"],
                    name=v["FriendlyName"],
                    gender=v.get("Gender", ""),
                    language=v.get("Locale", ""),
                )
                for v in voices_data
                if v.get("ShortName")
            ]
        except Exception:
            pass
        # Fallback popular voices
        return [
            TtsVoice(id="en-US-AriaNeural", name="Aria (US Female)", gender="Female", language="en-US"),
            TtsVoice(id="en-US-GuyNeural", name="Guy (US Male)", gender="Male", language="en-US"),
            TtsVoice(id="en-GB-SoniaNeural", name="Sonia (UK Female)", gender="Female", language="en-GB"),
            TtsVoice(id="tr-TR-EmelNeural", name="Emel (TR Female)", gender="Female", language="tr-TR"),
            TtsVoice(id="tr-TR-AhmetNeural", name="Ahmet (TR Male)", gender="Male", language="tr-TR"),
        ]

    if provider == "elevenlabs":
        if not settings.ELEVENLABS_API_KEY:
            return []
        try:
            from elevenlabs.client import ElevenLabs  # type: ignore[import]
            client = ElevenLabs(api_key=settings.ELEVENLABS_API_KEY)
            voices = client.voices.get_all()
            return [
                TtsVoice(
                    id=v.voice_id,
                    name=v.name or "",
                    gender=getattr(v.labels, "gender", "") if v.labels else "",
                    language=getattr(v.labels, "language", "") if v.labels else "",
                    preview_url=v.preview_url or "",
                )
                for v in voices.voices
            ]
        except Exception:
            pass

    return []


# ---------------------------------------------------------------------------
# Image generation (Stable Diffusion XL)
# ---------------------------------------------------------------------------

def _image_dir() -> Path:
    path = Path(settings.IMAGE_OUTPUT_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


async def generate_image(request: "ImageGenerateRequest") -> ImageGenerateResponse:  # type: ignore[name-defined]
    """SDXL servisine istek gönderir, PNG'yi kaydeder ve statik URL döner."""
    from app.schemas.content import ImageGenerateRequest  # local import to avoid circular

    image_id = str(uuid.uuid4())
    output_path = _image_dir() / f"{image_id}.png"

    url = f"{settings.SDXL_BASE_URL.rstrip('/')}/generate?fmt=binary"

    payload: dict[str, Any] = {
        "prompt": request.prompt,
        "negative_prompt": request.negative_prompt,
        "width": request.width,
        "height": request.height,
        "num_inference_steps": request.num_inference_steps,
        "guidance_scale": request.guidance_scale,
    }
    if request.seed is not None:
        payload["seed"] = request.seed

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=5.0)) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()

            content_type = response.headers.get("content-type", "")
            if "image" not in content_type and len(response.content) < 100:
                raise ContentGenerationError(
                    f"SDXL servisi geçersiz yanıt döndürdü. Content-Type: {content_type}"
                )

            output_path.write_bytes(response.content)

    except ContentGenerationError:
        raise
    except httpx.ConnectError as exc:
        raise ContentGenerationError(
            f"SDXL servisine bağlanılamadı ({settings.SDXL_BASE_URL}): {exc}"
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise ContentGenerationError(
            f"SDXL servisi hata döndürdü: HTTP {exc.response.status_code}"
        ) from exc
    except Exception as exc:
        raise ContentGenerationError(f"Görsel üretimi başarısız: {exc}") from exc

    return ImageGenerateResponse(
        image_url=f"/static/images/{image_id}.png",
        prompt=request.prompt,
        model="sdxl",
        width=request.width,
        height=request.height,
        num_inference_steps=request.num_inference_steps,
        guidance_scale=request.guidance_scale,
        seed=request.seed,
    )


# ---------------------------------------------------------------------------
# Video rendering
# ---------------------------------------------------------------------------

def _video_dir() -> Path:
    path = Path(settings.VIDEO_OUTPUT_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


async def render_video(request: "RenderVideoRequest") -> "RenderVideoResponse":  # type: ignore[name-defined]
    """Remotion renderer servisine render isteği gönderir ve MP4 URL döner."""
    from app.schemas.content import RenderVideoRequest, RenderVideoResponse  # noqa: F401

    video_id = str(uuid.uuid4())
    output_filename = f"{video_id}.mp4"

    renderer_url = f"{settings.RENDERER_URL.rstrip('/')}/render"

    body: dict[str, Any] = {
        "payload": request.payload,
        "audioUrl": request.audio_url,
        "durationInFrames": request.duration_in_frames,
        "fps": request.fps,
        "width": request.width,
        "height": request.height,
        "outputFilename": output_filename,
    }

    try:
        # Render can take several minutes for longer videos
        async with httpx.AsyncClient(timeout=httpx.Timeout(600.0, connect=10.0)) as client:
            response = await client.post(renderer_url, json=body)
            response.raise_for_status()
            result = response.json()
    except httpx.ConnectError as exc:
        raise ContentGenerationError(
            f"Renderer servisine bağlanılamadı ({settings.RENDERER_URL}). "
            "docker-compose'da 'renderer' servisi çalışıyor mu?"
        ) from exc
    except httpx.HTTPStatusError as exc:
        body_text = exc.response.text[:500]
        raise ContentGenerationError(
            f"Renderer servisi hata döndürdü: HTTP {exc.response.status_code} — {body_text}"
        ) from exc
    except Exception as exc:
        raise ContentGenerationError(f"Video render başarısız: {exc}") from exc

    duration = result.get("durationSeconds", request.duration_in_frames / request.fps)
    return RenderVideoResponse(
        video_url=f"/static/videos/{output_filename}",
        duration_seconds=duration,
    )
