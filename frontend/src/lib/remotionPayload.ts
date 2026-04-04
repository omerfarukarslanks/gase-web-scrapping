import type {
  CarouselOutput,
  CarouselBlueprint,
  ContentCategory,
  ContentStrategy,
  EditorialIntent,
  LayoutFamily,
  OutputBlueprint,
  PlatformOutputs,
  PlanningDecision,
  PlanningStatus,
  RemotionPromptPayload,
  RemotionStoryboard,
  RiskFlag,
  SafeVoiceRule,
  SceneBlueprint,
  SceneGoal,
  StoryboardScene,
  StoryboardSceneType,
  StoryboardStat,
  StoryFactPackV3,
  StoryFamily,
  TopicBrief,
  VideoContent,
  VerticalVideoBlueprint,
  VisualAsset,
  VisualType,
  VideoPlan,
  VideoPlanLayoutHint,
  VideoPlanPurpose,
  VideoPlanScene,
  VideoPlanSourceVisibility,
} from '../types/analysis';

const STORAGE_KEY = 'gase-remotion-payload';
const SCORE_RE = /\b\d{1,3}\s*-\s*\d{1,3}\b/;

const VALID_PURPOSES = new Set<VideoPlanPurpose>(['hook', 'explain', 'detail', 'context', 'comparison', 'takeaway', 'close']);
const VALID_LAYOUTS = new Set<VideoPlanLayoutHint>([
  'headline',
  'split',
  'stat',
  'timeline',
  'quote',
  'comparison',
  'minimal',
  'full-bleed',
]);
const VALID_SOURCE_VISIBILITY = new Set<VideoPlanSourceVisibility>(['none', 'subtle', 'contextual']);
const VALID_MASTER_FORMATS = new Set<'16:9' | '9:16'>(['16:9', '9:16']);
const VALID_STORY_FAMILIES = new Set<StoryFamily>([
  'result_update',
  'profile_feature',
  'preview_watchlist',
  'schedule_listing',
  'betting_pick',
  'conflict_breaking',
  'disaster_update',
  'legal_case',
  'court_ruling',
  'consumer_impact',
  'institutional_review',
  'obituary_profile',
  'culture_controversy',
  'commentary_recap',
  'policy_shift',
  'social_trend',
  'opinion_editorial',
  'rescue_operation',
  'general_update',
]);
const VALID_PLANNING_STATUS = new Set<PlanningStatus>(['produce', 'review', 'carousel_only', 'skip']);
const VALID_EDITORIAL_INTENTS = new Set<EditorialIntent>([
  'break',
  'explain',
  'profile',
  'memorial',
  'debate',
  'guide',
  'warning',
  'watchlist',
]);
const VALID_LAYOUT_FAMILIES = new Set<LayoutFamily>([
  'scoreboard_stack',
  'hero_detail_stack',
  'panel_listing_stack',
  'map_casualty_stack',
  'document_context_stack',
  'quote_context_stack',
  'price_impact_stack',
  'timeline_stack',
  'memorial_profile_stack',
  'reaction_split_stack',
  'rescue_sequence_stack',
  'generic_story_stack',
]);
const VALID_RISK_FLAGS = new Set<RiskFlag>([
  'conflict_or_casualty',
  'legal_allegation',
  'election_process',
  'medical_claim',
  'minor_involved',
  'opinion_content',
  'gambling_content',
  'hate_speech_context',
  'obituary_sensitive',
  'speculative_claim',
]);
const VALID_SCENE_GOALS = new Set<SceneGoal>(['hook', 'setup', 'main_fact', 'context', 'impact', 'reaction', 'close']);
const VALID_VISUAL_TYPES = new Set<VisualType>([
  'action_photo',
  'portrait',
  'scoreboard',
  'map',
  'document',
  'quote_card',
  'data_card',
  'timeline',
  'symbolic',
]);
const VALID_SAFE_VOICE_RULES = new Set<SafeVoiceRule>(['fact_voice', 'attributed', 'opinion_labeled']);

const PURPOSE_TO_STORYBOARD_TYPE: Record<VideoPlanPurpose, StoryboardSceneType> = {
  hook: 'hook',
  explain: 'story',
  detail: 'detail',
  context: 'story',
  comparison: 'story',
  takeaway: 'outro',
  close: 'outro',
};

