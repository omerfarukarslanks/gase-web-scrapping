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
    TtsVoice,
    VoiceoverResponse,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _compact(value: str | None) -> str:
    return " ".join((value or "").split()).strip()


_SCRAPE_ERROR_PATTERNS = re.compile(
    r"browser extension.*blocking|video player.*loading|disable.*on this site|"
    r"enable javascript to|javascript is required|please enable javascript|"
    r"subscribe to read|sign in to read|log in to read|paywall|access denied",
    re.IGNORECASE,
)

_MIN_CONTENT_LENGTH = 400  # Bu uzunluğun altındaki içerik yetersiz sayılır
_GARBAGE_CHECK_MAX_LEN = 600  # Sadece kısa metinlerde garbage kontrolü yap


def _is_scrape_garbage(text: str) -> bool:
    """Metnin scraping hatası veya erişim engeli içerip içermediğini kontrol eder.
    Uzun metinlerde (>600 karakter) garbage pattern aranmaz — gerçek içerik barındırıyor olabilir."""
    if len(text) > _GARBAGE_CHECK_MAX_LEN:
        return False
    return bool(_SCRAPE_ERROR_PATTERNS.search(text))


def _extract_article_text(article: dict[str, Any]) -> str:
    """En zengin gerçek metin kaynağını döner; scraping hatalarını ve kısa içerikleri atlar."""
    for field in ("content_text", "content_snippet", "summary", "title"):
        text = _compact(str(article.get(field) or ""))
        if not text:
            continue
        if _is_scrape_garbage(text):
            logger.warning("Field '%s' scraping garbage içeriyor, atlanıyor.", field)
            continue
        if len(text) > _MIN_CONTENT_LENGTH:
            return text[:settings.ANALYSIS_TEXT_CHAR_LIMIT]
    # Hiçbir alan yeterli değilse kısa summary veya title'a düş
    for field in ("summary", "title"):
        text = _compact(str(article.get(field) or ""))
        if text:
            return text
    return ""


def _detect_language(article: dict[str, Any]) -> str:
    """content_text üzerinden dili tespit eder; başarısız olursa metadata'ya düşer."""
    fallback = _compact(str(article.get("language") or "en")) or "en"
    text = _compact(str(article.get("content_text") or article.get("content_snippet") or ""))
    if len(text) < 30:
        return fallback
    try:
        from langdetect import detect, LangDetectException  # type: ignore[import]
        return detect(text[:600])
    except Exception:
        return fallback


# ---------------------------------------------------------------------------
# LLM Prompt
# ---------------------------------------------------------------------------

_SCHEMA = {
    # voiceover önce geliyor — LLM token bütçesi tükenmeden üretsin
    "voiceover": "Write the full anchor narration here. 3-5 complete sentences. 40-60 seconds when read aloud.",
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
}

