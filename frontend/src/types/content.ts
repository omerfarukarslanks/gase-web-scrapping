import type { RemotionPromptPayload } from './analysis';

export interface ImagePrompt {
  scene_id: string;
  label: string;
  prompt: string;
  style: string;
}

export interface ArticleContentRequest {
  article: Record<string, unknown>;
}

export interface ArticleContentResponse {
  /** Remotion PromptVideo.tsx ile uyumlu video planı */
  remotion_payload: Partial<RemotionPromptPayload> & Record<string, unknown>;
  /** TTS ile seslendirilecek tam metin */
  voiceover: string;
  /** Her sahne için görsel üretim promptları */
  image_prompts: ImagePrompt[];
}

export interface VoiceoverRequest {
  text: string;
  provider: 'elevenlabs' | 'edge_tts';
  voice_id: string;
}

export interface VoiceoverResponse {
  audio_url: string;
  duration_seconds: number;
  provider: string;
}

export interface TtsVoice {
  id: string;
  name: string;
  gender: string;
  language: string;
  preview_url: string;
}

export interface ImageGenerateRequest {
  prompt: string;
  negative_prompt?: string;
  width?: number;
  height?: number;
  num_inference_steps?: number;
  guidance_scale?: number;
  seed?: number | null;
  model?: string;
}

export interface ImageGenerateResponse {
  image_url: string;
  prompt: string;
  model: string;
  width: number;
  height: number;
  num_inference_steps: number;
  guidance_scale: number;
  seed: number | null;
}

export interface RenderVideoRequest {
  payload: RemotionPromptPayload;
  audioUrl?: string;
  durationInFrames: number;
  fps: number;
  width: number;
  height: number;
}

export interface RenderVideoResponse {
  video_url: string;
  duration_seconds: number;
}