const DEFAULT_STRATEGY_BY_CATEGORY: Record<string, ContentStrategy> = {
  world: {
    primary_category: 'world',
    secondary_categories: [],
    strategy_domain: 'world',
    primary_output: 'vertical_video',
    secondary_outputs: ['carousel'],
    viewer_language: 'en',
    voiceover_mode: 'hybrid',
    hook_style: 'urgent',
    pacing: 'fast',
    visual_policy: 'real_asset_first',
    claim_policy: 'attributed_claims',
    sensitivity_level: 'high',
    human_review_required: false,
    review_reasons: [],
  },
  politics: {
    primary_category: 'politics',
    secondary_categories: [],
    strategy_domain: 'politics',
    primary_output: 'carousel',
    secondary_outputs: ['vertical_video'],
    viewer_language: 'en',
    voiceover_mode: 'hybrid',
    hook_style: 'authority',
    pacing: 'balanced',
    visual_policy: 'real_asset_first',
    claim_policy: 'attributed_claims',
    sensitivity_level: 'high',
    human_review_required: false,
    review_reasons: [],
  },
  business: {
    primary_category: 'business',
    secondary_categories: [],
    strategy_domain: 'business',
    primary_output: 'vertical_video',
    secondary_outputs: ['carousel'],
    viewer_language: 'en',
    voiceover_mode: 'hybrid',
    hook_style: 'authority',
    pacing: 'balanced',
    visual_policy: 'data_card',
    claim_policy: 'standard_fact_voice',
    sensitivity_level: 'medium',
    human_review_required: false,
    review_reasons: [],
  },
  economy: {
    primary_category: 'economy',
    secondary_categories: [],
    strategy_domain: 'economy',
    primary_output: 'carousel',
    secondary_outputs: ['vertical_video'],
    viewer_language: 'en',
    voiceover_mode: 'hybrid',
    hook_style: 'explainer',
    pacing: 'measured',
    visual_policy: 'data_card',
    claim_policy: 'analysis_attribution',
    sensitivity_level: 'medium',
    human_review_required: false,
    review_reasons: [],
  },
  technology: {
    primary_category: 'technology',
    secondary_categories: [],
    strategy_domain: 'technology',
    primary_output: 'vertical_video',
    secondary_outputs: ['carousel'],
    viewer_language: 'en',
    voiceover_mode: 'hybrid',
    hook_style: 'curiosity',
    pacing: 'balanced',
    visual_policy: 'demo_explainer',
    claim_policy: 'standard_fact_voice',
    sensitivity_level: 'medium',
    human_review_required: false,
    review_reasons: [],
  },
  sports: {
    primary_category: 'sports',
    secondary_categories: [],
    strategy_domain: 'sports',
    primary_output: 'vertical_video',
    secondary_outputs: ['carousel'],
    viewer_language: 'en',
    voiceover_mode: 'native',
    hook_style: 'urgent',
    pacing: 'fast',
    visual_policy: 'scoreboard',
    claim_policy: 'standard_fact_voice',
    sensitivity_level: 'low',
    human_review_required: false,
    review_reasons: [],
  },
  culture: {
    primary_category: 'culture',
    secondary_categories: [],
    strategy_domain: 'culture',
    primary_output: 'vertical_video',
    secondary_outputs: ['carousel'],
    viewer_language: 'en',
    voiceover_mode: 'hybrid',
    hook_style: 'human',
    pacing: 'balanced',
    visual_policy: 'human_centered',
    claim_policy: 'standard_fact_voice',
    sensitivity_level: 'medium',
    human_review_required: false,
    review_reasons: [],
  },
  arts: {
    primary_category: 'arts',
    secondary_categories: [],
    strategy_domain: 'arts',
    primary_output: 'carousel',
    secondary_outputs: ['vertical_video'],
    viewer_language: 'en',
    voiceover_mode: 'text_only',
    hook_style: 'human',
    pacing: 'measured',
    visual_policy: 'quote_visual',
    claim_policy: 'analysis_attribution',
    sensitivity_level: 'medium',
    human_review_required: false,
    review_reasons: [],
  },
  science: {
    primary_category: 'science',
    secondary_categories: [],
    strategy_domain: 'science',
    primary_output: 'carousel',
    secondary_outputs: ['vertical_video'],
    viewer_language: 'en',
    voiceover_mode: 'hybrid',
    hook_style: 'explainer',
    pacing: 'measured',
    visual_policy: 'data_card',
    claim_policy: 'analysis_attribution',
    sensitivity_level: 'medium',
    human_review_required: false,
    review_reasons: [],
  },
  environment: {
    primary_category: 'environment',
    secondary_categories: [],
    strategy_domain: 'environment',
    primary_output: 'carousel',
    secondary_outputs: ['vertical_video'],
    viewer_language: 'en',
    voiceover_mode: 'hybrid',
    hook_style: 'urgent',
    pacing: 'balanced',
    visual_policy: 'restrained_drama',
    claim_policy: 'analysis_attribution',
    sensitivity_level: 'high',
    human_review_required: false,
    review_reasons: [],
  },
  health: {
    primary_category: 'health',
    secondary_categories: [],
    strategy_domain: 'health',
    primary_output: 'carousel',
    secondary_outputs: ['vertical_video'],
    viewer_language: 'en',
    voiceover_mode: 'hybrid',
    hook_style: 'explainer',
    pacing: 'measured',
    visual_policy: 'data_card',
    claim_policy: 'medical_caution',
    sensitivity_level: 'high',
    human_review_required: true,
    review_reasons: ['health_content_requires_review'],
  },
  opinion: {
    primary_category: 'opinion',
    secondary_categories: [],
    strategy_domain: 'opinion',
    primary_output: 'carousel',
    secondary_outputs: [],
    viewer_language: 'en',
    voiceover_mode: 'text_only',
    hook_style: 'analysis',
    pacing: 'measured',
    visual_policy: 'quote_visual',
    claim_policy: 'opinion_attribution',
    sensitivity_level: 'high',
    human_review_required: true,
    review_reasons: ['opinion_content_requires_review'],
  },
  analysis: {
    primary_category: 'analysis',
    secondary_categories: [],
    strategy_domain: 'analysis',
    primary_output: 'carousel',
    secondary_outputs: ['vertical_video'],
    viewer_language: 'en',
    voiceover_mode: 'hybrid',
    hook_style: 'analysis',
    pacing: 'measured',
    visual_policy: 'data_card',
    claim_policy: 'analysis_attribution',
    sensitivity_level: 'high',
    human_review_required: true,
    review_reasons: ['analysis_content_requires_review'],
  },
  general: {
    primary_category: 'general',
    secondary_categories: [],
    strategy_domain: 'general',
    primary_output: 'vertical_video',
    secondary_outputs: ['carousel'],
    viewer_language: 'en',
    voiceover_mode: 'hybrid',
    hook_style: 'urgent',
    pacing: 'balanced',
    visual_policy: 'real_asset_first',
    claim_policy: 'standard_fact_voice',
    sensitivity_level: 'medium',
    human_review_required: false,
    review_reasons: [],
  },
};

function cleanString(value: unknown, fallback = ''): string {
  return typeof value === 'string' && value.trim() ? value.trim() : fallback;
}

function cleanStringArray(value: unknown, fallback: string[] = []): string[] {
  if (!Array.isArray(value)) return fallback;
  return value.map((item) => cleanString(item)).filter(Boolean);
}

function dedupe(items: string[]): string[] {
  return Array.from(new Set(items.map((item) => item.trim()).filter(Boolean)));
}

function truncate(value: string, limit: number): string {
  return value.length <= limit ? value : `${value.slice(0, Math.max(0, limit - 3)).trimEnd()}...`;
}

function cleanEnumValue<T extends string>(value: unknown, valid: Set<T>, fallback: T): T {
  const normalized = cleanString(value, fallback) as T;
  return valid.has(normalized) ? normalized : fallback;
}

function extractScore(items: string[]): string {
  for (const item of items) {
    const match = item.match(SCORE_RE);
    if (match) return match[0].replace(/\s+/g, '');
  }
  return '';
}

function clampDuration(value: unknown, fallback = 30): number {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return fallback;
  return Math.min(30, Math.max(8, Math.round(numeric)));
}

function cleanCategory(value: unknown, fallback: ContentCategory = 'general'): ContentCategory {
  const normalized = cleanString(typeof value === 'string' ? value.toLowerCase() : '', fallback);
  const valid: ContentCategory[] = [
    'world',
    'politics',
    'business',
    'economy',
    'technology',
    'sports',
    'culture',
    'arts',
    'science',
    'environment',
    'health',
    'opinion',
    'analysis',
    'general',
  ];
  return (valid.includes(normalized as ContentCategory) ? normalized : fallback) as ContentCategory;
}

function cleanStrategy(value: unknown, category: string): ContentStrategy {
  const fallback = DEFAULT_STRATEGY_BY_CATEGORY[cleanCategory(category)] ?? DEFAULT_STRATEGY_BY_CATEGORY.general;
  if (!value || typeof value !== 'object') return fallback;
  const raw = value as Record<string, unknown>;
  const primary = cleanCategory(raw.primary_category, fallback.primary_category);
  const primaryOutput = cleanString(raw.primary_output, fallback.primary_output) as ContentStrategy['primary_output'];
  const secondaryOutputs = dedupe(
    cleanStringArray(raw.secondary_outputs as unknown[])
      .map((item) => cleanString(item).toLowerCase())
      .filter((item) => item === 'vertical_video' || item === 'carousel')
      .filter((item) => item !== primaryOutput)
  ) as ContentStrategy['secondary_outputs'];

  return {
    ...fallback,
    primary_category: primary,
    secondary_categories: cleanStringArray(raw.secondary_categories as unknown[]).map((item) => cleanCategory(item, primary)).filter((item) => item !== primary).slice(0, 3),
    strategy_domain: cleanString(raw.strategy_domain, fallback.strategy_domain) as ContentStrategy['strategy_domain'],
    primary_output: primaryOutput,
    secondary_outputs: secondaryOutputs.length ? secondaryOutputs : fallback.secondary_outputs,
    viewer_language: cleanString(raw.viewer_language, fallback.viewer_language),
    voiceover_mode: cleanString(raw.voiceover_mode, fallback.voiceover_mode) as ContentStrategy['voiceover_mode'],
    hook_style: cleanString(raw.hook_style, fallback.hook_style) as ContentStrategy['hook_style'],
    pacing: cleanString(raw.pacing, fallback.pacing) as ContentStrategy['pacing'],
    visual_policy: cleanString(raw.visual_policy, fallback.visual_policy) as ContentStrategy['visual_policy'],
    claim_policy: cleanString(raw.claim_policy, fallback.claim_policy) as ContentStrategy['claim_policy'],
    sensitivity_level: cleanString(raw.sensitivity_level, fallback.sensitivity_level) as ContentStrategy['sensitivity_level'],
    human_review_required: Boolean(raw.human_review_required ?? fallback.human_review_required),
    review_reasons: cleanStringArray(raw.review_reasons),
  };
}