_INSTRUCTIONS = """You are an experienced social media news editor. Your job is to turn a news article into a punchy YouTube Shorts / Instagram Reels script.

Before writing anything, mentally scan the article for:
  A) The single most surprising or emotional moment (a quote, a reaction, a reversal)
  B) The strongest NUMBER or historical stat (years, records, firsts, amounts)
  C) The core "why it matters" for a casual viewer who knows nothing about this topic

These three elements MUST appear somewhere in your output.

STRICT RULES:
1. voiceover MUST be a non-empty string — 4 to 6 complete sentences a news anchor reads aloud.
   - Open with the most gripping fact or quote from the article, not a generic summary.
     BAD:  "The community is outraged as the items are set to leave the country."
     GOOD: "'[Direct quote from the article],' says [Name from the article]."
     If a direct quote captures the story better than any summary, lead with the quote.
     IMPORTANT: The examples above are illustrative only. Never copy example text into your output — use only quotes and names from the current article.
   - Include at least one specific number, date, or record.
   - Close with what happens next or why this matters.
   - Write voiceover FIRST in the JSON before video_plan.

2. scene.body = text the viewer will READ on screen. Real news sentences only.
   Good: "Bezzecchi told reporters: 'His message moved me.' Now he leads MotoGP."
   Bad: "Exciting developments in motorsport" or any vague production note.

3. scene selection priority — always prefer the MOST IMPACTFUL angle:
   - Emotional quotes > dry facts
   - Historical records/firsts > general background
   - Surprising reversals > expected outcomes
   - Specific numbers > vague descriptions
   NEVER fill a scene with secondary trivia when a stronger fact exists in the article.

4. key_figures = ONLY real names of people, teams, clubs, or organizations from the article.
   NEVER use generic words like "Stars", "Drivers", "Officials", "Rising Talent".

5. key_data = one striking fact that includes a real number or record.
   Good: "20 years — Italy's F1 drought", "3 consecutive wins", "$2.3B deal"
   Bad: "Two rising stars", "Rossi will compete", or any sentence without a number.
   If no number exists in the article, use an empty string.

6. NEVER use ellipsis (...). Write complete sentences only.

11. scene.headline is subject to the same factual accuracy and emotional language rules as scene.body. Headlines are NOT creative summaries — they must stay within what the article explicitly states.
    BAD:  "Rossi's message moved Bezzecchi to tears"  ← escalates "me emocionó"
    GOOD: "Rossi's call kept Bezzecchi winning"       ← stays within article facts
    If the body correctly says "moved me", the headline cannot say "to tears".
    If the body correctly says "led the championship", the headline cannot say "won the title".

7. Each scene must introduce NEW information. No repeating scene 1 in scene 2.

8. Use 1–4 scenes based on story depth. Do NOT pad with filler scenes.

12. The takeaway scene (purpose: "takeaway") must close with a fact, consequence, or direct implication that is explicitly stated or clearly shown in the article. Do NOT invent editorial angles, themes, or conclusions that are not in the article.
    BAD:  "This mission could set a new standard for international collaboration in lunar travel."  ← not in article
    GOOD: "Hansen will fly further from Earth than any human before — more than 250,000 miles."  ← directly from article

9. Match the language of the article (Spanish article → Spanish output, English → English).

10. layout_hint choices: headline, split, stat, timeline, quote, comparison, minimal, full-bleed
    purpose choices: hook, explain, detail, context, comparison, takeaway, close
    Use layout_hint "quote" when a scene features a direct quote from a person.
    Use layout_hint "stat" only when key_data contains a real number.

CRITICAL: The JSON must start with the "voiceover" key. voiceover must never be empty.

CLAIM STRENGTH: When translating records, titles, or achievements, always use the weakest accurate form. Never upgrade a claim to a stronger version.
- "led the championship" ≠ "won the championship"
- "won races" ≠ "won the world title"
- "could become champion" ≠ "will become champion"
- "one of the best" ≠ "the greatest ever"
If the article says someone "led" or "was competitive", do NOT say they "won" or "dominated".

FACTUAL ACCURACY: NEVER add details, timeframes, emotions, or intensifiers that are not explicitly stated in the article.
- Do NOT write "moved to tears" if the article only says "moved me".
- Do NOT write "in just two years" if no timeframe is given.
- Do NOT invent quotes or paraphrase them as direct quotes.
- Every claim in voiceover and scene.body must be directly traceable to the article text.
- If the article does not give a specific number for a stat, do NOT invent one. Use the descriptive form instead: "consecutive wins" not "3 consecutive wins", "multiple goals" not "4 goals".
- Do NOT add "first time", "first ever", "historic first", or similar superlatives unless the article explicitly uses those words. The article saying something is an "objective" or "goal" does NOT mean it is the first time it has been done.

EMOTIONAL LANGUAGE TRANSLATION — Spanish articles often use emotionally rich words. Translate their EXACT meaning, never escalate:
- "emocionó" / "me emocionó" → "moved me" or "affected me" — NOT "moved me to tears", NOT "made me cry"
- "increíble" → "remarkable" or "impressive" — NOT "unbelievable" or "jaw-dropping"
- "histórico" → "historic" — NOT "greatest ever" or "all-time"
- "apasionante" → "exciting" — NOT "breathtaking" or "electrifying"
- "impresionante" → "impressive" — NOT "stunning" or "incredible"
- When in doubt: use the literal translation, not the most dramatic English equivalent.
- This rule applies to ALL text fields without exception: voiceover, scene.body, scene.headline, headline fields, and sceneSequence entries. If it would be wrong in scene.body, it is equally wrong in a scene.headline.

Return ONLY valid JSON matching the schema. No markdown, no commentary."""


