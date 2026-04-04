import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ArrowRight,
  Clipboard,
  Clock3,
  Film,
  Layers3,
  RefreshCw,
  Sparkles,
} from 'lucide-react';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { deleteTopicFeedback, fetchTopicBriefs, saveTopicFeedback } from '../api/analysis';
import LoadingSpinner from '../components/common/LoadingSpinner';
import { buildRemotionPayload, saveRemotionPayload } from '../lib/remotionPayload';
import type {
  FeedbackLabel,
  TopicBrief,
  TopicBriefFilters,
  TopicBriefsResponse,
  TopicFeedbackSnapshotInput,
  TopicLatestFeedback,
} from '../types/analysis';

const categoryLabels: Record<string, string> = {
  world: 'Dunya',
  politics: 'Politika',
  business: 'Is',
  economy: 'Ekonomi',
  technology: 'Teknoloji',
  sports: 'Spor',
  culture: 'Kultur',
  arts: 'Sanat',
  science: 'Bilim',
  environment: 'Cevre',
  health: 'Saglik',
  opinion: 'Kose',
  analysis: 'Analiz',
  general: 'Genel',
};

function labelCategory(value: string): string {
  return categoryLabels[value] ?? value;
}

function labelStrategyValue(value: string): string {
  return value
    .split('_')
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

function plannerStatusClass(value: string): string {
  switch (value) {
    case 'produce':
      return 'bg-emerald-50 text-emerald-700';
    case 'review':
      return 'bg-amber-50 text-amber-700';
    case 'carousel_only':
      return 'bg-indigo-50 text-indigo-700';
    case 'skip':
      return 'bg-rose-50 text-rose-700';
    default:
      return 'bg-slate-100 text-slate-700';
  }
}

const categoryOptions = [
  { value: '', label: 'Tum konular' },
  { value: 'world', label: 'Dunya' },
  { value: 'politics', label: 'Politika' },
  { value: 'business', label: 'Is' },
  { value: 'economy', label: 'Ekonomi' },
  { value: 'technology', label: 'Teknoloji' },
  { value: 'sports', label: 'Spor' },
  { value: 'culture', label: 'Kultur' },
  { value: 'arts', label: 'Sanat' },
  { value: 'science', label: 'Bilim' },
  { value: 'environment', label: 'Cevre' },
  { value: 'health', label: 'Saglik' },
  { value: 'opinion', label: 'Kose' },
  { value: 'analysis', label: 'Analiz' },
  { value: 'general', label: 'Genel' },
];

const sourceCategoryOptions = [
  { value: '', label: 'Tum kaynaklar' },
  { value: 'general', label: 'Genel Haber' },
  { value: 'finance', label: 'Finans' },
  { value: 'sports', label: 'Spor' },
];

const feedbackOptions: Array<{
  value: FeedbackLabel;
  label: string;
  className: string;
}> = [
  { value: 'approved', label: 'Approved', className: 'bg-emerald-600 hover:bg-emerald-700 text-white' },
  { value: 'wrong', label: 'Wrong', className: 'bg-rose-600 hover:bg-rose-700 text-white' },
  { value: 'boring', label: 'Boring', className: 'bg-amber-500 hover:bg-amber-600 text-white' },
  { value: 'malformed', label: 'Malformed', className: 'bg-slate-700 hover:bg-slate-800 text-white' },
];

async function copyText(value: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value);
  }
}

function buildTopicFeedbackSnapshot(topic: TopicBrief): TopicFeedbackSnapshotInput {
  return {
    headline_tr: topic.headline_tr,
    summary_tr: topic.summary_tr,
    category: topic.category,
    aggregation_type: topic.aggregation_type,
    quality_status: topic.quality_status,
    quality_score: topic.quality_score,
    video_quality_status: topic.video_quality_status,
    video_quality_score: topic.video_quality_score,
    source_count: topic.source_count,
    article_count: topic.article_count,
    sources: topic.sources,
    source_slugs: topic.representative_articles
      .map((article) => article.source_slug)
      .filter((value): value is string => Boolean(value)),
    review_reasons: topic.review_reasons,
    video_review_reasons: topic.video_review_reasons,
    representative_article_ids: topic.representative_articles.map((article) => article.id),
    has_visual_asset: topic.visual_assets.length > 0,
    has_published_at: topic.representative_articles.some((article) => Boolean(article.published_at)),
  };
}