function cleanStoryFactPack(value: unknown): StoryFactPackV3 | null {
  if (!value || typeof value !== 'object') return null;
  const raw = value as Record<string, unknown>;
  const coreEvent = cleanString(raw.core_event);
  if (!coreEvent) return null;

  return {
    core_event: coreEvent,
    what_changed: cleanString(raw.what_changed, coreEvent),
    why_now: cleanString(raw.why_now),
    key_entities: cleanStringArray(raw.key_entities).slice(0, 6),
    key_numbers: cleanStringArray(raw.key_numbers).slice(0, 6),
    key_locations: cleanStringArray(raw.key_locations).slice(0, 5),
    time_reference: cleanString(raw.time_reference),
    source_attribution: cleanString(raw.source_attribution),
    evidence_level: cleanEnumValue(raw.evidence_level, new Set(['full_text', 'summary_only', 'headline_only']), 'summary_only'),
    uncertainty_level: cleanEnumValue(raw.uncertainty_level, new Set(['confirmed', 'mixed', 'speculative']), 'mixed'),
  };
}

function inferStoryFamilyFromStrategy(strategy: ContentStrategy): StoryFamily {
  if (strategy.primary_category === 'sports') return 'result_update';
  if (strategy.primary_category === 'opinion') return 'opinion_editorial';
  if (strategy.primary_category === 'health') return 'consumer_impact';
  if (strategy.primary_output === 'carousel') return 'general_update';
  return 'general_update';
}

function inferLayoutFamilyFromStrategy(strategy: ContentStrategy): LayoutFamily {
  switch (strategy.visual_policy) {
    case 'scoreboard':
      return 'scoreboard_stack';
    case 'data_card':
      return 'price_impact_stack';
    case 'quote_visual':
      return 'quote_context_stack';
    default:
      return strategy.primary_output === 'carousel' ? 'document_context_stack' : 'hero_detail_stack';
  }
}

function cleanPlanningDecision(value: unknown, strategy: ContentStrategy): PlanningDecision | null {
  if (!value || typeof value !== 'object') return null;
  const raw = value as Record<string, unknown>;

  return {
    status: cleanEnumValue(raw.status, VALID_PLANNING_STATUS, strategy.primary_output === 'carousel' ? 'carousel_only' : 'produce'),
    story_family: cleanEnumValue(raw.story_family, VALID_STORY_FAMILIES, inferStoryFamilyFromStrategy(strategy)),
    editorial_intent: cleanEnumValue(raw.editorial_intent, VALID_EDITORIAL_INTENTS, 'explain'),
    layout_family: cleanEnumValue(raw.layout_family, VALID_LAYOUT_FAMILIES, inferLayoutFamilyFromStrategy(strategy)),
    scene_count: Math.max(1, Math.min(4, Math.round(Number(raw.scene_count) || 3))),
    risk_flags: cleanStringArray(raw.risk_flags)
      .filter((flag): flag is RiskFlag => VALID_RISK_FLAGS.has(flag as RiskFlag))
      .slice(0, 6),
    reason: cleanString(raw.reason),
  };
}

function cleanSceneBlueprint(value: unknown, index: number): SceneBlueprint | null {
  if (!value || typeof value !== 'object') return null;
  const raw = value as Record<string, unknown>;
  return {
    goal: cleanEnumValue(raw.goal, VALID_SCENE_GOALS, index === 0 ? 'hook' : index >= 2 ? 'impact' : 'context'),
    visual_type: cleanEnumValue(raw.visual_type, VALID_VISUAL_TYPES, index === 0 ? 'action_photo' : 'data_card'),
    must_include: cleanStringArray(raw.must_include).slice(0, 5),
    safe_voice_rule: cleanEnumValue(raw.safe_voice_rule, VALID_SAFE_VOICE_RULES, 'fact_voice'),
  };
}

function cleanVerticalVideoBlueprint(value: unknown): VerticalVideoBlueprint | null {
  if (!value || typeof value !== 'object') return null;
  const raw = value as Record<string, unknown>;
  const sceneBlueprints = Array.isArray(raw.scene_blueprints)
    ? raw.scene_blueprints
        .slice(0, 4)
        .map((entry, index) => cleanSceneBlueprint(entry, index))
        .filter((entry): entry is SceneBlueprint => Boolean(entry))
    : [];

  if (!sceneBlueprints.length) return null;

  return {
    target_duration_seconds: clampDuration(raw.target_duration_seconds, 15),
    scene_blueprints: sceneBlueprints,
  };
}

function cleanCarouselBlueprint(value: unknown): CarouselBlueprint | null {
  if (!value || typeof value !== 'object') return null;
  const raw = value as Record<string, unknown>;
  const slideGoals = cleanStringArray(raw.slide_goals).slice(0, 6);
  if (!slideGoals.length) return null;

  return {
    slide_count: Math.max(1, Math.min(8, Math.round(Number(raw.slide_count) || slideGoals.length))),
    cover_angle: cleanString(raw.cover_angle, slideGoals[0]),
    slide_goals: slideGoals,
  };
}

function cleanOutputBlueprint(value: unknown): OutputBlueprint | null {
  if (!value || typeof value !== 'object') return null;
  const raw = value as Record<string, unknown>;
  const verticalVideo = cleanVerticalVideoBlueprint(raw.vertical_video);
  const carousel = cleanCarouselBlueprint(raw.carousel);
  if (!verticalVideo && !carousel) return null;
  return {
    vertical_video: verticalVideo,
    carousel,
  };
}

function allocateSceneDurations(total: number, count: number, requested?: number[]): number[] {
  if (count <= 0) return [];
  if (count === 1) return [total];
  const minimum = 2;
  const base = Array.from({ length: count }, () => minimum);
  const remaining = Math.max(0, total - minimum * count);
  const weights = (requested?.slice(0, count).map((value) => Math.max(1, Math.round(value))) ?? []).concat(
    Array.from({ length: Math.max(0, count - (requested?.length ?? 0)) }, () => 1)
  );
  const totalWeight = weights.reduce((sum, value) => sum + value, 0);
  const rawShares = weights.map((value) => (remaining * value) / totalWeight);
  const ints = rawShares.map((value) => Math.floor(value));
  const result = base.map((value, index) => value + ints[index]);
  let leftover = remaining - ints.reduce((sum, value) => sum + value, 0);
  const order = rawShares
    .map((value, index) => ({ index, fraction: value - Math.floor(value) }))
    .sort((left, right) => right.fraction - left.fraction);
  for (const item of order) {
    if (leftover <= 0) break;
    result[item.index] += 1;
    leftover -= 1;
  }
  return result;
}

function inferPacing(total: number, sceneCount: number): string {
  if (total <= 14 || sceneCount >= 3) return 'fast';
  if (total >= 24) return 'measured';
  return 'balanced';
}

function inferComplexity(summary: string, keyPoints: string[]): 'short' | 'medium' | 'complex' {
  const summaryLength = cleanString(summary).length;
  const pointCount = keyPoints.filter((point) => cleanString(point)).length;
  if (pointCount <= 1 && summaryLength <= 120) return 'short';
  if (pointCount <= 3 && summaryLength <= 220) return 'medium';
  return 'complex';
}

function inferSceneCount(summary: string, keyPoints: string[]): number {
  const complexity = inferComplexity(summary, keyPoints);
  if (complexity === 'short') return 1;
  if (complexity === 'medium') return 2;
  return 3;
}

