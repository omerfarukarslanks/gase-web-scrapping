import type {
  RemotionPromptPayload,
  RemotionStoryboard,
  StoryboardScene,
  StoryboardSceneType,
  StoryboardStat,
  TopicBrief,
  VideoContent,
  VisualAsset,
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

const PURPOSE_TO_STORYBOARD_TYPE: Record<VideoPlanPurpose, StoryboardSceneType> = {
  hook: 'hook',
  explain: 'story',
  detail: 'detail',
  context: 'story',
  comparison: 'story',
  takeaway: 'outro',
  close: 'outro',
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
  return value;
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
  return Math.min(60, Math.max(8, Math.round(numeric)));
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
  );
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
      headline: scene.headline,
      body: scene.body,
      voiceover: (scene as any).voiceover || scene.body || scene.headline,
      source_line: scene.source_line,
      asset_ids: scene.asset_ids.slice(0, 2),
      visual_elements: scene.visual_direction ? [scene.visual_direction] : [],
      bullet_points: scene.supporting_points,
      stats: stats,
      chips: scene.key_figures,
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
}): VideoPlan {
  const total = clampDuration(fields.durationSeconds, 30);
  const keyData =
    fields.videoContent?.key_data || extractScore([fields.headline, fields.summary, ...fields.keyPoints]) || '';
  const keyFigures = fields.videoContent?.key_figures ?? [];
  const sceneCount = inferSceneCount(fields.summary, fields.keyPoints);
  const sceneDurations = allocateSceneDurations(total, sceneCount, [4, 3, 2].slice(0, sceneCount));
  const primaryAssetId = fields.visualAssets[0]?.asset_id ?? '';
  const secondaryAssetId = fields.visualAssets[1]?.asset_id ?? primaryAssetId;

  const scenes: VideoPlanScene[] = [
    {
      scene_id: 'scene-1',
      purpose: 'hook',
      duration_seconds: sceneDurations[0],
      layout_hint: defaultLayout(fields.category, 'hook', keyData, keyFigures),
      headline: fields.videoContent?.headline || fields.headline,
      body: fields.summary,
      voiceover: fields.summary || fields.headline,
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
    const layout = defaultLayout(fields.category, 'explain', keyData, keyFigures);
    scenes.push({
      scene_id: 'scene-2',
      purpose: 'explain',
      duration_seconds: sceneDurations[1],
      layout_hint: layout,
      headline: fields.keyPoints[0] || fields.summary,
      body: sceneCount === 2 ? fields.summary : '',
      voiceover: fields.keyPoints[0] || fields.summary,
      supporting_points: fields.keyPoints.slice(0, 2),
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
      layout_hint: defaultLayout(fields.category, 'takeaway', '', keyFigures),
      headline: fields.whyItMatters,
      body: fields.whyItMatters,
      voiceover: fields.whyItMatters,
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
    master_format: '16:9',
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
  const headline = cleanString(raw.headline) || cleanString(fallback.headline) || 'Update';

  const finalPurpose = VALID_PURPOSES.has(purpose) ? purpose : 'explain';
  const finalLayout = VALID_LAYOUTS.has(layoutHint) ? layoutHint : 'full-bleed';

  return {
    scene_id: cleanString(raw.scene_id, `scene-${index + 1}`),
    purpose: finalPurpose,
    duration_seconds: Math.max(1, Math.round(Number(raw.duration_seconds) || fallback.duration_seconds || 1)),
    layout_hint: finalLayout,
    headline,
    body: cleanString(raw.body, fallback.body),
    voiceover: cleanString(raw.voiceover, (fallback as any).voiceover || fallback.body),
    supporting_points: cleanStringArray(raw.supporting_points, fallback.supporting_points),
    key_figures: cleanStringArray(raw.key_figures, fallback.key_figures),
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

  const rawFormat = cleanString(raw.master_format);
  const masterFormat = rawFormat === '9:16' ? '9:16' : '16:9';

  return {
    title: cleanString(raw.title, fallback.title),
    audience_mode: 'sound_off_first',
    master_format: masterFormat,
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

function buildPayloadBase(topic: {
  headline: string;
  category: string;
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
  videoPlan?: VideoPlan | null;
  storyboard?: RemotionStoryboard;
}): RemotionPromptPayload {
  const visualAssets = dedupe(
    topic.visualAssets.map((asset) => asset.asset_id)
  )
    .map((assetId) => topic.visualAssets.find((asset) => asset.asset_id === assetId) ?? null)
    .filter((asset): asset is VisualAsset => Boolean(asset));

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
  });

  const videoPlan = normalizeVideoPlan(topic.videoPlan, fallbackVideoPlan, visualAssets);
  const videoContent = topic.videoContent ?? buildVideoContentFromPlan(videoPlan);
  const fallbackStoryboard = buildStoryboardFromPlan(videoPlan);

  return {
    ...topic,
    durationSeconds: videoPlan.duration_seconds,
    visualAssets,
    videoPlan,
    videoContent,
    storyboard: normalizeStoryboard(topic.storyboard, fallbackStoryboard),
  };
}

export function buildRemotionPayload(topic: TopicBrief): RemotionPromptPayload {
  return buildPayloadBase({
    headline: topic.headline_tr,
    category: topic.category,
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
    videoPlan: topic.video_plan,
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
    summary,
    keyPoints: cleanStringArray(payload.keyPoints),
    whyItMatters: cleanString(payload.whyItMatters, 'Bu gelisme kisa vadede gundemi etkileyebilir.'),
    sources: cleanStringArray(payload.sources),
    promptText: cleanString(payload.promptText, headline),
    formatHint: cleanString(payload.formatHint, 'Editorial motion-graphics short'),
    storyAngle: cleanString(payload.storyAngle, headline),
    visualBrief: cleanString(payload.visualBrief, 'Readable motion graphics with labeled facts and clear visual hierarchy.'),
    motionTreatment: cleanString(payload.motionTreatment, 'Clean panel choreography and subtle kinetic typography.'),
    transitionStyle: cleanString(payload.transitionStyle, 'Shape wipes and restrained motion transitions.'),
    tone: cleanString(payload.tone, 'Urgent and factual'),
    sceneSequence: cleanStringArray(payload.sceneSequence, [
      'Open with the main headline and a bold category strap.',
      'Highlight the summary with supporting visuals and data callouts.',
      'Close with why it matters and what to watch next.',
    ]),
    designKeywords: cleanStringArray(payload.designKeywords, ['editorial motion', 'clear typography']),
    mustInclude: cleanStringArray(payload.mustInclude),
    avoid: cleanStringArray(payload.avoid, ['Publisher logos', 'Unsupported claims']),
    durationSeconds: clampDuration(payload.durationSeconds, 30),
    visualAssets: rawVisualAssets
      .map((asset: unknown, index: number) => cleanVisualAsset(asset, `asset-${index + 1}`))
      .filter((asset): asset is VisualAsset => Boolean(asset)),
    videoContent: cleanVideoContent(payload.videoContent),
    videoPlan: (payload.videoPlan ?? payload.video_plan) as VideoPlan | undefined,
    storyboard: payload.storyboard as RemotionStoryboard | undefined,
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