function updateTopicFeedbackInResponse(
  response: TopicBriefsResponse | undefined,
  topicId: string,
  latestFeedback: TopicLatestFeedback | null
): TopicBriefsResponse | undefined {
  if (!response) return response;
  return {
    ...response,
    groups: response.groups.map((group) => ({
      ...group,
      topics: group.topics.map((topic) =>
        topic.topic_id === topicId
          ? {
              ...topic,
              latest_feedback: latestFeedback,
            }
          : topic
      ),
    })),
  };
}

function TopicCard({
  topic,
  moderationMode,
  onCopyJson,
  onCopyVerticalOutput,
  onCopyCarouselOutput,
  onOpenPreview,
  onCopyPrompt,
  onSaveFeedback,
  onDeleteFeedback,
  feedbackPending,
  deletePending,
}: {
  topic: TopicBrief;
  moderationMode: boolean;
  onCopyJson: (topic: TopicBrief) => void;
  onCopyVerticalOutput: (topic: TopicBrief) => void;
  onCopyCarouselOutput: (topic: TopicBrief) => void;
  onOpenPreview: (topic: TopicBrief) => void;
  onCopyPrompt: (topic: TopicBrief) => void;
  onSaveFeedback: (topic: TopicBrief, label: FeedbackLabel, note: string | null) => void;
  onDeleteFeedback: (topicId: string) => void;
  feedbackPending: boolean;
  deletePending: boolean;
}) {
  const [note, setNote] = useState(topic.latest_feedback?.note ?? '');
  const secondaryCategories = topic.secondary_categories.map((category) => labelCategory(category));
  const strategy = topic.strategy;
  const planningDecision = topic.planning_decision;
  const storyFactPack = topic.story_fact_pack;
  const outputBlueprint = topic.output_blueprint;
  const plannerVerticalCount = outputBlueprint?.vertical_video?.scene_blueprints.length ?? 0;
  const plannerCarouselCount = outputBlueprint?.carousel?.slide_goals.length ?? 0;
  const plannerRiskFlags = planningDecision?.risk_flags ?? [];
  const plannerStatusLabel = planningDecision ? labelStrategyValue(planningDecision.status) : null;

  useEffect(() => {
    setNote(topic.latest_feedback?.note ?? '');
  }, [topic.latest_feedback?.label, topic.latest_feedback?.note, topic.latest_feedback?.updated_at]);

  return (
    <article className="bg-white rounded-3xl border border-slate-200 p-6 shadow-sm">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-slate-600">
              {labelCategory(topic.category)}
            </span>
            {secondaryCategories.map((category) => (
              <span
                key={category}
                className="inline-flex items-center rounded-full bg-slate-50 px-3 py-1 text-xs font-semibold text-slate-600"
              >
                {category}
              </span>
            ))}
            <span className="inline-flex items-center rounded-full bg-blue-50 px-3 py-1 text-xs font-semibold text-blue-700">
              {topic.source_count} kaynak
            </span>
            <span className="inline-flex items-center rounded-full bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700">
              guven {(topic.confidence * 100).toFixed(0)}%
            </span>
            <span className="inline-flex items-center rounded-full bg-fuchsia-50 px-3 py-1 text-xs font-semibold text-fuchsia-700">
              {labelStrategyValue(strategy.strategy_domain)}
            </span>
            <span className="inline-flex items-center rounded-full bg-indigo-50 px-3 py-1 text-xs font-semibold text-indigo-700">
              {labelStrategyValue(strategy.primary_output)}
            </span>
            {planningDecision ? (
              <span
                className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold ${plannerStatusClass(planningDecision.status)}`}
              >
                planner {plannerStatusLabel}
              </span>
            ) : null}
            {planningDecision ? (
              <span className="inline-flex items-center rounded-full bg-violet-50 px-3 py-1 text-xs font-semibold text-violet-700">
                {labelStrategyValue(planningDecision.story_family)}
              </span>
            ) : null}
            {planningDecision ? (
              <span className="inline-flex items-center rounded-full bg-sky-50 px-3 py-1 text-xs font-semibold text-sky-700">
                {labelStrategyValue(planningDecision.layout_family)}
              </span>
            ) : null}
            <span className="inline-flex items-center rounded-full bg-cyan-50 px-3 py-1 text-xs font-semibold text-cyan-700">
              izleyici dili {strategy.viewer_language}
            </span>
            {strategy.human_review_required ? (
              <span className="inline-flex items-center rounded-full bg-amber-50 px-3 py-1 text-xs font-semibold text-amber-700">
                review gerekli
              </span>
            ) : (
              <span className="inline-flex items-center rounded-full bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700">
                publishable akisi
              </span>
            )}
            {moderationMode ? (
              <>
                <span className="inline-flex items-center rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-700">
                  dil {topic.story_language}
                </span>
                <span className="inline-flex items-center rounded-full bg-cyan-50 px-3 py-1 text-xs font-semibold text-cyan-700">
                  {topic.editorial_type}
                </span>
              </>
            ) : null}
            {moderationMode ? (
              <>
                <span
                  className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold ${
                    topic.quality_status === 'publishable'
                      ? 'bg-emerald-50 text-emerald-700'
                      : 'bg-amber-50 text-amber-700'
                  }`}
                >
                  {topic.quality_status}
                </span>
                <span className="inline-flex items-center rounded-full bg-violet-50 px-3 py-1 text-xs font-semibold text-violet-700">
                  skor {topic.quality_score.toFixed(3)}
                </span>
                <span
                  className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold ${
                    topic.video_quality_status === 'publishable'
                      ? 'bg-emerald-50 text-emerald-700'
                      : topic.video_quality_status === 'review'
                        ? 'bg-amber-50 text-amber-700'
                        : 'bg-rose-50 text-rose-700'
                  }`}
                >
                  video {topic.video_quality_status}
                </span>
                <span className="inline-flex items-center rounded-full bg-fuchsia-50 px-3 py-1 text-xs font-semibold text-fuchsia-700">
                  video skor {topic.video_quality_score}
                </span>
              </>
            ) : null}
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
                  <p className="uppercase tracking-[0.18em] text-slate-500">Format</p>
                  <p className="mt-2 text-base font-semibold text-white">{topic.video_plan.master_format}</p>
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
              {planningDecision || outputBlueprint ? (
                <div className="mt-4 rounded-2xl border border-white/10 bg-white/5 px-3 py-3">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">Planner</p>
                  <div className="mt-3 grid grid-cols-2 gap-3 text-xs text-slate-300">
                    <div className="rounded-2xl border border-white/10 bg-white/5 px-3 py-3">
                      <p className="uppercase tracking-[0.18em] text-slate-500">Status</p>
                      <p className="mt-2 text-sm font-semibold text-white">
                        {planningDecision ? labelStrategyValue(planningDecision.status) : '-'}
                      </p>
                    </div>
                    <div className="rounded-2xl border border-white/10 bg-white/5 px-3 py-3">
                      <p className="uppercase tracking-[0.18em] text-slate-500">Family</p>
                      <p className="mt-2 text-sm font-semibold text-white">
                        {planningDecision ? labelStrategyValue(planningDecision.story_family) : '-'}
                      </p>
                    </div>
                    <div className="rounded-2xl border border-white/10 bg-white/5 px-3 py-3">
                      <p className="uppercase tracking-[0.18em] text-slate-500">Vertical BP</p>
                      <p className="mt-2 text-sm font-semibold text-white">{plannerVerticalCount}</p>
                    </div>
                    <div className="rounded-2xl border border-white/10 bg-white/5 px-3 py-3">
                      <p className="uppercase tracking-[0.18em] text-slate-500">Carousel BP</p>
                      <p className="mt-2 text-sm font-semibold text-white">{plannerCarouselCount}</p>
                    </div>
                  </div>
                </div>
              ) : null}
            </div>
          </div>

          {planningDecision || storyFactPack || outputBlueprint ? (
            <div className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
              <div className="rounded-2xl border border-slate-200 bg-white p-4">
                <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">Planning Decision</p>
                {planningDecision ? (
                  <>
                    <div className="mt-3 flex flex-wrap gap-2">
                      <span
                        className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold ${plannerStatusClass(planningDecision.status)}`}
                      >
                        {labelStrategyValue(planningDecision.status)}
                      </span>
                      <span className="inline-flex items-center rounded-full bg-violet-50 px-3 py-1 text-xs font-semibold text-violet-700">
                        {labelStrategyValue(planningDecision.story_family)}
                      </span>
                      <span className="inline-flex items-center rounded-full bg-sky-50 px-3 py-1 text-xs font-semibold text-sky-700">
                        {labelStrategyValue(planningDecision.layout_family)}
                      </span>
                      <span className="inline-flex items-center rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-700">
                        {planningDecision.scene_count} scene
                      </span>
                    </div>
                    {plannerRiskFlags.length > 0 ? (
                      <div className="mt-3 flex flex-wrap gap-2">
                        {plannerRiskFlags.map((flag) => (
                          <span
                            key={flag}
                            className="inline-flex items-center rounded-full bg-rose-50 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-rose-700"
                          >
                            {labelStrategyValue(flag)}
                          </span>
                        ))}
                      </div>
                    ) : null}
                    {planningDecision.reason ? (
                      <p className="mt-4 text-sm leading-6 text-slate-600">{planningDecision.reason}</p>
                    ) : null}
                  </>
                ) : (
                  <p className="mt-3 text-sm text-slate-500">Planner karari bulunmuyor.</p>
                )}

                {storyFactPack ? (
                  <div className="mt-4 grid gap-3 md:grid-cols-3">
                    <div className="rounded-2xl bg-slate-50 px-4 py-3">
                      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Core event</p>
                      <p className="mt-2 text-sm font-semibold text-slate-900">{storyFactPack.core_event}</p>
                    </div>
                    <div className="rounded-2xl bg-slate-50 px-4 py-3">
                      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">What changed</p>
                      <p className="mt-2 text-sm leading-6 text-slate-700">{storyFactPack.what_changed}</p>
                    </div>
                    <div className="rounded-2xl bg-slate-50 px-4 py-3">
                      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Why now</p>
                      <p className="mt-2 text-sm leading-6 text-slate-700">{storyFactPack.why_now || '-'}</p>
                    </div>
                  </div>
                ) : null}
              </div>

              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">Output Blueprint</p>
                <div className="mt-3 grid grid-cols-2 gap-3">
                  <div className="rounded-2xl bg-white px-4 py-3">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Vertical scenes</p>
                    <p className="mt-2 text-lg font-semibold text-slate-900">{plannerVerticalCount}</p>
                  </div>
                  <div className="rounded-2xl bg-white px-4 py-3">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Carousel slides</p>
                    <p className="mt-2 text-lg font-semibold text-slate-900">
                      {outputBlueprint?.carousel?.slide_count ?? plannerCarouselCount}
                    </p>
                  </div>
                </div>
                {outputBlueprint?.vertical_video?.scene_blueprints.length ? (
                  <div className="mt-4 space-y-2">
                    {outputBlueprint.vertical_video.scene_blueprints.slice(0, 3).map((scene, index) => (
                      <div key={`${scene.goal}-${index}`} className="rounded-2xl bg-white px-4 py-3">
                        <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">
                          {labelStrategyValue(scene.goal)} · {labelStrategyValue(scene.visual_type)}
                        </p>
                        <p className="mt-2 text-sm font-medium text-slate-900">
                          {scene.must_include.join(' · ') || 'Must include yok'}
                        </p>
                        <p className="mt-1 text-xs uppercase tracking-[0.14em] text-slate-500">
                          {labelStrategyValue(scene.safe_voice_rule)}
                        </p>
                      </div>
                    ))}
                  </div>
                ) : null}
                {outputBlueprint?.carousel?.slide_goals.length ? (
                  <div className="mt-4 rounded-2xl bg-white px-4 py-3">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Carousel goals</p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {outputBlueprint.carousel.slide_goals.slice(0, 4).map((goal) => (
                        <span
                          key={goal}
                          className="inline-flex items-center rounded-full bg-indigo-50 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-indigo-700"
                        >
                          {goal}
                        </span>
                      ))}
                    </div>
                  </div>
                ) : null}
              </div>
            </div>
          ) : null}

          {moderationMode ? (
            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Moderation</p>
                  <p className="mt-2 text-sm font-medium text-slate-700">
                    Editorial type: <span className="font-semibold text-slate-900">{topic.editorial_type}</span>
                  </p>
                  <p className="mt-2 text-sm font-medium text-slate-700">
                    Story language: <span className="font-semibold text-slate-900">{topic.story_language}</span>
                  </p>
                  <p className="mt-2 text-sm font-medium text-slate-700">
                    Status: <span className="font-semibold text-slate-900">{topic.quality_status}</span>
                  </p>
                  <p className="mt-2 text-sm font-medium text-slate-700">
                    Video: <span className="font-semibold text-slate-900">{topic.video_quality_status}</span>
                  </p>
                  {topic.review_reasons.length > 0 ? (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {topic.review_reasons.map((reason) => (
                        <span
                          key={reason}
                          className="inline-flex items-center rounded-full bg-amber-100 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-amber-800"
                        >
                          {reason}
                        </span>
                      ))}
                    </div>
                  ) : (
                    <p className="mt-3 text-xs text-slate-500">Bu topic icin aktif review reason yok.</p>
                  )}
                  {topic.video_review_reasons.length > 0 ? (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {topic.video_review_reasons.map((reason) => (
                        <span
                          key={reason}
                          className="inline-flex items-center rounded-full bg-rose-100 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-rose-800"
                        >
                          video:{reason}
                        </span>
                      ))}
                    </div>
                  ) : (
                    <p className="mt-3 text-xs text-slate-500">Bu topic icin aktif video review reason yok.</p>
                  )}
                  {topic.planning_debug ? (
                    <div className="mt-4 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-xs text-slate-600">
                      <p className="font-semibold uppercase tracking-[0.14em] text-slate-500">Planning debug</p>
                      <p className="mt-2 text-sm font-medium text-slate-700">
                        Primary angle:{' '}
                        <span className="font-semibold text-slate-900">{topic.planning_debug.primary_angle_type}</span>
                      </p>
                      {topic.planning_debug.alternate_angle_type ? (
                        <p className="mt-2 text-sm font-medium text-slate-700">
                          Alternate angle:{' '}
                          <span className="font-semibold text-slate-900">{topic.planning_debug.alternate_angle_type}</span>
                        </p>
                      ) : null}
                      {topic.planning_debug.alternate_video_plan_summary ? (
                        <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
                          {topic.planning_debug.alternate_video_plan_summary}
                        </p>
                      ) : null}
                      {topic.planning_debug.angle_scores.length > 0 ? (
                        <div className="mt-3 flex flex-wrap gap-2">
                          {topic.planning_debug.angle_scores.map((score) => (
                            <span
                              key={`${score.angle_type}-${score.quality_status}`}
                              className="inline-flex items-center rounded-full bg-blue-50 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-blue-800"
                            >
                              {score.angle_type} · {score.quality_status} · {score.quality_score}
                            </span>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                </div>

                {topic.latest_feedback ? (
                  <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-xs text-slate-600">
                    <p className="font-semibold uppercase tracking-[0.14em] text-slate-500">Latest feedback</p>
                    <p className="mt-2 text-sm font-semibold text-slate-900">{topic.latest_feedback.label}</p>
                    <p className="mt-1">{new Date(topic.latest_feedback.updated_at).toLocaleString('tr-TR')}</p>
                    {topic.latest_feedback.note ? (
                      <p className="mt-2 max-w-xs text-sm leading-6 text-slate-700">{topic.latest_feedback.note}</p>
                    ) : null}
                  </div>
                ) : (
                  <div className="rounded-2xl border border-dashed border-slate-300 px-4 py-3 text-xs text-slate-500">
                    Bu topic icin feedback yok.
                  </div>
                )}
              </div>

              <div className="mt-4">
                <label className="block text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
                  Kisa not
                </label>
                <textarea
                  value={note}
                  onChange={(event) => setNote(event.target.value)}
                  placeholder="Neden approved, wrong, boring ya da malformed?"
                  disabled={feedbackPending || deletePending}
                  className="mt-2 min-h-24 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm leading-6 text-slate-700 outline-none transition focus:border-blue-500 disabled:cursor-not-allowed disabled:bg-slate-100"
                />
              </div>

              <div className="mt-4 flex flex-wrap gap-2">
                {feedbackOptions.map((option) => (
                  <button
                    key={option.value}
                    type="button"
                    disabled={feedbackPending || deletePending}
                    onClick={() => onSaveFeedback(topic, option.value, note.trim() || null)}
                    className={`inline-flex items-center justify-center rounded-2xl px-4 py-2 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-60 ${option.className}`}
                  >
                    {option.label}
                  </button>
                ))}
                {topic.latest_feedback ? (
                  <button
                    type="button"
                    disabled={feedbackPending || deletePending}
                    onClick={() => onDeleteFeedback(topic.topic_id)}
                    className="inline-flex items-center justify-center rounded-2xl border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {deletePending ? 'Temizleniyor...' : 'Feedback temizle'}
                  </button>
                ) : null}
              </div>
            </div>
          ) : null}
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
            onClick={() => onCopyVerticalOutput(topic)}
            className="inline-flex items-center justify-center gap-2 rounded-2xl border border-slate-200 px-4 py-3 text-sm font-semibold text-slate-700 transition hover:bg-slate-50"
          >
            <Clipboard className="h-4 w-4" />
            Vertical Kopyala
          </button>
          <button
            onClick={() => onCopyCarouselOutput(topic)}
            className="inline-flex items-center justify-center gap-2 rounded-2xl border border-slate-200 px-4 py-3 text-sm font-semibold text-slate-700 transition hover:bg-slate-50"
          >
            <Clipboard className="h-4 w-4" />
            Carousel Kopyala
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
  const queryClient = useQueryClient();
  const [filters, setFilters] = useState<TopicBriefFilters>({
    hours: 3,
    limit_topics: 12,
  });
  const [moderationMode, setModerationMode] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const effectiveFilters: TopicBriefFilters = moderationMode
    ? { ...filters, include_review: true, debug: true }
    : { ...filters, include_review: undefined, debug: undefined };

  const { data, isLoading, isFetching, refetch } = useQuery({
    queryKey: ['topic-briefs', effectiveFilters],
    queryFn: () => fetchTopicBriefs(effectiveFilters),
  });

  const saveFeedbackMutation = useMutation({
    mutationFn: saveTopicFeedback,
    onMutate: async (payload) => {
      await queryClient.cancelQueries({ queryKey: ['topic-briefs'] });
      const previous = queryClient.getQueriesData<TopicBriefsResponse>({ queryKey: ['topic-briefs'] });
      const optimisticFeedback: TopicLatestFeedback = {
        label: payload.feedback_label,
        note: payload.note ?? null,
        updated_at: new Date().toISOString(),
      };
      queryClient.setQueriesData<TopicBriefsResponse>({ queryKey: ['topic-briefs'] }, (current) =>
        updateTopicFeedbackInResponse(current, payload.topic_id, optimisticFeedback)
      );
      return { previous };
    },
    onError: (_error, _payload, context) => {
      context?.previous.forEach(([queryKey, queryData]) => {
        queryClient.setQueryData(queryKey, queryData);
      });
      setMessage('Feedback kaydedilemedi.');
    },
    onSuccess: (response) => {
      queryClient.setQueriesData<TopicBriefsResponse>({ queryKey: ['topic-briefs'] }, (current) =>
        updateTopicFeedbackInResponse(current, response.topic_id, response.latest_feedback)
      );
      setMessage('Feedback kaydedildi.');
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ['topic-briefs'] });
    },
  });

  const deleteFeedbackMutation = useMutation({
    mutationFn: deleteTopicFeedback,
    onMutate: async (topicId) => {
      await queryClient.cancelQueries({ queryKey: ['topic-briefs'] });
      const previous = queryClient.getQueriesData<TopicBriefsResponse>({ queryKey: ['topic-briefs'] });
      queryClient.setQueriesData<TopicBriefsResponse>({ queryKey: ['topic-briefs'] }, (current) =>
        updateTopicFeedbackInResponse(current, topicId, null)
      );
      return { previous };
    },
    onError: (_error, _topicId, context) => {
      context?.previous.forEach(([queryKey, queryData]) => {
        queryClient.setQueryData(queryKey, queryData);
      });
      setMessage('Feedback temizlenemedi.');
    },
    onSuccess: () => {
      setMessage('Feedback temizlendi.');
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ['topic-briefs'] });
    },
  });

  const handleCopyJson = async (topic: TopicBrief) => {
    const payload = buildRemotionPayload(topic);
    await copyText(JSON.stringify(payload, null, 2));
    setMessage('JSON payload panoya kopyalandi.');
  };

  const handleCopyVerticalOutput = async (topic: TopicBrief) => {
    if (!topic.platform_outputs.vertical_video) {
      setMessage('Bu topic icin vertical output hazir degil.');
      return;
    }
    await copyText(JSON.stringify(topic.platform_outputs.vertical_video, null, 2));
    setMessage('Vertical video output panoya kopyalandi.');
  };

  const handleCopyCarouselOutput = async (topic: TopicBrief) => {
    if (!topic.platform_outputs.carousel) {
      setMessage('Bu topic icin carousel output hazir degil.');
      return;
    }
    await copyText(JSON.stringify(topic.platform_outputs.carousel, null, 2));
    setMessage('Carousel output panoya kopyalandi.');
  };

  const handleCopyPrompt = async (topic: TopicBrief) => {
    await copyText(topic.video_prompt_en);
    setMessage('Video prompt panoya kopyalandi.');
  };

  const handleOpenPreview = (topic: TopicBrief) => {
    saveRemotionPayload(buildRemotionPayload(topic));
    navigate('/video-preview');
  };

  const handleSaveFeedback = (topic: TopicBrief, feedbackLabel: FeedbackLabel, note: string | null) => {
    saveFeedbackMutation.mutate({
      topic_id: topic.topic_id,
      feedback_label: feedbackLabel,
      note,
      topic_snapshot: buildTopicFeedbackSnapshot(topic),
    });
  };

  const handleDeleteFeedback = (topicId: string) => {
    deleteFeedbackMutation.mutate(topicId);
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

          <div className="flex flex-col gap-3">
            <label className="inline-flex items-center gap-3 rounded-2xl border border-slate-200 px-4 py-3 text-sm font-semibold text-slate-700">
              <input
                type="checkbox"
                checked={moderationMode}
                onChange={(event) => setModerationMode(event.target.checked)}
                className="h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
              />
              Moderation Mode
            </label>
            <button
              onClick={() => refetch()}
              className="inline-flex items-center justify-center gap-2 rounded-2xl bg-slate-950 px-4 py-3 text-sm font-semibold text-white transition hover:bg-slate-800"
            >
              <RefreshCw className={`h-4 w-4 ${isFetching ? 'animate-spin' : ''}`} />
              Yenile
            </button>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-4 text-xs text-slate-500">
          <span className="inline-flex items-center gap-2">
            <Clock3 className="h-4 w-4" />
            {data ? `${new Date(data.window_start).toLocaleString('tr-TR')} - ${new Date(data.window_end).toLocaleString('tr-TR')}` : 'Pencere bekleniyor'}
          </span>
          {moderationMode ? (
            <span className="rounded-full bg-amber-50 px-3 py-1 text-amber-700">
              Review topicler gorunur. Kartlardan approved / wrong / boring / malformed feedback verebilirsin.
            </span>
          ) : null}
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
                <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">{labelCategory(group.category)}</p>
                <h3 className="text-2xl font-bold tracking-tight text-slate-900">
                  {labelCategory(group.category)} · {group.topics.length} prompt
                </h3>
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
                  moderationMode={moderationMode}
                  onCopyJson={handleCopyJson}
                  onCopyVerticalOutput={handleCopyVerticalOutput}
                  onCopyCarouselOutput={handleCopyCarouselOutput}
                  onCopyPrompt={handleCopyPrompt}
                  onOpenPreview={handleOpenPreview}
                  onSaveFeedback={handleSaveFeedback}
                  onDeleteFeedback={handleDeleteFeedback}
                  feedbackPending={saveFeedbackMutation.isPending && saveFeedbackMutation.variables?.topic_id === topic.topic_id}
                  deletePending={deleteFeedbackMutation.isPending && deleteFeedbackMutation.variables === topic.topic_id}
                />
              ))}
            </div>
          </section>
        ))
      )}
    </div>
  );
}