function layoutHintFromVisualType(visualType: VisualType, fallback: VideoPlanLayoutHint): VideoPlanLayoutHint {
  switch (visualType) {
    case 'scoreboard':
      return 'stat';
    case 'map':
    case 'timeline':
      return 'timeline';
    case 'document':
    case 'quote_card':
      return 'quote';
    case 'portrait':
    case 'action_photo':
      return 'full-bleed';
    case 'data_card':
      return 'stat';
    case 'symbolic':
      return 'minimal';
    default:
      return fallback;
  }
}

function cleanVideoContent(value: unknown): VideoContent | null {
  if (!value || typeof value !== 'object') return null;
  const raw = value as Record<string, unknown>;
  const headline = cleanString(raw.headline);
  if (!headline) return null;
  return {
    headline,
    narrative: cleanStringArray(raw.narrative),
    key_figures: cleanStringArray(raw.key_figures),
    key_data: cleanString(raw.key_data),
    source_line: cleanString(raw.source_line),
    duration_seconds: clampDuration(raw.duration_seconds, 32),
  };
}

function cleanVisualAsset(value: unknown, fallbackId: string): VisualAsset | null {
  if (!value || typeof value !== 'object') return null;
  const raw = value as Record<string, unknown>;
  const url = cleanString(raw.url);
  if (!url) return null;
  const kind = cleanString(raw.kind) === 'og_image' ? 'og_image' : 'article_image';
  return {
    asset_id: cleanString(raw.asset_id, fallbackId),
    url,
    kind,
    source_article_id: cleanString(raw.source_article_id),
    source_name: cleanString(raw.source_name) || null,
    alt_text: cleanString(raw.alt_text, 'News visual'),
  };
}

function defaultLayout(category: string, purpose: VideoPlanPurpose, keyData: string, keyFigures: string[]): VideoPlanLayoutHint {
  if (purpose === 'hook') return category === 'sports' || category === 'science' ? 'full-bleed' : 'headline';
  if (purpose === 'comparison') return 'comparison';
  if (purpose === 'context') return 'timeline';
  if (purpose === 'detail') return keyData ? 'stat' : 'split';
  if (purpose === 'takeaway' || purpose === 'close') return 'minimal';
  if (purpose === 'explain') {
    if (category === 'world' || category === 'science' || category === 'politics') return 'timeline';
    if (category === 'sports' && keyFigures.length >= 2) return 'comparison';
    if (keyData) return 'stat';
    return 'split';
  }
  return 'headline';
}

function buildVideoContentFromPlan(plan: VideoPlan): VideoContent {
  const narrative = dedupe(
    plan.scenes.map((scene) => scene.body || scene.headline).filter(Boolean)
  ).slice(0, 3);
  const keyFigures = dedupe(plan.scenes.flatMap((scene) => scene.key_figures)).slice(0, 4);
  const keyData = plan.scenes.find((scene) => scene.key_data)?.key_data ?? '';

  return {
    headline: plan.title,
    narrative,
    key_figures: keyFigures,
    key_data: keyData,
    source_line: '',
    duration_seconds: plan.duration_seconds,
  };
}

function buildStoryboardFromPlan(plan: VideoPlan): RemotionStoryboard {
  const scenes: StoryboardScene[] = plan.scenes.map((scene) => {
    const stats: StoryboardStat[] = [];
    if (scene.key_data) {
      stats.push({ label: 'Key data', value: truncate(scene.key_data, 60) });
    }
    stats.push({ label: 'Duration', value: `${scene.duration_seconds}s` });

    return {
      scene_type: PURPOSE_TO_STORYBOARD_TYPE[scene.purpose] ?? 'story',
      duration_seconds: scene.duration_seconds,
      layout_hint: scene.layout_hint,
      kicker: scene.purpose.toUpperCase(),
      headline: truncate(scene.headline, 2000),
      body: truncate(scene.body, 2000),
      voiceover: (scene as any).voiceover || scene.body || scene.headline,
      source_line: scene.source_line,
      asset_ids: scene.asset_ids.slice(0, 2),
      visual_elements: scene.visual_direction ? [truncate(scene.visual_direction, 2000)] : [],
      bullet_points: scene.supporting_points.slice(0, 4).map((point) => truncate(point, 2000)),
      stats: stats.slice(0, 4),
      chips: scene.key_figures.slice(0, 4),
    };
  });

  return {
    visual_thesis: plan.title,
    scenes,
  };
}

function buildFallbackVideoPlan(fields: {
  headline: string;
  category: string;
  summary: string;
  keyPoints: string[];
  whyItMatters: string;
  sources: string[];
  durationSeconds: number;
  visualAssets: VisualAsset[];
  videoContent: VideoContent | null;
  strategy: ContentStrategy;
  storyFactPack?: StoryFactPackV3 | null;
  planningDecision?: PlanningDecision | null;
  outputBlueprint?: OutputBlueprint | null;
}): VideoPlan {
  const preferredSceneCount =
    fields.outputBlueprint?.vertical_video?.scene_blueprints.length ||
    fields.planningDecision?.scene_count ||
    inferSceneCount(fields.summary, fields.keyPoints);
  const targetDuration =
    fields.outputBlueprint?.vertical_video?.target_duration_seconds ??
    fields.durationSeconds;
  const total = clampDuration(targetDuration, 30);
  const keyData =
    fields.videoContent?.key_data ||
    fields.storyFactPack?.key_numbers[0] ||
    extractScore([fields.headline, fields.summary, ...fields.keyPoints]) ||
    '';
  const keyFigures = dedupe([
    ...(fields.videoContent?.key_figures ?? []),
    ...(fields.storyFactPack?.key_numbers ?? []),
  ]).slice(0, 4);
  const sceneCount = Math.max(1, Math.min(3, preferredSceneCount));
  const sceneDurations = allocateSceneDurations(total, sceneCount, [4, 3, 2].slice(0, sceneCount));
  const primaryAssetId = fields.visualAssets[0]?.asset_id ?? '';
  const secondaryAssetId = fields.visualAssets[1]?.asset_id ?? primaryAssetId;
  const sceneBlueprints = fields.outputBlueprint?.vertical_video?.scene_blueprints ?? [];
  const hookBlueprint = sceneBlueprints[0] ?? null;
  const explainBlueprint = sceneBlueprints[1] ?? null;
  const closeBlueprint = sceneBlueprints[2] ?? sceneBlueprints[sceneBlueprints.length - 1] ?? null;
  const hookBody = fields.storyFactPack?.what_changed || fields.summary;
  const takeawayBody = fields.storyFactPack?.why_now || fields.whyItMatters;
  const takeawayHeadline = fields.whyItMatters || fields.storyFactPack?.why_now || fields.headline;

  const scenes: VideoPlanScene[] = [
    {
      scene_id: 'scene-1',
      purpose: 'hook',
      duration_seconds: sceneDurations[0],
      layout_hint: layoutHintFromVisualType(
        hookBlueprint?.visual_type ?? 'action_photo',
        defaultLayout(fields.category, 'hook', keyData, keyFigures)
      ),
      headline: fields.videoContent?.headline || fields.headline,
      body: hookBody,
      voiceover: hookBody || fields.headline,
      supporting_points: [],
      key_figures: keyFigures.slice(0, 4),
      key_data: keyData,
      visual_direction: '',
      motion_direction: '',
      transition_from_previous: 'Cold open',
      source_line: '',
      asset_ids: primaryAssetId ? [primaryAssetId] : [],
    },
  ];

  if (sceneCount >= 2) {
    const layout = layoutHintFromVisualType(
      explainBlueprint?.visual_type ?? 'data_card',
      defaultLayout(fields.category, 'explain', keyData, keyFigures)
    );
    scenes.push({
      scene_id: 'scene-2',
      purpose: 'explain',
      duration_seconds: sceneDurations[1],
      layout_hint: layout,
      headline: fields.keyPoints[0] || fields.storyFactPack?.core_event || fields.summary,
      body: sceneCount === 2 ? takeawayBody : '',
      voiceover: fields.keyPoints[0] || fields.storyFactPack?.what_changed || fields.summary,
      supporting_points: dedupe([
        ...fields.keyPoints.slice(0, 2),
        ...(fields.storyFactPack?.key_entities ?? []).slice(0, 2),
      ]).slice(0, 3),
      key_figures: keyFigures.slice(0, 4),
      key_data: layout === 'stat' ? keyData : '',
      visual_direction: '',
      motion_direction: '',
      transition_from_previous: '',
      source_line: '',
      asset_ids: secondaryAssetId && layout === 'split' ? [secondaryAssetId] : [],
    });
  }

  if (sceneCount >= 3) {
    scenes.push({
      scene_id: 'scene-3',
      purpose: 'takeaway',
      duration_seconds: sceneDurations[2],
      layout_hint: layoutHintFromVisualType(
        closeBlueprint?.visual_type ?? 'symbolic',
        defaultLayout(fields.category, 'takeaway', '', keyFigures)
      ),
      headline: takeawayHeadline,
      body: takeawayBody,
      voiceover: takeawayBody || takeawayHeadline,
      supporting_points: [],
      key_figures: keyFigures.slice(0, 3),
      key_data: '',
      visual_direction: '',
      motion_direction: '',
      transition_from_previous: '',
      source_line: '',
      asset_ids: [],
    });
  }

  return {
    title: fields.videoContent?.headline || fields.headline,
    audience_mode: 'sound_off_first',
    master_format: fields.strategy.primary_output === 'vertical_video' ? '9:16' : '16:9',
    duration_seconds: total,
    pacing_hint: inferPacing(total, sceneCount),
    source_visibility: 'none',
    scenes,
  };
}

