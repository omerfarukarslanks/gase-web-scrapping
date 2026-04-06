from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ArticleContentRequest(BaseModel):
    article: dict[str, Any] = Field(..., description="Ham article JSON — herhangi bir validasyon uygulanmaz")


class ImagePrompt(BaseModel):
    scene_id: str = ""
    label: str = ""
    prompt: str = ""
    style: str = "cinematic"


class ArticleContentResponse(BaseModel):
    remotion_payload: dict[str, Any] = Field(
        ..., description="Remotion PromptVideo.tsx ile uyumlu video planı"
    )
    voiceover: str = Field("", description="TTS'e gönderilecek tam seslendirilecek metin")
    image_prompts: list[ImagePrompt] = Field(
        default_factory=list, description="Her sahne için DALL-E / Midjourney uyumlu görsel promptları"
    )


class VoiceoverRequest(BaseModel):
    text: str = Field(..., min_length=1)
    provider: Literal["elevenlabs", "edge_tts"] = "edge_tts"
    voice_id: str = Field(
        "",
        description="ElevenLabs: voice UUID | Edge TTS: voice name (ör. en-US-AriaNeural)",
    )


class VoiceoverResponse(BaseModel):
    audio_url: str = Field(..., description="/static/audio/{uuid}.mp3 olarak serve edilir")
    duration_seconds: float = 0.0
    provider: str = ""


class TtsVoice(BaseModel):
    id: str
    name: str
    gender: str = ""
    language: str = ""
    preview_url: str = ""


class ImageGenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=2000, description="Görsel üretim promptu")
    negative_prompt: str = Field(
        "blurry, low quality, watermark, text overlay, logo, cartoon, anime, nsfw, distorted, deformed",
        max_length=2000,
        description="Görselde istenmeyen unsurlar",
    )
    width: int = Field(768, ge=512, le=2048, description="Genişlik (px)")
    height: int = Field(1344, ge=512, le=2048, description="Yükseklik (px)")
    num_inference_steps: int = Field(30, ge=1, le=150, description="Adım sayısı")
    guidance_scale: float = Field(7.5, ge=1.0, le=20.0, description="Yönlendirme katsayısı")
    seed: int | None = Field(None, ge=0, description="Seed (None = rastgele)")
    model: str = Field("sdxl", description="Kullanılacak model")


class ImageGenerateResponse(BaseModel):
    image_url: str = Field(..., description="/static/images/{uuid}.png olarak serve edilir")
    prompt: str = ""
    model: str = "sdxl"
    width: int = 768
    height: int = 1344
    num_inference_steps: int = 30
    guidance_scale: float = 7.5
    seed: int | None = None


class RenderVideoRequest(BaseModel):
    payload: dict[str, Any] = Field(..., description="Remotion RemotionPromptPayload — SDXL görseller dahil")
    audio_url: str | None = Field(None, description="Sese dönüştürülmüş MP3 URL'si (opsiyonel)")
    duration_in_frames: int = Field(900, ge=30, description="Toplam frame sayısı")
    fps: int = Field(30, ge=1, le=60)
    width: int = Field(1080, ge=320, le=3840)
    height: int = Field(1920, ge=320, le=3840)


class RenderVideoResponse(BaseModel):
    video_url: str = Field(..., description="/static/videos/{uuid}.mp4 olarak serve edilir")
    duration_seconds: float = 0.0