def _build_prompt(article: dict[str, Any]) -> str:
    article_text = _extract_article_text(article)
    article_meta = {
        "title": _compact(str(article.get("title") or "")),
        "source_name": _compact(str(article.get("source_name") or "")),
        "category": _compact(str(article.get("category") or "general")),
        "published_at": _compact(str(article.get("published_at") or "")),
        "tags": article.get("tags") or [],
        "language": _detect_language(article),
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
        "think": False,   # qwen3 gibi thinking modellerde <think> bloklarını devre dışı bırakır
        "options": {
            "temperature": 0.75,
            "top_p": 0.90,
            "repeat_penalty": 1.05,
            "num_predict": 2048,   # voiceover + video_plan için yeterli token
            "num_ctx": 8192,       # context penceresi
        },
    }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(2000.0, connect=5.0)) as client:
            response = await client.post(f"{settings.OLLAMA_BASE_URL}/api/generate", json=payload)
            response.raise_for_status()
    except Exception as exc:
        raise ContentGenerationError(f"Ollama isteği başarısız: {exc}") from exc

    raw = _compact(response.json().get("response", ""))
    logger.info("Ollama raw response (first 800 chars): %s", raw[:800])

    # Strip <think>...</think> blocks (qwen3 ve benzeri thinking modeller için)
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()

    # Strip potential markdown fences
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    if not raw:
        raise ContentGenerationError("LLM boş yanıt döndürdü. Model yüklü ve erişilebilir mi?")

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
# Scene duration redistribution
# ---------------------------------------------------------------------------

# Edge TTS +10% rate → ortalama 2.75 kelime/saniye
_WORDS_PER_SECOND = 2.75
_MIN_SCENE_SECONDS = 3


def _redistribute_scene_durations(scenes: list[dict], target_seconds: float) -> list[dict]:
    """Sahne sürelerini voiceover kelime sayısından türetilen hedef süreye orantısal dağıtır.

    - Her sahne en az _MIN_SCENE_SECONDS alır.
    - Son sahne yuvarlama artıklarını yutar.
    - scenes listesi değiştirilmez; yeni liste döner.
    """
    if not scenes or target_seconds <= 0:
        return scenes

    current_total = sum(s["duration_seconds"] for s in scenes)
    if current_total <= 0:
        return scenes

    scale = target_seconds / current_total
    new_scenes: list[dict] = []
    allocated = 0

    for i, scene in enumerate(scenes):
        if i == len(scenes) - 1:
            # Son sahne: kalan sürenin tamamını al
            duration = max(_MIN_SCENE_SECONDS, round(target_seconds) - allocated)
        else:
            duration = max(_MIN_SCENE_SECONDS, round(scene["duration_seconds"] * scale))
            allocated += duration
        new_scenes.append({**scene, "duration_seconds": duration})

    return new_scenes


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def generate_article_content(article: dict[str, Any]) -> ArticleContentResponse:
    """Ham article JSON → LLM → ArticleContentResponse."""
    article_text = _extract_article_text(article)
    if len(article_text) < _MIN_CONTENT_LENGTH:
        raise ContentGenerationError(
            "Makale içeriği yetersiz — yalnızca başlık veya kısa özet mevcut. "
            "Model bu içerikten güvenilir video scripti üretemez."
        )
    prompt = _build_prompt(article)
    llm_output = await _call_ollama(prompt)

    remotion_payload = _build_remotion_payload(article, llm_output)

    voiceover = _compact(str(llm_output.get("voiceover") or ""))
    logger.info("LLM output keys: %s | voiceover length: %d", list(llm_output.keys()), len(voiceover))

    # Voiceover kelime sayısından tahmini süre hesapla ve sahne sürelerini yeniden dağıt.
    # Bu sayede TTS kullanılmasa da (müzik, sessiz video) süreler anlamlı olur.
    if voiceover:
        word_count = len(voiceover.split())
        estimated_seconds = max(10.0, word_count / _WORDS_PER_SECOND)
        logger.info(
            "Voiceover word count: %d → estimated duration: %.1fs", word_count, estimated_seconds
        )

        scenes = remotion_payload["videoPlan"]["scenes"]
        redistributed = _redistribute_scene_durations(scenes, estimated_seconds)
        new_total = sum(s["duration_seconds"] for s in redistributed)

        remotion_payload["videoPlan"]["scenes"] = redistributed
        remotion_payload["videoPlan"]["duration_seconds"] = new_total
        remotion_payload["videoContent"]["duration_seconds"] = new_total
        remotion_payload["durationSeconds"] = new_total

        # storyboard sahnelerini de güncelle
        for sb_scene, rs in zip(remotion_payload["storyboard"]["scenes"], redistributed):
            sb_scene["duration_seconds"] = rs["duration_seconds"]

        logger.info(
            "Scene durations redistributed: %s → total %ds",
            [s["duration_seconds"] for s in redistributed],
            new_total,
        )

    return ArticleContentResponse(
        remotion_payload=remotion_payload,
        voiceover=voiceover,
        image_prompts=[],
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
            voice = voice_id or "en-US-JennyNeural"
            communicate = edge_tts.Communicate(text, voice=voice, rate="+10%", pitch="+0Hz")
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