function cleanVideoPlanScene(value: unknown, fallback: VideoPlanScene, index: number): VideoPlanScene | null {
  if (!value || typeof value !== 'object') return null;
  const raw = value as Record<string, unknown>;
  const purpose = cleanString(raw.purpose).toLowerCase() as VideoPlanPurpose;
  const layoutHint = cleanString(raw.layout_hint).toLowerCase() as VideoPlanLayoutHint;
  const headline = cleanString(raw.headline);
  if (!VALID_PURPOSES.has(purpose) || !VALID_LAYOUTS.has(layoutHint) || !headline) return null;

  return {
    scene_id: cleanString(raw.scene_id, `scene-${index + 1}`),
    purpose,
    duration_seconds: Math.max(1, Math.round(Number(raw.duration_seconds) || fallback.duration_seconds || 1)),
    layout_hint: layoutHint,
    headline,
    body: cleanString(raw.body, fallback.body),
    voiceover: cleanString(raw.voiceover, (fallback as any).voiceover || fallback.body),
    supporting_points: cleanStringArray(raw.supporting_points, fallback.supporting_points).slice(0, 4),
    key_figures: cleanStringArray(raw.key_figures, fallback.key_figures).slice(0, 4),
    key_data: cleanString(raw.key_data, fallback.key_data),
    visual_direction: cleanString(raw.visual_direction, fallback.visual_direction),
    motion_direction: cleanString(raw.motion_direction, fallback.motion_direction),
    transition_from_previous: cleanString(raw.transition_from_previous, fallback.transition_from_previous),
    source_line: cleanString(raw.source_line, fallback.source_line),
    asset_ids: cleanStringArray(raw.asset_ids, fallback.asset_ids).slice(0, 2),
  };
}

function normalizeVideoPlan(value: unknown, fallback: VideoPlan, visualAssets: VisualAsset[]): VideoPlan {
  if (!value || typeof value !== 'object') return fallback;
  const raw = value as Record<string, unknown>;
  const scenesInput = Array.isArray(raw.scenes) ? raw.scenes : [];
  const fallbackScenes = fallback.scenes;
  const validAssetIds = new Set(visualAssets.map((asset) => asset.asset_id));
  const cleanedScenes = scenesInput
    .slice(0, 4)
    .map((scene, index) => cleanVideoPlanScene(scene, fallbackScenes[Math.min(index, fallbackScenes.length - 1)], index))
    .filter((scene): scene is VideoPlanScene => Boolean(scene));
  if (!cleanedScenes.length) return fallback;

  const totalDuration = clampDuration(raw.duration_seconds, fallback.duration_seconds);
  const sceneDurations = allocateSceneDurations(
    totalDuration,
    cleanedScenes.length,
    cleanedScenes.map((scene) => scene.duration_seconds)
  );
  const sourceVisibility = cleanString(raw.source_visibility).toLowerCase() as VideoPlanSourceVisibility;
  const normalizedVisibility = VALID_SOURCE_VISIBILITY.has(sourceVisibility) ? sourceVisibility : fallback.source_visibility;

  return {
    title: cleanString(raw.title, fallback.title),
    audience_mode: 'sound_off_first',
    master_format: VALID_MASTER_FORMATS.has(cleanString(raw.master_format, fallback.master_format) as '16:9' | '9:16')
      ? (cleanString(raw.master_format, fallback.master_format) as '16:9' | '9:16')
      : fallback.master_format,
    duration_seconds: totalDuration,
    pacing_hint: cleanString(raw.pacing_hint, inferPacing(totalDuration, cleanedScenes.length)),
    source_visibility: normalizedVisibility,
    scenes: cleanedScenes.map((scene, index) => ({
      ...scene,
      duration_seconds: sceneDurations[index],
      source_line: normalizedVisibility === 'none' ? '' : scene.source_line,
      voiceover: (scene as any).voiceover || scene.body || scene.headline,
      asset_ids: scene.asset_ids.filter((assetId) => validAssetIds.has(assetId)).slice(0, 2),
    })),
  };
}

function normalizeStoryboard(value: unknown, fallback: RemotionStoryboard): RemotionStoryboard {
  if (!value || typeof value !== 'object') return fallback;
  const raw = value as Record<string, unknown>;
  const rawScenes = Array.isArray(raw.scenes) ? raw.scenes : [];
  const scenes = rawScenes
    .map((item, index) => {
      if (!item || typeof item !== 'object') return null;
      const scene = item as Record<string, unknown>;
      const fallbackScene = fallback.scenes[Math.min(index, fallback.scenes.length - 1)];
      return {
        scene_type: cleanString(scene.scene_type, fallbackScene.scene_type) as StoryboardSceneType,
        duration_seconds: Math.max(0, Math.round(Number(scene.duration_seconds) || fallbackScene.duration_seconds || 0)),
        layout_hint: cleanString(scene.layout_hint, fallbackScene.layout_hint),
        kicker: cleanString(scene.kicker, fallbackScene.kicker),
        headline: cleanString(scene.headline, fallbackScene.headline),
        body: cleanString(scene.body, fallbackScene.body),
        source_line: cleanString(scene.source_line, fallbackScene.source_line),
        asset_ids: cleanStringArray(scene.asset_ids, fallbackScene.asset_ids).slice(0, 2),
        visual_elements: cleanStringArray(scene.visual_elements, fallbackScene.visual_elements).slice(0, 4),
        bullet_points: cleanStringArray(scene.bullet_points, fallbackScene.bullet_points).slice(0, 4),
        stats: (Array.isArray(scene.stats) ? scene.stats : fallbackScene.stats)
          .map((stat) => {
            if (!stat || typeof stat !== 'object') return null;
            const rawStat = stat as Record<string, unknown>;
            const label = cleanString(rawStat.label);
            const value = cleanString(rawStat.value);
            return label && value ? { label, value } : null;
          })
          .filter((stat): stat is StoryboardStat => Boolean(stat))
          .slice(0, 4),
        chips: cleanStringArray(scene.chips, fallbackScene.chips).slice(0, 5),
      } satisfies StoryboardScene;
    })
    .filter((scene): scene is StoryboardScene => Boolean(scene));

  return scenes.length
    ? {
        visual_thesis: cleanString(raw.visual_thesis, fallback.visual_thesis),
        scenes,
      }
    : fallback;
}

