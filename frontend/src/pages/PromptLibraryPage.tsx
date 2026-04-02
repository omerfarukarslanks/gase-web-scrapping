import { useQuery } from '@tanstack/react-query';
import {
  ArrowRight,
  Clipboard,
  Clock3,
  Film,
  Layers3,
  RefreshCw,
  Sparkles,
} from 'lucide-react';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchTopicBriefs } from '../api/analysis';
import LoadingSpinner from '../components/common/LoadingSpinner';
import { buildRemotionPayload, saveRemotionPayload } from '../lib/remotionPayload';
import type { TopicBrief, TopicBriefFilters } from '../types/analysis';

const categoryOptions = [
  { value: '', label: 'Tum konular' },
  { value: 'world', label: 'Dunya' },
  { value: 'politics', label: 'Politika' },
  { value: 'business', label: 'Ekonomi' },
  { value: 'technology', label: 'Teknoloji' },
  { value: 'sports', label: 'Spor' },
  { value: 'entertainment', label: 'Kultur' },
  { value: 'science', label: 'Bilim' },
  { value: 'health', label: 'Saglik' },
  { value: 'opinion', label: 'Analiz' },
  { value: 'general', label: 'Genel' },
];

const sourceCategoryOptions = [
  { value: '', label: 'Tum kaynaklar' },
  { value: 'general', label: 'Genel Haber' },
  { value: 'finance', label: 'Finans' },
  { value: 'sports', label: 'Spor' },
];

async function copyText(value: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value);
  }
}

