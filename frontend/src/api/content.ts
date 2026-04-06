import apiClient from './client';
import type {
  ArticleContentResponse,
  ImageGenerateRequest,
  ImageGenerateResponse,
  RenderVideoRequest,
  RenderVideoResponse,
  TtsVoice,
  VoiceoverResponse,
} from '../types/content';

export async function generateFromArticle(
  article: Record<string, unknown>,
): Promise<ArticleContentResponse> {
  const { data } = await apiClient.post('/content/generate-from-article', { article });
  return data;
}

export async function generateVoiceover(
  text: string,
  provider: 'elevenlabs' | 'edge_tts',
  voiceId: string,
): Promise<VoiceoverResponse> {
  const { data } = await apiClient.post('/content/generate-voiceover', {
    text,
    provider,
    voice_id: voiceId,
  });
  return data;
}

export async function getTtsVoices(provider: string): Promise<TtsVoice[]> {
  const { data } = await apiClient.get('/content/tts-voices', { params: { provider } });
  return data;
}

export async function generateImage(request: ImageGenerateRequest): Promise<ImageGenerateResponse> {
  const { data } = await apiClient.post('/content/generate-image', { model: 'sdxl', ...request });
  return data;
}

export async function renderVideo(request: RenderVideoRequest): Promise<RenderVideoResponse> {
  // Convert camelCase frontend types → snake_case Pydantic schema
  const body = {
    payload: request.payload,
    audio_url: request.audioUrl ?? null,
    duration_in_frames: request.durationInFrames,
    fps: request.fps,
    width: request.width,
    height: request.height,
  };
  const { data } = await apiClient.post('/content/render-video', body, {
    timeout: 600_000, // 10 min — rendering can be slow
  });
  return data;
}