function buildFallbackPlatformOutputs(fields: {
  headline: string;
  summary: string;
  keyPoints: string[];
  whyItMatters: string;
  videoPlan: VideoPlan;
  videoContent: VideoContent;
  strategy: ContentStrategy;
  storyFactPack?: StoryFactPackV3 | null;
  planningDecision?: PlanningDecision | null;
  outputBlueprint?: OutputBlueprint | null;
}): PlatformOutputs {
  const allowVertical = fields.planningDecision?.status !== 'skip' && fields.planningDecision?.status !== 'carousel_only';
  const allowCarousel = fields.planningDecision?.status !== 'skip';
  let startSecond = 0;
  const verticalScenes = fields.videoPlan.scenes.map((scene) => {
    const current = {
      scene_id: scene.scene_id,
      start_second: startSecond,
      duration_seconds: scene.duration_seconds,
      headline: scene.headline,
      body: scene.body,
      voiceover: scene.voiceover || scene.body || scene.headline,
      overlay_text: scene.headline,
      visual_direction: scene.visual_direction,
    };
    startSecond += scene.duration_seconds;
    return current;
  });

  const overlayText = verticalScenes.map((scene) => scene.overlay_text).filter(Boolean).slice(0, 5);
  const hashtags = dedupe(
    ['#News', `#${fields.strategy.primary_category}`]
      .concat(fields.videoContent.key_figures.slice(0, 2).map((value) => `#${value.replace(/[^A-Za-z0-9]+/g, '')}`))
      .filter(Boolean)
  ).slice(0, 5);

  const carouselGoals = fields.outputBlueprint?.carousel?.slide_goals?.length
    ? fields.outputBlueprint.carousel.slide_goals
    : dedupe([...fields.keyPoints, fields.storyFactPack?.why_now ?? '', fields.whyItMatters]).filter(Boolean).slice(0, 4);
  const carouselSlides = carouselGoals.map((body) => ({
    title: truncate(body, 56) || fields.headline,
    body,
    kicker: fields.planningDecision?.story_family
      ? fields.planningDecision.story_family.toUpperCase()
      : fields.strategy.strategy_domain.toUpperCase(),
    image_prompt: `Editorial visual about ${fields.headline}. Keep it clear, social-first, and text-free.`,
  }));

  return {
    vertical_video: allowVertical
      ? {
          aspect_ratio: '9:16',
          target_platforms: ['youtube_shorts', 'instagram_reels', 'tiktok'],
          duration_seconds: fields.videoPlan.duration_seconds,
          hook: overlayText[0] || fields.headline,
          title: fields.videoContent.headline || fields.headline,
          tts_script: verticalScenes.map((scene) => scene.voiceover).join(' '),
          overlay_text: overlayText,
          scenes: verticalScenes,
          caption: [fields.summary, fields.whyItMatters].filter(Boolean).join(' ').trim(),
          hashtags,
        }
      : null,
    carousel: allowCarousel
      ? {
          cover: {
            title: fields.headline,
            body: fields.summary,
            kicker: fields.outputBlueprint?.carousel?.cover_angle
              ? truncate(fields.outputBlueprint.carousel.cover_angle, 36)
              : fields.strategy.primary_category.toUpperCase(),
            image_prompt: `Editorial cover visual about ${fields.headline}. Clear composition, strong focus, text-free.`,
          },
          slides: carouselSlides.length
            ? carouselSlides
            : [{
                title: fields.headline,
                body: fields.summary,
                kicker: fields.strategy.primary_category.toUpperCase(),
                image_prompt: `Editorial supporting visual about ${fields.summary || fields.headline}.`,
              }],
          caption: [fields.summary, fields.whyItMatters].filter(Boolean).join(' ').trim(),
          hashtags,
        }
      : null,
    image_prompts: [
      {
        usage: 'cover',
        prompt: `Cinematic editorial visual about ${fields.storyFactPack?.core_event || fields.headline}. Clear hierarchy, platform-safe framing, no on-image text.`,
      },
      {
        usage: 'supporting',
        prompt: `Supporting editorial visual for ${fields.storyFactPack?.what_changed || fields.summary || fields.headline}.`,
      },
    ],
  };
}

function cleanPlatformOutputs(value: unknown, fallback: PlatformOutputs): PlatformOutputs {
  if (!value || typeof value !== 'object') return fallback;
  const raw = value as Record<string, unknown>;
  const vertical = raw.vertical_video && typeof raw.vertical_video === 'object' ? raw.vertical_video as Record<string, unknown> : null;
  const carousel = raw.carousel && typeof raw.carousel === 'object' ? raw.carousel as Record<string, unknown> : null;
  const fallbackVertical = fallback.vertical_video;
  const fallbackCarousel = fallback.carousel;

  return {
    vertical_video: fallbackVertical
      ? {
          ...fallbackVertical,
          hook: cleanString(vertical?.hook, fallbackVertical.hook),
          title: cleanString(vertical?.title, fallbackVertical.title),
          tts_script: cleanString(vertical?.tts_script, fallbackVertical.tts_script),
          caption: cleanString(vertical?.caption, fallbackVertical.caption),
          overlay_text: cleanStringArray(vertical?.overlay_text, fallbackVertical.overlay_text),
          hashtags: cleanStringArray(vertical?.hashtags, fallbackVertical.hashtags),
          scenes: Array.isArray(vertical?.scenes)
            ? vertical!.scenes
                .map((scene, index) => {
                  if (!scene || typeof scene !== 'object') return null;
                  const fallbackScene = fallbackVertical.scenes[Math.min(index, fallbackVertical.scenes.length - 1)];
                  const rawScene = scene as Record<string, unknown>;
                  return {
                    ...fallbackScene,
                    scene_id: cleanString(rawScene.scene_id, fallbackScene.scene_id),
                    start_second: Math.max(0, Math.round(Number(rawScene.start_second) || fallbackScene.start_second)),
                    duration_seconds: Math.max(1, Math.round(Number(rawScene.duration_seconds) || fallbackScene.duration_seconds)),
                    headline: cleanString(rawScene.headline, fallbackScene.headline),
                    body: cleanString(rawScene.body, fallbackScene.body),
                    voiceover: cleanString(rawScene.voiceover, fallbackScene.voiceover),
                    overlay_text: cleanString(rawScene.overlay_text, fallbackScene.overlay_text),
                    visual_direction: cleanString(rawScene.visual_direction, fallbackScene.visual_direction),
                  };
                })
                .filter(Boolean) as typeof fallbackVertical.scenes
            : fallbackVertical.scenes,
        }
      : null,
    carousel: fallbackCarousel
      ? {
          ...fallbackCarousel,
          cover: carousel?.cover && typeof carousel.cover === 'object'
            ? {
                title: cleanString((carousel.cover as Record<string, unknown>).title, fallbackCarousel.cover.title),
                body: cleanString((carousel.cover as Record<string, unknown>).body, fallbackCarousel.cover.body),
                kicker: cleanString((carousel.cover as Record<string, unknown>).kicker, fallbackCarousel.cover.kicker),
                image_prompt: cleanString((carousel.cover as Record<string, unknown>).image_prompt, fallbackCarousel.cover.image_prompt),
              }
            : fallbackCarousel.cover,
          slides: Array.isArray(carousel?.slides)
            ? carousel!.slides
                .map((slide, index) => {
                  if (!slide || typeof slide !== 'object') return null;
                  const fallbackSlide = fallbackCarousel.slides[Math.min(index, fallbackCarousel.slides.length - 1)] ?? fallbackCarousel.cover;
                  const rawSlide = slide as Record<string, unknown>;
                  return {
                    title: cleanString(rawSlide.title, fallbackSlide.title),
                    body: cleanString(rawSlide.body, fallbackSlide.body),
                    kicker: cleanString(rawSlide.kicker, fallbackSlide.kicker),
                    image_prompt: cleanString(rawSlide.image_prompt, fallbackSlide.image_prompt),
                  };
                })
                .filter(Boolean) as CarouselOutput['slides']
            : fallbackCarousel.slides,
          caption: cleanString(carousel?.caption, fallbackCarousel.caption),
          hashtags: cleanStringArray(carousel?.hashtags, fallbackCarousel.hashtags),
        }
      : null,
    image_prompts: Array.isArray(raw.image_prompts)
      ? raw.image_prompts
          .map((entry) => {
            if (!entry || typeof entry !== 'object') return null;
            const rawPrompt = entry as Record<string, unknown>;
            const prompt = cleanString(rawPrompt.prompt);
            if (!prompt) return null;
            return {
              usage: cleanString(rawPrompt.usage, 'supporting') as 'cover' | 'scene' | 'supporting',
              prompt,
            };
          })
          .filter(Boolean) as PlatformOutputs['image_prompts']
      : fallback.image_prompts,
  };
}

