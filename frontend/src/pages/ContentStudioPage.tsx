import { Player } from '@remotion/player';
import { useQuery } from '@tanstack/react-query';
import {
  ArrowLeft,
  ChevronDown,
  Clipboard,
  ClipboardCheck,
  Clapperboard,
  Download,
  Expand,
  ImageIcon,
  Loader2,
  Mic,
  Shrink,
  Video,
  Volume2,
} from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useLocation, useParams } from 'react-router-dom';
import { fetchArticle } from '../api/articles';
import { generateFromArticle, generateImage, generateVoiceover, getTtsVoices, renderVideo } from '../api/content';
import { parseRemotionPayload } from '../lib/remotionPayload';
import { PromptVideo } from '../remotion/PromptVideo';
import type { RemotionPromptPayload } from '../types/analysis';
import type { ArticleContentResponse, TtsVoice } from '../types/content';

const FPS = 30;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const handle = async () => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <button
      onClick={handle}
      title="Kopyala"
      className="inline-flex items-center gap-1 rounded-xl bg-slate-100 px-2 py-1 text-xs font-medium text-slate-600 transition hover:bg-slate-200"
    >
      {copied ? <ClipboardCheck className="h-3 w-3 text-green-600" /> : <Clipboard className="h-3 w-3" />}
      {copied ? 'Kopyalandı' : 'Kopyala'}
    </button>
  );
}

const QUALITY_PRESETS = [
  { label: 'Hızlı', steps: 15 },
  { label: 'Normal', steps: 30 },
  { label: 'Yüksek Kalite', steps: 40 },
] as const;

const DEFAULT_NEGATIVE_PROMPT =
  'blurry, low quality, watermark, text overlay, logo, cartoon, anime, nsfw, distorted, deformed';

function defaultGuidance(style: string): number {
  if (['artistic', 'illustration', 'anime'].includes(style.toLowerCase())) return 5.0;
  return 7.5;
}

// ---------------------------------------------------------------------------
// ImagePromptCard — controlled: parent owns imageUrl
// ---------------------------------------------------------------------------