function TopicCard({
  topic,
  onCopyJson,
  onOpenPreview,
  onCopyPrompt,
}: {
  topic: TopicBrief;
  onCopyJson: (topic: TopicBrief) => void;
  onOpenPreview: (topic: TopicBrief) => void;
  onCopyPrompt: (topic: TopicBrief) => void;
}) {
  return (
    <article className="bg-white rounded-3xl border border-slate-200 p-6 shadow-sm">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-slate-600">
              {topic.category}
            </span>
            <span className="inline-flex items-center rounded-full bg-blue-50 px-3 py-1 text-xs font-semibold text-blue-700">
              {topic.source_count} kaynak
            </span>
            <span className="inline-flex items-center rounded-full bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700">
              guven {(topic.confidence * 100).toFixed(0)}%
            </span>
          </div>

          <div>
            <h3 className="text-2xl font-bold tracking-tight text-slate-900">{topic.headline_tr}</h3>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">{topic.summary_tr}</p>
          </div>

          <div className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
            <div className="rounded-2xl bg-slate-50 p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">One cikan noktalar</p>
              <ul className="mt-3 space-y-2 text-sm text-slate-700">
                {topic.key_points_tr.map((point) => (
                  <li key={point} className="flex gap-2">
                    <span className="mt-1 h-1.5 w-1.5 rounded-full bg-blue-600" />
                    <span>{point}</span>
                  </li>
                ))}
              </ul>
            </div>

            <div className="rounded-2xl bg-slate-950 p-4 text-slate-100">
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Video Plan</p>
              {topic.visual_assets[0] ? (
                <div className="mt-3 overflow-hidden rounded-2xl border border-white/10">
                  <img
                    src={topic.visual_assets[0].url}
                    alt={topic.visual_assets[0].alt_text}
                    className="h-32 w-full object-cover"
                  />
                </div>
              ) : null}
              <p className="mt-3 text-lg font-bold text-white">{topic.video_plan.title}</p>
              <div className="mt-3 grid grid-cols-2 gap-3 text-xs text-slate-300">
                <div className="rounded-2xl border border-white/10 bg-white/5 px-3 py-3">
                  <p className="uppercase tracking-[0.18em] text-slate-500">Duration</p>
                  <p className="mt-2 text-base font-semibold text-white">{topic.video_plan.duration_seconds}s</p>
                </div>
                <div className="rounded-2xl border border-white/10 bg-white/5 px-3 py-3">
                  <p className="uppercase tracking-[0.18em] text-slate-500">Scenes</p>
                  <p className="mt-2 text-base font-semibold text-white">{topic.video_plan.scenes.length}</p>
                </div>
                <div className="rounded-2xl border border-white/10 bg-white/5 px-3 py-3">
                  <p className="uppercase tracking-[0.18em] text-slate-500">Pacing</p>
                  <p className="mt-2 text-base font-semibold text-white">{topic.video_plan.pacing_hint}</p>
                </div>
                <div className="rounded-2xl border border-white/10 bg-white/5 px-3 py-3">
                  <p className="uppercase tracking-[0.18em] text-slate-500">Sources</p>
                  <p className="mt-2 text-base font-semibold text-white">{topic.video_plan.source_visibility}</p>
                </div>
              </div>
              <div className="mt-4 space-y-2">
                {topic.video_plan.scenes.slice(0, 2).map((scene) => (
                  <div key={scene.scene_id} className="rounded-2xl border border-white/10 bg-white/5 px-3 py-3">
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">
                        {scene.purpose}
                      </p>
                      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">
                        {scene.layout_hint} · {scene.duration_seconds}s
                      </p>
                    </div>
                    <p className="mt-2 text-sm font-semibold text-white">{scene.headline}</p>
                    {scene.body ? <p className="mt-1 text-sm leading-6 text-slate-300">{scene.body}</p> : null}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        <div className="flex shrink-0 flex-col gap-3 lg:w-56">
          <button
            onClick={() => onOpenPreview(topic)}
            className="inline-flex items-center justify-center gap-2 rounded-2xl bg-blue-600 px-4 py-3 text-sm font-semibold text-white transition hover:bg-blue-700"
          >
            <Film className="h-4 w-4" />
            Remotion'da Ac
          </button>
          <button
            onClick={() => onCopyJson(topic)}
            className="inline-flex items-center justify-center gap-2 rounded-2xl border border-slate-200 px-4 py-3 text-sm font-semibold text-slate-700 transition hover:bg-slate-50"
          >
            <Clipboard className="h-4 w-4" />
            JSON Kopyala
          </button>
          <button
            onClick={() => onCopyPrompt(topic)}
            className="inline-flex items-center justify-center gap-2 rounded-2xl border border-slate-200 px-4 py-3 text-sm font-semibold text-slate-700 transition hover:bg-slate-50"
          >
            <Sparkles className="h-4 w-4" />
            Human Prompt Kopyala
          </button>
        </div>
      </div>

      <div className="mt-5 flex flex-wrap items-center gap-3 border-t border-slate-100 pt-4 text-xs text-slate-500">
        <span>{topic.article_count} haber birlestirildi</span>
        <span className="h-1 w-1 rounded-full bg-slate-300" />
        <span>{topic.sources.join(', ')}</span>
      </div>
    </article>
  );
}

export default function PromptLibraryPage() {
  const navigate = useNavigate();
  const [filters, setFilters] = useState<TopicBriefFilters>({
    hours: 3,
    limit_topics: 12,
  });
  const [message, setMessage] = useState<string | null>(null);

  const { data, isLoading, isFetching, refetch } = useQuery({
    queryKey: ['topic-briefs', filters],
    queryFn: () => fetchTopicBriefs(filters),
  });

  const handleCopyJson = async (topic: TopicBrief) => {
    const payload = buildRemotionPayload(topic);
    await copyText(JSON.stringify(payload, null, 2));
    setMessage('JSON payload panoya kopyalandi.');
  };

  const handleCopyPrompt = async (topic: TopicBrief) => {
    await copyText(topic.video_prompt_en);
    setMessage('Video prompt panoya kopyalandi.');
  };

  const handleOpenPreview = (topic: TopicBrief) => {
    saveRemotionPayload(buildRemotionPayload(topic));
    navigate('/video-preview');
  };

  if (isLoading && !data) return <LoadingSpinner />;

  return (
    <div className="space-y-8">
      <section className="rounded-[32px] bg-slate-950 px-8 py-10 text-white shadow-xl">
        <div className="flex flex-col gap-8 xl:flex-row xl:items-end xl:justify-between">
          <div className="max-w-3xl">
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-sky-300">Prompt Library</p>
            <h2 className="mt-3 text-4xl font-bold tracking-tight">Uretilen video promptlarini tek ekranda incele</h2>
            <p className="mt-4 text-sm leading-7 text-slate-300">
              Analiz endpoint'i artik iki asamali calisir: once insan okunur guclu bir video promptu uretilir, sonra
              ayri bir storyboard servisi bunu Remotion icin cizilebilir JSON'a donusturur.
            </p>
          </div>

          <div className="grid gap-3 sm:grid-cols-3">
            <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
              <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Durum</p>
              <p className="mt-2 text-2xl font-semibold">{data?.analysis_status ?? '-'}</p>
            </div>
            <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
              <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Pencere</p>
              <p className="mt-2 text-2xl font-semibold">{filters.hours}s</p>
            </div>
            <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
              <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Gruplar</p>
              <p className="mt-2 text-2xl font-semibold">{data?.groups.length ?? 0}</p>
            </div>
          </div>
        </div>
      </section>

      <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
          <div className="grid gap-4 md:grid-cols-4">
            <label className="block">
              <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Saat</span>
              <input
                type="number"
                min={1}
                max={168}
                value={filters.hours ?? 3}
                onChange={(event) =>
                  setFilters((current) => ({ ...current, hours: Math.max(1, Number(event.target.value) || 1) }))
                }
                className="w-full rounded-2xl border border-slate-200 px-4 py-3 text-sm outline-none transition focus:border-blue-500"
              />
            </label>

            <label className="block">
              <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Kaynak tipi</span>
              <select
                value={filters.source_category ?? ''}
                onChange={(event) => setFilters((current) => ({ ...current, source_category: event.target.value || undefined }))}
                className="w-full rounded-2xl border border-slate-200 px-4 py-3 text-sm outline-none transition focus:border-blue-500"
              >
                {sourceCategoryOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>

            <label className="block">
              <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Konu</span>
              <select
                value={filters.category ?? ''}
                onChange={(event) => setFilters((current) => ({ ...current, category: event.target.value || undefined }))}
                className="w-full rounded-2xl border border-slate-200 px-4 py-3 text-sm outline-none transition focus:border-blue-500"
              >
                {categoryOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>

            <label className="block">
              <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Limit</span>
              <input
                type="number"
                min={1}
                max={24}
                value={filters.limit_topics ?? 12}
                onChange={(event) =>
                  setFilters((current) => ({
                    ...current,
                    limit_topics: Math.max(1, Math.min(24, Number(event.target.value) || 1)),
                  }))
                }
                className="w-full rounded-2xl border border-slate-200 px-4 py-3 text-sm outline-none transition focus:border-blue-500"
              />
            </label>
          </div>

          <button
            onClick={() => refetch()}
            className="inline-flex items-center justify-center gap-2 rounded-2xl bg-slate-950 px-4 py-3 text-sm font-semibold text-white transition hover:bg-slate-800"
          >
            <RefreshCw className={`h-4 w-4 ${isFetching ? 'animate-spin' : ''}`} />
            Yenile
          </button>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-4 text-xs text-slate-500">
          <span className="inline-flex items-center gap-2">
            <Clock3 className="h-4 w-4" />
            {data ? `${new Date(data.window_start).toLocaleString('tr-TR')} - ${new Date(data.window_end).toLocaleString('tr-TR')}` : 'Pencere bekleniyor'}
          </span>
          {message ? <span className="rounded-full bg-emerald-50 px-3 py-1 text-emerald-700">{message}</span> : null}
        </div>
      </section>

      {!data || data.groups.length === 0 ? (
        <section className="rounded-3xl border border-dashed border-slate-300 bg-white p-10 text-center">
          <Layers3 className="mx-auto h-10 w-10 text-slate-400" />
          <h3 className="mt-4 text-xl font-semibold text-slate-900">Bu filtrelerle prompt bulunamadi</h3>
          <p className="mt-2 text-sm leading-6 text-slate-500">
            Saat penceresini buyut veya kaynak tipini degistir. En pratik deneme icin `hours=3` ya da `hours=6`
            kullanabilirsin.
          </p>
        </section>
      ) : (
        data.groups.map((group) => (
          <section key={group.category} className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">{group.category}</p>
                <h3 className="text-2xl font-bold tracking-tight text-slate-900">{group.topics.length} prompt</h3>
              </div>
              <button
                onClick={() => navigate('/video-preview')}
                className="inline-flex items-center gap-2 text-sm font-semibold text-blue-700 transition hover:text-blue-900"
              >
                Preview sayfasina git
                <ArrowRight className="h-4 w-4" />
              </button>
            </div>

            <div className="space-y-4">
              {group.topics.map((topic) => (
                <TopicCard
                  key={topic.topic_id}
                  topic={topic}
                  onCopyJson={handleCopyJson}
                  onCopyPrompt={handleCopyPrompt}
                  onOpenPreview={handleOpenPreview}
                />
              ))}
            </div>
          </section>
        ))
      )}
    </div>
  );
}