function buildPayloadBase(topic: {
  headline: string;
  category: string;
  secondaryCategories?: ContentCategory[];
  summary: string;
  keyPoints: string[];
  whyItMatters: string;
  sources: string[];
  promptText: string;
  storyAngle: string;
  visualBrief: string;
  formatHint: string;
  motionTreatment: string;
  transitionStyle: string;
  tone: string;
  sceneSequence: string[];
  designKeywords: string[];
  mustInclude: string[];
  avoid: string[];
  durationSeconds: number;
  visualAssets: VisualAsset[];
  videoContent: VideoContent | null;
  strategy?: ContentStrategy | null;
  platformOutputs?: PlatformOutputs | null;
  videoPlan?: VideoPlan | null;
  storyFactPack?: StoryFactPackV3 | null;
  planningDecision?: PlanningDecision | null;
  outputBlueprint?: OutputBlueprint | null;
  storyboard?: RemotionStoryboard;
}): RemotionPromptPayload {
  const visualAssets = dedupe(
    topic.visualAssets.map((asset) => asset.asset_id)
  )
    .map((assetId) => topic.visualAssets.find((asset) => asset.asset_id === assetId) ?? null)
    .filter((asset): asset is VisualAsset => Boolean(asset));
  const strategy = cleanStrategy(topic.strategy, topic.category);
  const storyFactPack = cleanStoryFactPack(topic.storyFactPack);
  const planningDecision = cleanPlanningDecision(topic.planningDecision, strategy);
  const outputBlueprint = cleanOutputBlueprint(topic.outputBlueprint);

  const fallbackVideoPlan = buildFallbackVideoPlan({
    headline: topic.headline,
    category: topic.category,
    summary: topic.summary,
    keyPoints: topic.keyPoints,
    whyItMatters: topic.whyItMatters,
    sources: topic.sources,
    durationSeconds: topic.durationSeconds,
    visualAssets,
    videoContent: topic.videoContent,
    strategy,
    storyFactPack,
    planningDecision,
    outputBlueprint,
  });

  const videoPlan = normalizeVideoPlan(topic.videoPlan, fallbackVideoPlan, visualAssets);
  const videoContent = topic.videoContent ?? buildVideoContentFromPlan(videoPlan);
  const fallbackStoryboard = buildStoryboardFromPlan(videoPlan);
  const fallbackPlatformOutputs = buildFallbackPlatformOutputs({
    headline: topic.headline,
    summary: topic.summary,
    keyPoints: topic.keyPoints,
    whyItMatters: topic.whyItMatters,
    videoPlan,
    videoContent,
    strategy,
    storyFactPack,
    planningDecision,
    outputBlueprint,
  });

  return {
    ...topic,
    secondaryCategories: topic.secondaryCategories ?? [],
    durationSeconds: videoPlan.duration_seconds,
    visualAssets,
    strategy,
    platformOutputs: cleanPlatformOutputs(topic.platformOutputs, fallbackPlatformOutputs),
    storyFactPack,
    planningDecision,
    outputBlueprint,
    videoPlan,
    videoContent,
    storyboard: normalizeStoryboard(topic.storyboard, fallbackStoryboard),
  };
}

export function buildRemotionPayload(topic: TopicBrief): RemotionPromptPayload {
  return buildPayloadBase({
    headline: topic.headline_tr,
    category: topic.category,
    secondaryCategories: topic.secondary_categories,
    summary: topic.summary_tr,
    keyPoints: topic.key_points_tr,
    whyItMatters: topic.why_it_matters_tr,
    sources: topic.sources,
    promptText: topic.video_prompt_en,
    formatHint: topic.video_prompt_parts.format_hint,
    storyAngle: topic.video_prompt_parts.story_angle,
    visualBrief: topic.video_prompt_parts.visual_brief,
    motionTreatment: topic.video_prompt_parts.motion_treatment,
    transitionStyle: topic.video_prompt_parts.transition_style,
    tone: topic.video_prompt_parts.tone,
    sceneSequence: topic.video_prompt_parts.scene_sequence,
    designKeywords: topic.video_prompt_parts.design_keywords,
    mustInclude: topic.video_prompt_parts.must_include,
    avoid: topic.video_prompt_parts.avoid,
    durationSeconds: topic.video_prompt_parts.duration_seconds,
    visualAssets: topic.visual_assets,
    videoContent: topic.video_content,
    strategy: topic.strategy,
    platformOutputs: topic.platform_outputs,
    videoPlan: topic.video_plan,
    storyFactPack: topic.story_fact_pack,
    planningDecision: topic.planning_decision,
    outputBlueprint: topic.output_blueprint,
    storyboard: topic.remotion_storyboard,
  });
}

