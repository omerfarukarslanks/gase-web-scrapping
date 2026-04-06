from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.schemas.content import (
    ArticleContentRequest,
    ArticleContentResponse,
    ImageGenerateRequest,
    ImageGenerateResponse,
    RenderVideoRequest,
    RenderVideoResponse,
    TtsVoice,
    VoiceoverRequest,
    VoiceoverResponse,
)
from app.services.article_content_service import (
    ContentGenerationError,
    generate_article_content,
    generate_image,
    generate_voiceover,
    get_available_voices,
    render_video,
)

router = APIRouter()


@router.post("/generate-from-article", response_model=ArticleContentResponse)
async def generate_from_article(request: ArticleContentRequest) -> ArticleContentResponse:
    """Ham article JSON'u direkt olarak LLM'e gönderir ve video içeriği üretir."""
    if not request.article:
        raise HTTPException(status_code=422, detail="article alanı boş olamaz")
    try:
        return await generate_article_content(request.article)
    except ContentGenerationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/generate-voiceover", response_model=VoiceoverResponse)
async def generate_voiceover_endpoint(request: VoiceoverRequest) -> VoiceoverResponse:
    """Verilen metni TTS ile sese çevirir ve MP3 dosyası döner."""
    try:
        return await generate_voiceover(request.text, request.provider, request.voice_id)
    except ContentGenerationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/tts-voices", response_model=list[TtsVoice])
async def list_tts_voices(provider: str = "edge_tts") -> list[TtsVoice]:
    """Seçili TTS provider için kullanılabilir sesleri listeler."""
    return await get_available_voices(provider)


@router.post("/generate-image", response_model=ImageGenerateResponse)
async def generate_image_endpoint(request: ImageGenerateRequest) -> ImageGenerateResponse:
    """Prompt'tan Stable Diffusion XL ile görsel üretir ve statik URL döner."""
    try:
        return await generate_image(request)
    except ContentGenerationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/render-video", response_model=RenderVideoResponse)
async def render_video_endpoint(request: RenderVideoRequest) -> RenderVideoResponse:
    """Remotion renderer ile MP4 video üretir ve statik URL döner."""
    try:
        return await render_video(request)
    except ContentGenerationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
