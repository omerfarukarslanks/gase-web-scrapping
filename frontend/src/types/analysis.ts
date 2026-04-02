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
  quality_status: 'publishable' | 'review';
  quality_score: number;
  review_reasons: string[];
  latest_feedback: TopicLatestFeedback | null;
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

export type FeedbackLabel = 'approved' | 'wrong' | 'boring' | 'malformed';

export interface TopicLatestFeedback {
  label: FeedbackLabel;
  note: string | null;
  updated_at: string;
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
  rejected_articles: number;
  candidate_clusters: number;
  multi_source_clusters: number;
  single_source_clusters: number;
  shared_topics_generated: number;
  unique_topics_generated: number;
  publishable_topics_generated: number;
  review_topics_generated: number;
  rejected_unique_candidates: number;
  dropped_unique_articles: number;
  source_breakdown: AnalysisSourceDebug[];
  cluster_previews: AnalysisClusterDebug[];
  rejection_breakdown: { reason: string; count: number }[];
  review_breakdown: { reason: string; count: number }[];
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
  include_review?: boolean;
}

export interface TopicQualitySampleRejection {
  title: string;
  reason: string;
}

export interface TopicQualitySampleReviewTopic {
  headline: string;
  reasons: string[];
}

export interface TopicQualityScoreBand {
  label: string;
  count: number;
}

export interface TopicQualityScoredTopic {
  headline: string;
  quality_status: 'publishable' | 'review';
  quality_score: number;
}

export interface TopicQualityReasonCount {
  reason: string;
  count: number;
}

export interface TopicFeedbackCount {
  label: FeedbackLabel;
  count: number;
}

export interface TopicQualityTotals {
  fetched_articles: number;
  prepared_articles: number;
  rejected_articles: number;
  candidate_clusters: number;
  publishable_topics: number;
  review_topics: number;
  rejected_topics: number;
  shared_topics: number;
  unique_topics: number;
  avg_quality_score: number;
  publishable_avg_quality_score: number;
  review_avg_quality_score: number;
  feedback_count: number;
  feedback_coverage_percent: number;
  score_distribution: TopicQualityScoreBand[];
  rejection_breakdown: TopicQualityReasonCount[];
  review_breakdown: TopicQualityReasonCount[];
  feedback_breakdown: TopicFeedbackCount[];
}

export interface TopicQualitySourceReport {
  source_slug: string;
  source_name: string;
  article_count: number;
  prepared_article_count: number;
  rejected_article_count: number;
  topic_contributions: number;
  publishable_contributions: number;
  review_contributions: number;
  shared_contributions: number;
  unique_contributions: number;
  avg_quality_score: number;
  publishable_avg_quality_score: number;
  review_avg_quality_score: number;
  rejection_breakdown: TopicQualityReasonCount[];
  review_breakdown: TopicQualityReasonCount[];
  sample_rejections: TopicQualitySampleRejection[];
  sample_review_topics: TopicQualitySampleReviewTopic[];
  lowest_scoring_topics: TopicQualityScoredTopic[];
}

export interface TopicQualityReportResponse {
  analysis_status: 'ok' | 'degraded';
  generated_at: string;
  window_start: string;
  window_end: string;
  totals: TopicQualityTotals;
  sources: TopicQualitySourceReport[];
  notes: string[];
  ollama_error: string | null;
}

export interface TopicFeedbackSnapshotInput {
  headline_tr: string;
  summary_tr: string;
  category: string;
  aggregation_type: 'shared' | 'unique';
  quality_status: 'publishable' | 'review';
  quality_score: number;
  source_count: number;
  article_count: number;
  sources: string[];
  source_slugs: string[];
  review_reasons: string[];
  representative_article_ids: string[];
  has_visual_asset: boolean;
  has_published_at: boolean;
}

export interface TopicFeedbackUpsertRequest {
  topic_id: string;
  feedback_label: FeedbackLabel;
  note?: string | null;
  topic_snapshot: TopicFeedbackSnapshotInput;
}

export interface TopicFeedbackResponse {
  topic_id: string;
  latest_feedback: TopicLatestFeedback;
}

export interface TopicFeedbackDeleteResponse {
  topic_id: string;
  deleted: boolean;
}

export interface TopicScoreWeightRecommendation {
  feature: string;
  current_weight: number;
  recommended_weight: number;
  delta: number;
  active_count: number;
  inactive_count: number;
  approval_rate_when_active: number;
  approval_rate_when_inactive: number;
  lift: number;
}

export interface TopicScoreTuningSample {
  topic_id: string;
  headline_tr: string;
  feedback_label: FeedbackLabel;
  quality_status: 'publishable' | 'review';
  quality_score: number;
}

export interface TopicScoreTuningTotals {
  feedback_count: number;
  approved_count: number;
  negative_count: number;
  eligible_for_recommendations: boolean;
  feedback_breakdown: TopicFeedbackCount[];
}

export interface TopicScoreTuningCalibrationSummary {
  high_score_negative_count: number;
  low_score_approved_count: number;
}

export interface TopicScoreTuningMismatchSamples {
  high_score_negative: TopicScoreTuningSample[];
  low_score_approved: TopicScoreTuningSample[];
}

export interface TopicScoreTuningReportResponse {
  generated_at: string;
  days: number;
  source_category: string | null;
  category: string | null;
  totals: TopicScoreTuningTotals;
  current_weights: Record<string, number>;
  recommendations: TopicScoreWeightRecommendation[];
  calibration_summary: TopicScoreTuningCalibrationSummary;
  mismatch_samples: TopicScoreTuningMismatchSamples;
  notes: string[];
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