export function parseRemotionPayload(value: unknown): RemotionPromptPayload {
  if (!value || typeof value !== 'object') {
    throw new Error('Prompt JSON nesnesi gecersiz.');
  }

  const payload = value as Record<string, unknown>;
  const headline = cleanString(payload.headline);
  const summary = cleanString(payload.summary);
  const rawVisualAssets = Array.isArray(payload.visualAssets ?? payload.visual_assets)
    ? (payload.visualAssets ?? payload.visual_assets) as unknown[]
    : [];

  if (!headline || !summary) {
    throw new Error('`headline` ve `summary` alanlari zorunludur.');
  }

  return buildPayloadBase({
    headline,
    category: cleanString(payload.category, 'general'),
    secondaryCategories: cleanStringArray(payload.secondaryCategories ?? payload.secondary_categories).map((item) => cleanCategory(item)),
    summary,
    keyPoints: cleanStringArray(payload.keyPoints ?? payload.key_points),
    whyItMatters: cleanString(payload.whyItMatters ?? payload.why_it_matters, 'Bu gelisme kisa vadede gundemi etkileyebilir.'),
    sources: cleanStringArray(payload.sources),
    promptText: cleanString(payload.promptText ?? payload.prompt_text, headline),
    formatHint: cleanString(payload.formatHint ?? payload.format_hint, 'Editorial motion-graphics short'),
    storyAngle: cleanString(payload.storyAngle ?? payload.story_angle, headline),
    visualBrief: cleanString(payload.visualBrief ?? payload.visual_brief, 'Readable motion graphics with labeled facts and clear visual hierarchy.'),
    motionTreatment: cleanString(payload.motionTreatment ?? payload.motion_treatment, 'Clean panel choreography and subtle kinetic typography.'),
    transitionStyle: cleanString(payload.transitionStyle ?? payload.transition_style, 'Shape wipes and restrained motion transitions.'),
    tone: cleanString(payload.tone, 'Urgent and factual'),
    sceneSequence: cleanStringArray(payload.sceneSequence ?? payload.scene_sequence, [
      'Open with the main headline and a bold category strap.',
      'Highlight the summary with supporting visuals and data callouts.',
      'Close with why it matters and what to watch next.',
    ]),
    designKeywords: cleanStringArray(payload.designKeywords ?? payload.design_keywords, ['editorial motion', 'clear typography']),
    mustInclude: cleanStringArray(payload.mustInclude ?? payload.must_include),
    avoid: cleanStringArray(payload.avoid, ['Publisher logos', 'Unsupported claims']),
    durationSeconds: clampDuration(payload.durationSeconds ?? payload.duration_seconds, 30),
    visualAssets: rawVisualAssets
      .map((asset: unknown, index: number) => cleanVisualAsset(asset, `asset-${index + 1}`))
      .filter((asset): asset is VisualAsset => Boolean(asset)),
    videoContent: cleanVideoContent(payload.videoContent ?? payload.video_content),
    strategy: (payload.strategy ?? payload.contentStrategy) as ContentStrategy | undefined,
    platformOutputs: (payload.platformOutputs ?? payload.platform_outputs) as PlatformOutputs | undefined,
    videoPlan: (payload.videoPlan ?? payload.video_plan) as VideoPlan | undefined,
    storyFactPack: (payload.storyFactPack ?? payload.story_fact_pack) as StoryFactPackV3 | undefined,
    planningDecision: (payload.planningDecision ?? payload.planning_decision) as PlanningDecision | undefined,
    outputBlueprint: (payload.outputBlueprint ?? payload.output_blueprint) as OutputBlueprint | undefined,
    storyboard: (payload.storyboard ?? payload.remotion_storyboard) as RemotionStoryboard | undefined,
  });
}

export function saveRemotionPayload(payload: RemotionPromptPayload): void {
  if (typeof window === 'undefined') return;
  window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
}

export function readRemotionPayload(): RemotionPromptPayload | null {
  if (typeof window === 'undefined') return null;
  const raw = window.sessionStorage.getItem(STORAGE_KEY);
  if (!raw) return null;

  try {
    return parseRemotionPayload(JSON.parse(raw));
  } catch {
    return null;
  }
}

export const SAMPLE_REMOTION_PAYLOAD: RemotionPromptPayload = buildPayloadBase({
  headline: 'Artemis II fırlatmasıyla Ay görevi yeni aşamaya geçti',
  category: 'science',
  summary:
    'Artemis II görevi başarıyla fırlatıldı ve insanlı Ay programı yeni bir aşamaya geçti.',
  keyPoints: [
    "Fırlatma Florida'dan gerçekleştirildi.",
    'Görev, insanlı Ay programının kritik aşamalarından biri olarak görülüyor.',
    'Uluslararası medya olayı geniş şekilde izledi.',
  ],
  whyItMatters:
    'Uzay programları, teknoloji yatırımları ve uluslararası prestij açısından uzun vadeli etkiler yaratabilir.',
  sources: ['BBC News', 'CBS News'],
  promptText:
    'Use Remotion best practices. Create a cinematic editorial science master video with a calm, readable sound-off structure and a sense of mission-scale momentum.',
  formatHint: 'Cinematic editorial science explainer',
  storyAngle: 'A major moon mission redefines the next phase of human spaceflight',
  visualBrief: 'Use mission timelines, launch status markers, orbital rings, and clear newsroom typography.',
  motionTreatment: 'Slow orbital drift, layered depth, and subtle scale pulls.',
  transitionStyle: 'Soft ring tunnels, luminous fades, and precise timeline morphs.',
  tone: 'Awe-inspiring, factual, and forward-looking',
  sceneSequence: [
    'Open with the rocket ignition and a bold moon mission headline.',
    'Explain the launch milestone with mission timeline graphics.',
    'Close with the broader significance for future lunar exploration.',
  ],
  designKeywords: ['orbital graphics', 'editorial science', 'soft glow', 'timeline cards'],
  mustInclude: ['Artemis II launch', 'moon mission milestone'],
  avoid: ['Sensational sci-fi visuals', 'Publisher branding'],
  durationSeconds: 22,
  visualAssets: [
    {
      asset_id: 'asset-1',
      url: 'https://ichef.bbci.co.uk/ace/standard/1600/cpsprodpb/2b5b/live/2229bdd0-2e23-11f1-b297-95b0a0a8331e.jpg',
      kind: 'article_image',
      source_article_id: 'sample-article-1',
      source_name: 'BBC News',
      alt_text: 'Artemis II launch at liftoff',
    },
  ],
  videoContent: null,
  videoPlan: {
    title: 'Artemis II launch opens a new lunar chapter',
    audience_mode: 'sound_off_first',
    master_format: '16:9',
    duration_seconds: 22,
    pacing_hint: 'balanced',
    source_visibility: 'none',
    scenes: [
      {
        scene_id: 'scene-1',
        purpose: 'hook',
        duration_seconds: 10,
        layout_hint: 'full-bleed',
        headline: 'Artemis II opens a new lunar chapter',
        body: 'NASA has launched its first crewed Moon mission in more than 50 years.',
        supporting_points: [],
        key_figures: ['NASA', 'Artemis II', 'Florida'],
        key_data: 'First crewed lunar flight in 50+ years',
        visual_direction: 'Use a dramatic launch silhouette with orbital glow and clean mission typography.',
        motion_direction: 'Slow push-in with luminous ignition bloom.',
        transition_from_previous: 'Cold open',
        source_line: 'BBC News · CBS News',
        asset_ids: ['asset-1'],
      },
      {
        scene_id: 'scene-2',
        purpose: 'context',
        duration_seconds: 12,
        layout_hint: 'timeline',
        headline: 'Why this launch matters for the Moon program',
        body: 'The mission tests systems and crew operations before the next lunar landing attempt.',
        supporting_points: [
          'Launch from Florida',
          'Crewed lunar orbit mission',
          'Pathfinder for Artemis III',
        ],
        key_figures: ['Artemis II', 'Artemis III'],
        key_data: '4 astronauts',
        visual_direction: 'Use mission timeline cards with soft rings and technical labels.',
        motion_direction: 'Measured step-through reveals with subtle parallax.',
        transition_from_previous: 'Ring fade',
        source_line: '',
        asset_ids: [],
      },
    ],
  },
  storyboard: undefined,
});
