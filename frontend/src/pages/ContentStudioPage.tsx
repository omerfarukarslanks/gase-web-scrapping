import { Player } from '@remotion/player';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeft,
  ChevronDown,
  Clapperboard,
  Download,
  Loader2,
  Mic,
  RefreshCw,
  Search,
  Video,
  Volume2,
} from 'lucide-react';
import { useCallback, useEffect, useRef, useState, useMemo } from 'react';
import { Link, useLocation, useParams } from 'react-router-dom';
import { fetchArticle } from '../api/articles';
import { generateFromArticle, generateVoiceover, getTtsVoices, renderVideo } from '../api/content';
import { parseRemotionPayload } from '../lib/remotionPayload';
import { PromptVideo } from '../remotion/PromptVideo';
import type { ArticleContentResponse, TtsVoice } from '../types/content';

const FPS = 30;

// ---------------------------------------------------------------------------
// Searchable voice combobox
// ---------------------------------------------------------------------------

interface VoiceComboboxProps {
  voices: TtsVoice[];
  value: string;
  onChange: (id: string) => void;
}

function VoiceCombobox({ voices, value, onChange }: VoiceComboboxProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const selected = voices.find((v) => v.id === value) ?? voices[0];

  const filtered = useMemo(() => {
    if (!query.trim()) return voices;
    const q = query.toLowerCase();
    return voices.filter(
      (v) =>
        v.name.toLowerCase().includes(q) ||
        v.language.toLowerCase().includes(q) ||
        v.gender.toLowerCase().includes(q),
    );
  }, [voices, query]);

  // Close on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
        setQuery('');
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const handleOpen = () => {
    setOpen(true);
    setTimeout(() => inputRef.current?.focus(), 50);
  };

  const handleSelect = (id: string) => {
    onChange(id);
    setOpen(false);
    setQuery('');
  };

  return (
    <div ref={containerRef} className="relative min-w-[200px]">
      {/* Trigger */}
      <button
        type="button"
        onClick={handleOpen}
        className="flex w-full items-center justify-between gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-800 transition hover:border-slate-300 hover:bg-white focus:outline-none focus:ring-2 focus:ring-slate-400"
      >
        <span className="truncate">{selected?.name ?? 'Ses seçin'}</span>
        <ChevronDown className={`h-4 w-4 shrink-0 text-slate-400 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {/* Dropdown */}
      {open && (
        <div className="absolute left-0 top-full z-50 mt-1.5 w-full min-w-[240px] overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-lg">
          {/* Search */}
          <div className="flex items-center gap-2 border-b border-slate-100 px-3 py-2">
            <Search className="h-3.5 w-3.5 shrink-0 text-slate-400" />
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Ara… (isim, dil, cinsiyet)"
              className="w-full bg-transparent text-sm text-slate-700 placeholder-slate-400 focus:outline-none"
            />
          </div>

          {/* List */}
          <ul className="max-h-56 overflow-y-auto py-1">
            {filtered.length === 0 && (
              <li className="px-4 py-3 text-xs text-slate-400">Sonuç bulunamadı</li>
            )}
            {filtered.map((v) => (
              <li key={v.id}>
                <button
                  type="button"
                  onClick={() => handleSelect(v.id)}
                  className={`flex w-full items-center justify-between px-3 py-2 text-left text-sm transition hover:bg-slate-50 ${
                    v.id === (selected?.id ?? '') ? 'font-semibold text-slate-900' : 'text-slate-700'
                  }`}
                >
                  <span className="truncate">{v.name}</span>
                  <span className="ml-3 shrink-0 text-[10px] text-slate-400">
                    {v.language} · {v.gender}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function ContentStudioPage() {
  const { articleId } = useParams<{ articleId: string }>();
  const location = useLocation();
  const queryClient = useQueryClient();

  const preloaded = location.state as ArticleContentResponse | null;

  // TTS state
  const [ttsProvider, setTtsProvider] = useState<'elevenlabs' | 'edge_tts'>('edge_tts');
  const [selectedVoice, setSelectedVoice] = useState('');
  const [ttsLoading, setTtsLoading] = useState(false);
  const [ttsError, setTtsError] = useState<string | null>(null);

  // Actual voiceover duration (from TTS response) — overrides LLM estimate
  const [audioDuration, setAudioDuration] = useState<number | null>(null);

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
    isFetching: regenerating,
  } = useQuery<ArticleContentResponse>({
    queryKey: ['content-studio', articleId],
    queryFn: async () => {
      const article = await fetchArticle(articleId ?? '');
      return generateFromArticle(article as Record<string, unknown>);
    },
    enabled: Boolean(articleId),
    placeholderData: preloaded ?? undefined,
    staleTime: 10 * 60 * 1000,
    retry: false,
  });

  const handleRegenerate = useCallback(async () => {
    setAudioDuration(null); // yeni içerik üretilince ses süresi sıfırlansın
    await queryClient.invalidateQueries({ queryKey: ['content-studio', articleId] });
  }, [queryClient, articleId]);

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

  // TTS gerçek süresiyle sahne dağılımını refine et.
  // Backend zaten word-count tahminiyle dağıtım yaptı; burada gerçek ses süresiyle ince ayar yapıyoruz.
  const activePayload = useMemo(() => {
    if (!remotionPayload || !audioDuration || audioDuration <= 0) return remotionPayload;

    const currentTotal = remotionPayload.videoPlan?.scenes?.reduce(
      (sum: number, s: { duration_seconds: number }) => sum + s.duration_seconds,
      0,
    ) ?? 0;
    if (currentTotal <= 0) return remotionPayload;

    const scale = audioDuration / currentTotal;
    let allocated = 0;
    const scenes = remotionPayload.videoPlan!.scenes;

    const refinedScenes = scenes.map(
      (scene: { duration_seconds: number }, i: number) => {
        let duration: number;
        if (i === scenes.length - 1) {
          duration = Math.max(3, Math.round(audioDuration) - allocated);
        } else {
          duration = Math.max(3, Math.round(scene.duration_seconds * scale));
          allocated += duration;
        }
        return { ...scene, duration_seconds: duration };
      },
    );

    const newTotal = refinedScenes.reduce((s: number, sc: { duration_seconds: number }) => s + sc.duration_seconds, 0);

    return {
      ...remotionPayload,
      durationSeconds: newTotal,
      videoPlan: {
        ...remotionPayload.videoPlan,
        duration_seconds: newTotal,
        scenes: refinedScenes,
      },
    };
  }, [remotionPayload, audioDuration]);

  // Duration: activePayload zaten doğru toplam süreyi taşıyor
  const effectiveDurationSeconds = activePayload?.durationSeconds ?? 30;
  const durationInFrames = Math.max(FPS * 8, Math.ceil(effectiveDurationSeconds * FPS));

  const isVertical = activePayload?.videoPlan?.master_format === '9:16';
  const canRender = activePayload !== null;

  // --- Generate voiceover ---
  const handleGenerateVoiceover = async () => {
    if (!content?.voiceover) return;
    setTtsLoading(true);
    setTtsError(null);
    setAudioUrl(null);
    setAudioDuration(null);
    try {
      const res = await generateVoiceover(content.voiceover, ttsProvider, effectiveVoice);
      setAudioUrl(res.audio_url);
      // Gerçek ses süresini al — video uzunluğu buna senkronize olacak
      if (res.duration_seconds && res.duration_seconds > 0) {
        setAudioDuration(res.duration_seconds);
      }
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
    if (!remotionPayload) return;
    setRenderLoading(true);
    setRenderError(null);
    setRenderVideoUrl(null);
    try {
      const res = await renderVideo({
        payload: activePayload!,
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

  if (generating && !content) {
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
    activePayload?.videoPlan?.title ??
    activePayload?.headline ??
    (content.remotion_payload as { headline?: string })?.headline ??
    'Video';

  const sceneCount = activePayload?.videoPlan?.scenes?.length ?? 0;
  const llmDuration = remotionPayload?.durationSeconds ?? 0;

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
                {sceneCount} sahne · {audioDuration != null ? (
                  <>
                    <span className="text-green-400">{audioDuration}s</span>
                    <span className="ml-1 text-slate-500 line-through">{llmDuration}s</span>
                  </>
                ) : (
                  `${llmDuration}s`
                )} · {isVertical ? '9:16 Shorts' : '16:9'} formatı
                {audioUrl && <span className="ml-2 text-green-400">· ses hazır</span>}
              </p>
            )}
          </div>
          <div className="flex items-center gap-3">
            {/* Regenerate button */}
            <button
              onClick={handleRegenerate}
              disabled={regenerating || generating}
              className="inline-flex items-center gap-2 rounded-2xl border border-white/15 px-4 py-3 text-sm font-semibold text-white transition hover:bg-white/10 disabled:opacity-40"
              title="İçeriği yapay zeka ile yeniden üret"
            >
              <RefreshCw className={`h-4 w-4 ${regenerating ? 'animate-spin' : ''}`} />
              {regenerating ? 'Üretiliyor…' : 'Yeniden Üret'}
            </button>
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

          {activePayload ? (
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
                inputProps={{ payload: activePayload, audioUrl: audioUrl ?? undefined }}
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
          {activePayload && sceneCount > 0 && (
            <div className="w-full max-w-xs space-y-1.5">
              {activePayload.videoPlan?.scenes.map((scene, i) => (
                <div
                  key={scene.scene_id}
                  className="flex items-center justify-between rounded-xl bg-slate-50 px-3 py-2 text-xs"
                >
                  <span className="font-medium text-slate-600">
                    {i + 1}. {scene.purpose.charAt(0).toUpperCase() + scene.purpose.slice(1)}
                  </span>
                  <span className="text-slate-400">{scene.duration_seconds}s</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* ── Right: Voiceover ── */}
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
                  {/* Provider select */}
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

                  {/* Voice searchable combobox */}
                  {voices.length > 0 && (
                    <div className="flex flex-col gap-1">
                      <label className="text-xs font-medium text-slate-500">Ses</label>
                      <VoiceCombobox
                        voices={voices}
                        value={effectiveVoice}
                        onChange={setSelectedVoice}
                      />
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
        </div>
      </div>
    </div>
  );
}
