import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.config import settings

app = FastAPI(
    title="GASE News Scraper",
    description="Automated news scraping from major global sources",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")

# Serve generated static files (TTS audio, SDXL images, rendered videos)
_audio_dir = os.path.abspath(settings.TTS_AUDIO_DIR)    # e.g. /app/static/audio
_image_dir = os.path.abspath(settings.IMAGE_OUTPUT_DIR) # e.g. /app/static/images
_video_dir = os.path.abspath(settings.VIDEO_OUTPUT_DIR) # e.g. /app/static/videos
_static_dir = os.path.dirname(_audio_dir)               # e.g. /app/static
os.makedirs(_audio_dir, exist_ok=True)
os.makedirs(_image_dir, exist_ok=True)
os.makedirs(_video_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=_static_dir), name="static")


@app.get("/api/health")
async def health_check():
    return {"status": "ok"}