function ImagePromptCard({
  prompt,
  index,
  imageUrl,
  isVertical,
  onImageGenerated,
}: {
  prompt: { scene_id: string; label: string; prompt: string; style: string };
  index: number;
  imageUrl: string | null;
  isVertical: boolean;
  onImageGenerated: (index: number, url: string | null) => void;
}) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [expanded, setExpanded] = useState(false);

  const [negativePrompt, setNegativePrompt] = useState(DEFAULT_NEGATIVE_PROMPT);
  const [qualityPreset, setQualityPreset] = useState<number>(1);
  const [guidanceScale, setGuidanceScale] = useState(defaultGuidance(prompt.style));

  const width = isVertical ? 768 : 1344;
  const height = isVertical ? 1344 : 768;

  const handleGenerate = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await generateImage({
        prompt: prompt.prompt,
        negative_prompt: negativePrompt,
        width,
        height,
        num_inference_steps: QUALITY_PRESETS[qualityPreset].steps,
        guidance_scale: guidanceScale,
        seed: null,
      });
      onImageGenerated(index, res.image_url);
      setExpanded(false);
    } catch (err: unknown) {
      setError(
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
          (err as Error).message ??
          'Görsel üretilemedi.',
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="rounded-2xl border border-slate-100 bg-slate-50 p-4">
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            {prompt.label || `Sahne ${index + 1}`}
          </span>
          {prompt.style && (
            <span className="rounded-full bg-slate-200 px-2 py-0.5 text-xs text-slate-500">
              {prompt.style}
            </span>
          )}
          <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-400">
            {width}×{height}
          </span>
          {imageUrl && (
            <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-600">
              ✓ Hazır
            </span>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <CopyButton text={prompt.prompt} />
          <button
            onClick={handleGenerate}
            disabled={loading}
            className="inline-flex items-center gap-1 rounded-xl bg-violet-600 px-2 py-1 text-xs font-medium text-white transition hover:bg-violet-700 disabled:opacity-50"
          >
            {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : <ImageIcon className="h-3 w-3" />}
            {loading ? 'Üretiliyor…' : imageUrl ? 'Yeniden Üret' : 'Görsel Üret'}
          </button>
        </div>
      </div>

      {/* Prompt text */}
      <p className="mt-2 text-sm leading-6 text-slate-700">{prompt.prompt}</p>

      {/* Advanced settings toggle */}
      <button
        onClick={() => setShowAdvanced((v) => !v)}
        className="mt-3 inline-flex items-center gap-1 text-xs text-slate-400 hover:text-slate-600"
      >
        <ChevronDown className={`h-3 w-3 transition-transform ${showAdvanced ? 'rotate-180' : ''}`} />
        Gelişmiş ayarlar
      </button>

      {showAdvanced && (
        <div className="mt-3 space-y-4 rounded-xl border border-slate-200 bg-white p-4">
          {/* Quality preset */}
          <div>
            <div className="mb-1">
              <span className="text-xs font-medium text-slate-600">Kalite</span>
              <p className="text-xs text-slate-400">
                Daha fazla adım = daha detaylı görsel, ancak üretim süresi uzar. Önizleme için
                "Hızlı", paylaşım için "Yüksek Kalite" önerilir.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              {QUALITY_PRESETS.map((p, i) => (
                <button
                  key={p.label}
                  onClick={() => setQualityPreset(i)}
                  className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
                    qualityPreset === i
                      ? 'bg-violet-600 text-white'
                      : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                  }`}
                >
                  {p.label} ({p.steps} adım)
                </button>
              ))}
            </div>
          </div>

          {/* Guidance scale */}
          <div>
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-slate-600">Prompt sadakati</span>
              <span className="text-xs font-semibold text-violet-600">{guidanceScale.toFixed(1)}</span>
            </div>
            <p className="mb-2 text-xs text-slate-400">
              Düşük değerlerde model daha özgür ve yaratıcı davranır; yüksek değerlerde prompt'u
              birebir uygulamaya çalışır. Haber görselleri için 7–9 arası idealdir.
            </p>
            <div className="flex items-center gap-2">
              <span className="w-14 text-right text-xs text-slate-400">Yaratıcı</span>
              <input
                type="range"
                min={1}
                max={20}
                step={0.5}
                value={guidanceScale}
                onChange={(e) => setGuidanceScale(parseFloat(e.target.value))}
                className="flex-1 accent-violet-600"
              />
              <span className="w-10 text-xs text-slate-400">Sadık</span>
            </div>
          </div>

          {/* Negative prompt */}
          <div>
            <span className="text-xs font-medium text-slate-600">Negatif prompt</span>
            <p className="mb-1 text-xs text-slate-400">
              Görselde görmek <strong>istemediğin</strong> unsurları virgülle ayırarak yaz. Bulanıklık,
              logo, metin gibi kalite bozucular varsayılan olarak eklidir; gerekirse düzenleyebilirsin.
            </p>
            <textarea
              value={negativePrompt}
              onChange={(e) => setNegativePrompt(e.target.value)}
              rows={2}
              maxLength={2000}
              className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-700 focus:outline-none focus:ring-2 focus:ring-violet-400"
            />
          </div>
        </div>
      )}

      {/* Error */}
      {error && (
        <p className="mt-3 rounded-xl bg-red-50 px-3 py-2 text-xs text-red-600">{error}</p>
      )}

      {/* Generated image — thumbnail by default, expandable */}
      {imageUrl && !loading && (
        <div className="mt-4">
          <div
            className={`relative overflow-hidden rounded-xl bg-slate-100 transition-all ${
              expanded ? '' : 'max-h-52'
            }`}
          >
            <img
              src={imageUrl}
              alt={prompt.label || `Sahne ${index + 1}`}
              className="w-full object-contain"
            />
            {!expanded && (
              <div className="absolute inset-x-0 bottom-0 h-12 bg-gradient-to-t from-slate-100 to-transparent" />
            )}
          </div>

          <div className="mt-2 flex items-center justify-between gap-2">
            <button
              onClick={() => setExpanded((v) => !v)}
              className="inline-flex items-center gap-1 text-xs text-slate-400 hover:text-slate-600"
            >
              {expanded ? (
                <><Shrink className="h-3 w-3" /> Küçült</>
              ) : (
                <><Expand className="h-3 w-3" /> Büyüt</>
              )}
            </button>
            <div className="flex gap-2">
              <a
                href={imageUrl}
                download={`scene-${index + 1}.png`}
                className="inline-flex items-center gap-1 rounded-xl bg-slate-100 px-2 py-1 text-xs font-medium text-slate-600 hover:bg-slate-200"
              >
                İndir
              </a>
              <button
                onClick={() => { onImageGenerated(index, null); setExpanded(false); }}
                className="rounded-xl bg-red-50 px-2 py-1 text-xs font-medium text-red-500 hover:bg-red-100"
              >
                Sil
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Build enriched Remotion payload with injected SDXL images + audio
// ---------------------------------------------------------------------------

function buildEnrichedPayload(
  base: RemotionPromptPayload,
  generatedImages: Record<number, string>,
  imagePrompts: Array<{ scene_id: string; label: string; prompt: string; style: string }>,
): RemotionPromptPayload {
  // Build visualAssets from generated images
  const newAssets = imagePrompts
    .map((ip, idx) => {
      const url = generatedImages[idx];
      if (!url) return null;
      return {
        asset_id: `sdxl-${ip.scene_id}-${idx}`,
        url,
        kind: 'article_image' as const,
        source_article_id: '',
        source_name: 'Stable Diffusion XL',
        alt_text: ip.label || `Sahne ${idx + 1}`,
      };
    })
    .filter(Boolean) as NonNullable<ReturnType<typeof buildEnrichedPayload>['visualAssets']>[number][];

  // Update scenes to reference their generated asset
  const updatedScenes = base.videoPlan.scenes.map((scene, idx) => {
    const assetId = `sdxl-${imagePrompts[idx]?.scene_id ?? scene.scene_id}-${idx}`;
    const hasImage = generatedImages[idx] != null;
    return {
      ...scene,
      asset_ids: hasImage ? [assetId, ...scene.asset_ids] : scene.asset_ids,
    };
  });

  return {
    ...base,
    visualAssets: [...newAssets, ...base.visualAssets],
    videoPlan: {
      ...base.videoPlan,
      scenes: updatedScenes,
    },
  };
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function ContentStudioPage() {
  const { articleId } = useParams<{ articleId: string }>();
  const location = useLocation();

  const preloaded = location.state as ArticleContentResponse | null;

  // TTS state
  const [ttsProvider, setTtsProvider] = useState<'elevenlabs' | 'edge_tts'>('edge_tts');
  const [selectedVoice, setSelectedVoice] = useState('');
  const [ttsLoading, setTtsLoading] = useState(false);
  const [ttsError, setTtsError] = useState<string | null>(null);

  // Audio URL — localStorage for full persistence
  const audioStorageKey = `content-studio-audio-${articleId}`;
  const [audioUrl, setAudioUrlState] = useState<string | null>(
    () => localStorage.getItem(audioStorageKey),
  );
  const setAudioUrl = (url: string | null) => {
    setAudioUrlState(url);
    if (url) localStorage.setItem(audioStorageKey, url);
    else localStorage.removeItem(audioStorageKey);
  };

  useEffect(() => {
    setAudioUrlState(localStorage.getItem(audioStorageKey));
  }, [audioStorageKey]);

  const audioRef = useRef<HTMLAudioElement>(null);

  // Generated images — lifted to parent, keyed by prompt index
  const [generatedImages, setGeneratedImages] = useState<Record<number, string>>(() => {
    const stored: Record<number, string> = {};
    for (let i = 0; i < 20; i++) {
      const key = `content-studio-img-${articleId}-${i}`;
      const val = localStorage.getItem(key);
      if (val) stored[i] = val;
    }
    return stored;
  });

  const handleImageGenerated = useCallback(
    (index: number, url: string | null) => {
      const key = `content-studio-img-${articleId}-${index}`;
      setGeneratedImages((prev) => {
        const next = { ...prev };
        if (url) {
          next[index] = url;
          localStorage.setItem(key, url);
        } else {
          delete next[index];
          localStorage.removeItem(key);
        }
        return next;
      });
    },
    [articleId],
  );

  // Render video state
  const [renderLoading, setRenderLoading] = useState(false);
  const [renderError, setRenderError] = useState<string | null>(null);
  const [renderVideoUrl, setRenderVideoUrl] = useState<string | null>(
    () => localStorage.getItem(`content-studio-video-${articleId}`),
  );

  // --- Content generation ---
  const {
    data: content,
    isLoading: generating,
    error: generateError,
  } = useQuery<ArticleContentResponse>({
    queryKey: ['content-studio', articleId],
    queryFn: async () => {
      const article = await fetchArticle(articleId ?? '');
      return generateFromArticle(article as Record<string, unknown>);
    },
    enabled: Boolean(articleId) && !preloaded,
    initialData: preloaded ?? undefined,
    staleTime: Infinity,
    retry: false,
  });

  // --- TTS voices ---
  const { data: voices = [] } = useQuery<TtsVoice[]>({
    queryKey: ['tts-voices', ttsProvider],
    queryFn: () => getTtsVoices(ttsProvider),
    staleTime: 5 * 60 * 1000,
    select: (data) => data,
  });

  const effectiveVoice = selectedVoice || voices[0]?.id || '';

  // --- Build Remotion payload ---
  const remotionPayload = useMemo(() => {
    if (!content) return null;
    try {
      return parseRemotionPayload(content.remotion_payload);
    } catch (err) {
      console.error('[ContentStudio] parseRemotionPayload failed:', err);
      return null;
    }
  }, [content]);

  // --- Build enriched payload with SDXL images injected ---
  const enrichedPayload = useMemo(() => {
    if (!remotionPayload || !content) return remotionPayload;
    return buildEnrichedPayload(remotionPayload, generatedImages, content.image_prompts);
  }, [remotionPayload, generatedImages, content]);

  const durationInFrames = useMemo(
    () => (remotionPayload ? Math.max(FPS * 8, remotionPayload.durationSeconds * FPS) : FPS * 30),
    [remotionPayload],
  );

  const isVertical = remotionPayload?.videoPlan?.master_format === '9:16';

  const generatedImageCount = Object.keys(generatedImages).length;
  const totalScenes = content?.image_prompts.length ?? 0;
  const canRender = enrichedPayload !== null;

  // --- Generate voiceover ---
  const handleGenerateVoiceover = async () => {
    if (!content?.voiceover) return;
    setTtsLoading(true);
    setTtsError(null);
    setAudioUrl(null);
    try {
      const res = await generateVoiceover(content.voiceover, ttsProvider, effectiveVoice);
      setAudioUrl(res.audio_url);
    } catch (err: unknown) {
      setTtsError(
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
          (err as Error).message ??
          'Ses oluşturulamadı.',
      );
    } finally {
      setTtsLoading(false);
    }
  };

  // --- Render video ---
  const handleRenderVideo = async () => {
    if (!enrichedPayload) return;
    setRenderLoading(true);
    setRenderError(null);
    setRenderVideoUrl(null);
    try {
      const res = await renderVideo({
        payload: enrichedPayload,
        audioUrl: audioUrl ?? undefined,
        durationInFrames,
        fps: FPS,
        width: isVertical ? 1080 : 1280,
        height: isVertical ? 1920 : 720,
      });
      setRenderVideoUrl(res.video_url);
      localStorage.setItem(`content-studio-video-${articleId}`, res.video_url);
    } catch (err: unknown) {
      setRenderError(
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
          (err as Error).message ??
          'Video render edilemedi.',
      );
    } finally {
      setRenderLoading(false);
    }
  };

  // ---------------------------------------------------------------------------
  // Loading / error states
  // ---------------------------------------------------------------------------

  if (generating) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <div className="text-center">
          <Loader2 className="mx-auto h-10 w-10 animate-spin text-slate-400" />
          <p className="mt-4 text-sm text-slate-500">Haber analiz ediliyor ve içerik üretiliyor…</p>
          <p className="mt-1 text-xs text-slate-400">Bu işlem 30–60 saniye sürebilir.</p>
        </div>
      </div>
    );
  }

  if (generateError || !content) {
    const msg =
      (generateError as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
      (generateError as Error | null)?.message ??
      'İçerik üretilemedi.';
    return (
      <section className="rounded-3xl border border-dashed border-red-200 bg-red-50 p-10 text-center">
        <p className="text-lg font-semibold text-red-700">İçerik üretilemedi</p>
        <p className="mt-2 text-sm text-red-500">{msg}</p>
        <Link
          to={articleId ? `/articles/${articleId}` : '/articles'}
          className="mt-6 inline-flex items-center gap-2 rounded-2xl bg-slate-950 px-4 py-3 text-sm font-semibold text-white transition hover:bg-slate-800"
        >
          <ArrowLeft className="h-4 w-4" />
          Makaleye dön
        </Link>
      </section>
    );
  }

  const videoTitle =
    remotionPayload?.videoPlan?.title ??
    remotionPayload?.headline ??
    (content.remotion_payload as { headline?: string })?.headline ??
    'Video';

  const sceneCount = remotionPayload?.videoPlan?.scenes?.length ?? 0;
  const duration = remotionPayload?.durationSeconds ?? 0;

  return (
    <div className="space-y-6">
      {/* Header */}
      <section className="rounded-[32px] bg-slate-950 px-8 py-8 text-white shadow-xl">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="max-w-3xl">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-sky-300">Content Studio</p>
            <h1 className="mt-3 text-3xl font-bold tracking-tight">{videoTitle}</h1>
            {sceneCount > 0 && (
              <p className="mt-2 text-sm text-slate-400">
                {sceneCount} sahne · {duration}s · {isVertical ? '9:16 Shorts' : '16:9'} formatı
                {generatedImageCount > 0 && (
                  <span className="ml-2 text-green-400">
                    · {generatedImageCount}/{totalScenes} görsel hazır
                  </span>
                )}
                {audioUrl && <span className="ml-2 text-green-400">· ses hazır</span>}
              </p>
            )}
          </div>
          <div className="flex items-center gap-3">
            {/* Render button */}
            <button
              onClick={handleRenderVideo}
              disabled={!canRender || renderLoading}
              className="inline-flex items-center gap-2 rounded-2xl bg-violet-600 px-5 py-3 text-sm font-semibold text-white transition hover:bg-violet-700 disabled:opacity-40"
              title={!canRender ? 'Video içeriği hazırlanıyor…' : ''}
            >
              {renderLoading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Clapperboard className="h-4 w-4" />
              )}
              {renderLoading ? 'Render ediliyor…' : 'Videoyu Render Et'}
            </button>
            <Link
              to={articleId ? `/articles/${articleId}` : '/articles'}
              className="inline-flex items-center gap-2 rounded-2xl border border-white/15 px-4 py-3 text-sm font-semibold text-white transition hover:bg-white/10"
            >
              <ArrowLeft className="h-4 w-4" />
              Makaleye dön
            </Link>
          </div>
        </div>

        {/* Render result */}
        {renderError && (
          <div className="mt-4 rounded-2xl bg-red-950/50 px-4 py-3 text-sm text-red-300">
            {renderError}
          </div>
        )}
        {renderVideoUrl && !renderLoading && (
          <div className="mt-4 flex flex-wrap items-center gap-4 rounded-2xl bg-white/5 px-4 py-3">
            <div className="flex items-center gap-2 text-sm text-green-300">
              <Clapperboard className="h-4 w-4" />
              Video hazır!
            </div>
            <video
              src={renderVideoUrl}
              controls
              className="h-20 rounded-xl"
            />
            <a
              href={renderVideoUrl}
              download="video.mp4"
              className="inline-flex items-center gap-2 rounded-2xl bg-white/10 px-4 py-2 text-sm font-semibold text-white hover:bg-white/20"
            >
              <Download className="h-4 w-4" />
              MP4 İndir
            </a>
          </div>
        )}
      </section>

      {/* Main grid: Player | Right column */}
      <div className="grid gap-6 xl:grid-cols-[auto_1fr]">

        {/* ── Left: Remotion Player ── */}
        <div className="flex flex-col items-start gap-3">
          <div className="flex items-center gap-2">
            <Video className="h-4 w-4 text-slate-400" />
            <span className="text-sm font-semibold uppercase tracking-[0.18em] text-slate-500">
              Video Önizleme
            </span>
          </div>

          {enrichedPayload ? (
            <div
              style={{
                width: isVertical ? 'min(320px, 100%)' : '560px',
                maxWidth: '100%',
                aspectRatio: isVertical ? '9 / 16' : '16 / 9',
              }}
              className="overflow-hidden rounded-[20px] shadow-lg ring-1 ring-slate-200"
            >
              <Player
                component={PromptVideo}
                inputProps={{ payload: enrichedPayload, audioUrl: audioUrl ?? undefined }}
                durationInFrames={durationInFrames}
                compositionWidth={isVertical ? 1080 : 1280}
                compositionHeight={isVertical ? 1920 : 720}
                fps={FPS}
                style={{ width: '100%', height: '100%' }}
                controls
                autoPlay={false}
              />
            </div>
          ) : (
            <div
              style={{
                width: 'min(320px, 100%)',
                aspectRatio: '9 / 16',
              }}
              className="flex flex-col items-center justify-center gap-3 rounded-[20px] bg-slate-100 shadow-inner ring-1 ring-slate-200"
            >
              <Video className="h-10 w-10 text-slate-300" />
              <p className="px-6 text-center text-xs text-slate-400">
                Video önizleme yüklenemedi. İçerik doğru formatlandığında burada görünecek.
              </p>
            </div>
          )}

          {/* Scene breakdown */}
          {remotionPayload && sceneCount > 0 && (
            <div className="w-full max-w-xs space-y-1.5">
              {remotionPayload.videoPlan?.scenes.map((scene, i) => (
                <div
                  key={scene.scene_id}
                  className="flex items-center justify-between rounded-xl bg-slate-50 px-3 py-2 text-xs"
                >
                  <span className="flex items-center gap-1.5 font-medium text-slate-600">
                    {generatedImages[i] && (
                      <span className="h-1.5 w-1.5 rounded-full bg-green-500" />
                    )}
                    {i + 1}. {scene.purpose.charAt(0).toUpperCase() + scene.purpose.slice(1)}
                  </span>
                  <span className="text-slate-400">{scene.duration_seconds}s</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* ── Right: Voiceover + Image Prompts ── */}
        <div className="space-y-5">

          {/* Voiceover panel */}
          <section className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
            <div className="flex items-center gap-2">
              <Mic className="h-4 w-4 text-slate-500" />
              <h2 className="text-sm font-semibold uppercase tracking-[0.18em] text-slate-500">Voiceover</h2>
            </div>

            <p className="mt-4 whitespace-pre-wrap text-sm leading-7 text-slate-700">
              {content.voiceover || (
                <span className="italic text-slate-400">Voiceover metni üretilemedi.</span>
              )}
            </p>

            {content.voiceover && (
              <div className="mt-5 space-y-4 border-t border-slate-100 pt-5">
                <div className="flex flex-wrap gap-3">
                  <div className="flex flex-col gap-1">
                    <label className="text-xs font-medium text-slate-500">Provider</label>
                    <select
                      value={ttsProvider}
                      onChange={(e) => {
                        setTtsProvider(e.target.value as 'elevenlabs' | 'edge_tts');
                        setSelectedVoice('');
                      }}
                      className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-400"
                    >
                      <option value="edge_tts">Edge TTS (Ücretsiz)</option>
                      <option value="elevenlabs">ElevenLabs</option>
                    </select>
                  </div>

                  {voices.length > 0 && (
                    <div className="flex flex-col gap-1">
                      <label className="text-xs font-medium text-slate-500">Ses</label>
                      <select
                        value={effectiveVoice}
                        onChange={(e) => setSelectedVoice(e.target.value)}
                        className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-400"
                      >
                        {voices.map((v) => (
                          <option key={v.id} value={v.id}>
                            {v.name}
                          </option>
                        ))}
                      </select>
                    </div>
                  )}
                </div>

                {ttsError && (
                  <p className="rounded-2xl bg-red-50 px-4 py-3 text-sm text-red-600">{ttsError}</p>
                )}

                <div className="flex flex-wrap items-center gap-3">
                  <button
                    onClick={handleGenerateVoiceover}
                    disabled={ttsLoading}
                    className="inline-flex items-center gap-2 rounded-2xl bg-slate-950 px-4 py-3 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:opacity-50"
                  >
                    {ttsLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Mic className="h-4 w-4" />}
                    {ttsLoading ? 'Üretiliyor…' : 'Ses Oluştur'}
                  </button>

                  {audioUrl && !ttsLoading && (
                    <div className="flex items-center gap-3">
                      <Volume2 className="h-4 w-4 text-green-600" />
                      <audio ref={audioRef} src={audioUrl} controls className="h-9 w-48 rounded-xl" />
                      <a
                        href={audioUrl}
                        download="voiceover.mp3"
                        className="rounded-xl bg-slate-100 px-3 py-2 text-xs font-medium text-slate-600 hover:bg-slate-200"
                      >
                        İndir
                      </a>
                    </div>
                  )}
                </div>
              </div>
            )}
          </section>

          {/* Image Prompts panel */}
          {content.image_prompts.length > 0 && (
            <section className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-sm font-semibold uppercase tracking-[0.18em] text-slate-500">
                    Görsel Promptlar ({content.image_prompts.length})
                  </h2>
                  <p className="mt-1 text-xs text-slate-400">
                    Stable Diffusion XL ile her sahne için görsel üretebilirsin. Üretilen görseller
                    doğrudan video önizlemesinde arka plan olarak görünür.
                  </p>
                </div>
                {generatedImageCount > 0 && (
                  <span className="shrink-0 rounded-full bg-green-100 px-3 py-1 text-xs font-semibold text-green-700">
                    {generatedImageCount}/{totalScenes} hazır
                  </span>
                )}
              </div>

              <div className="mt-4 space-y-4">
                {content.image_prompts.map((ip, idx) => (
                  <ImagePromptCard
                    key={`${ip.scene_id}-${idx}`}
                    prompt={ip}
                    index={idx}
                    imageUrl={generatedImages[idx] ?? null}
                    isVertical={isVertical}
                    onImageGenerated={handleImageGenerated}
                  />
                ))}
              </div>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}
