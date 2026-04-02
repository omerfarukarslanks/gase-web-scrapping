export interface VideoPromptParts {
  format_hint: string;
  story_angle: string;
  visual_brief: string;
  motion_treatment: string;
  transition_style: string;
  scene_sequence: string[];
  tone: string;
  design_keywords: string[];
  must_include: string[];
  avoid: string[];
  duration_seconds: number;
}

export interface VideoContent {
  headline: string;
  narrative: string[];
  key_figures: string[];
  key_data: string;
  source_line: string;
  duration_seconds: number;
}

export type VideoPlanPurpose = 'hook' | 'explain' | 'detail' | 'context' | 'comparison' | 'takeaway' | 'close';
export type VideoPlanLayoutHint =
  | 'headline'
  | 'split'
  | 'stat'
  | 'timeline'
  | 'quote'
  | 'comparison'
  | 'minimal'
  | 'full-bleed';
export type VideoPlanSourceVisibility = 'none' | 'subtle' | 'contextual';

export interface VideoPlanScene {
  scene_id: string;
  purpose: VideoPlanPurpose;
  duration_seconds: number;
  layout_hint: VideoPlanLayoutHint;
  headline: string;
  body: string;
  supporting_points: string[];
  key_figures: string[];
  key_data: string;
  visual_direction: string;
  motion_direction: string;
  transition_from_previous: string;
  source_line: string;
  asset_ids: string[];
}

export interface VideoPlan {
  title: string;
  audience_mode: 'sound_off_first';
  master_format: '16:9';
  duration_seconds: number;
  pacing_hint: string;
  source_visibility: VideoPlanSourceVisibility;
  scenes: VideoPlanScene[];
}

export interface StoryboardStat {
  label: string;
  value: string;
}

export type StoryboardSceneType = 'hook' | 'story' | 'detail' | 'outro' | 'hero' | 'stat-grid' | 'timeline' | 'style-board' | 'impact';

export interface StoryboardScene {
  scene_type: StoryboardSceneType;
  duration_seconds: number;
  layout_hint: string;
  kicker: string;
  headline: string;
  body: string;
  source_line: string;
  asset_ids: string[];
  visual_elements: string[];
  bullet_points: string[];
  stats: StoryboardStat[];
  chips: string[];
}

export interface RemotionStoryboard {
  visual_thesis: string;
  scenes: StoryboardScene[];
}

export interface TopicRepresentativeArticle {
  id: string;
  title: string;
  url: string;
  source_name: string | null;
  source_slug: string | null;
  published_at: string | null;
  image_url: string | null;
}

export type VisualAssetKind = 'article_image' | 'og_image';

export interface VisualAsset {
  asset_id: string;
  url: string;
  kind: VisualAssetKind;
  source_article_id: string;
  source_name: string | null;
  alt_text: string;
}

export interface TopicBrief {
  topic_id: string;
  category: string;
  aggregation_type: 'shared' | 'unique';
  headline_tr: string;
  summary_tr: string;
  key_points_tr: string[];
  why_it_matters_tr: string;
  confidence: number;
  source_count: number;
  article_count: number;
  sources: string[];
  representative_articles: TopicRepresentativeArticle[];
  visual_assets: VisualAsset[];
  video_prompt_en: string;
  video_prompt_parts: VideoPromptParts;
  video_plan: VideoPlan;
  video_content: VideoContent | null;
  remotion_storyboard: RemotionStoryboard;
}

export interface TopicGroup {
  category: string;
  topics: TopicBrief[];
}

export interface AnalysisSourceDebug {
  source_slug: string;
  source_name: string;
  article_count: number;
}

export interface AnalysisClusterDebug {
  category: string;
  article_count: number;
  source_count: number;
  sources: string[];
  sample_titles: string[];
}

export interface AnalysisDebug {
  fetched_articles: number;
  prepared_articles: number;
  candidate_clusters: number;
  multi_source_clusters: number;
  single_source_clusters: number;
  shared_topics_generated: number;
  unique_topics_generated: number;
  dropped_unique_articles: number;
  source_breakdown: AnalysisSourceDebug[];
  cluster_previews: AnalysisClusterDebug[];
  notes: string[];
  ollama_base_url: string | null;
  ollama_error: string | null;
}

export interface TopicBriefsResponse {
  analysis_status: 'ok' | 'degraded';
  generated_at: string;
  window_start: string;
  window_end: string;
  groups: TopicGroup[];
  debug?: AnalysisDebug | null;
}

export interface TopicBriefFilters {
  source_category?: string;
  category?: string;
  hours?: number;
  limit_topics?: number;
}

export interface RemotionPromptPayload {
  headline: string;
  category: string;
  summary: string;
  keyPoints: string[];
  whyItMatters: string;
  sources: string[];
  promptText: string;
  formatHint: string;
  storyAngle: string;
  visualBrief: string;
  motionTreatment: string;
  transitionStyle: string;
  tone: string;
  sceneSequence: string[];
  designKeywords: string[];
  mustInclude: string[];
  avoid: string[];
  durationSeconds: number;
  visualAssets: VisualAsset[];
  videoPlan: VideoPlan;
  videoContent: VideoContent | null;
  storyboard: RemotionStoryboard;
}
