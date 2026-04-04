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
  voiceover?: string;
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
  master_format: '16:9' | '9:16';
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
  voiceover?: string;
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

export interface PlanningDebugAngleScore {
  angle_type: string;
  quality_status: 'publishable' | 'review' | 'reject';
  quality_score: number;
  reasons: string[];
}

export interface PlanningDebug {
  primary_angle_type: string;
  alternate_angle_type: string | null;
  alternate_video_plan_summary: string;
  angle_scores: PlanningDebugAngleScore[];
}

export type ContentCategory =
  | 'world'
  | 'politics'
  | 'business'
  | 'economy'
  | 'technology'
  | 'sports'
  | 'culture'
  | 'arts'
  | 'science'
  | 'environment'
  | 'health'
  | 'opinion'
  | 'analysis'
  | 'general';
export type StrategyDomain =
  | ContentCategory
  | 'crime_legal'
  | 'diplomacy';
export type PrimaryOutput = 'vertical_video' | 'carousel';
export type VoiceoverMode = 'native' | 'hybrid' | 'text_only';
export type HookStyle = 'urgent' | 'authority' | 'curiosity' | 'human' | 'explainer' | 'analysis';
export type StrategyPacing = 'fast' | 'balanced' | 'measured';
export type VisualPolicy =
  | 'real_asset_first'
  | 'data_card'
  | 'demo_explainer'
  | 'scoreboard'
  | 'human_centered'
  | 'quote_visual'
  | 'symbolic_reconstruction'
  | 'restrained_drama';
export type ClaimPolicy =
  | 'standard_fact_voice'
  | 'attributed_claims'
  | 'analysis_attribution'
  | 'medical_caution'
  | 'opinion_attribution';
export type SensitivityLevel = 'low' | 'medium' | 'high';
export type StoryFamily =
  | 'result_update'
  | 'profile_feature'
  | 'preview_watchlist'
  | 'schedule_listing'
  | 'betting_pick'
  | 'conflict_breaking'
  | 'disaster_update'
  | 'legal_case'
  | 'court_ruling'
  | 'consumer_impact'
  | 'institutional_review'
  | 'obituary_profile'
  | 'culture_controversy'
  | 'commentary_recap'
  | 'policy_shift'
  | 'social_trend'
  | 'opinion_editorial'
  | 'rescue_operation'
  | 'general_update';
export type PlanningStatus = 'produce' | 'review' | 'carousel_only' | 'skip';
export type EditorialIntent = 'break' | 'explain' | 'profile' | 'memorial' | 'debate' | 'guide' | 'warning' | 'watchlist';
export type LayoutFamily =
  | 'scoreboard_stack'
  | 'hero_detail_stack'
  | 'panel_listing_stack'
  | 'map_casualty_stack'
  | 'document_context_stack'
  | 'quote_context_stack'
  | 'price_impact_stack'
  | 'timeline_stack'
  | 'memorial_profile_stack'
  | 'reaction_split_stack'
  | 'rescue_sequence_stack'
  | 'generic_story_stack';
export type RiskFlag =
  | 'conflict_or_casualty'
  | 'legal_allegation'
  | 'election_process'
  | 'medical_claim'
  | 'minor_involved'
  | 'opinion_content'
  | 'gambling_content'
  | 'hate_speech_context'
  | 'obituary_sensitive'
  | 'speculative_claim';
export type EvidenceLevel = 'full_text' | 'summary_only' | 'headline_only';
export type UncertaintyLevel = 'confirmed' | 'mixed' | 'speculative';
export type SceneGoal = 'hook' | 'setup' | 'main_fact' | 'context' | 'impact' | 'reaction' | 'close';
export type VisualType = 'action_photo' | 'portrait' | 'scoreboard' | 'map' | 'document' | 'quote_card' | 'data_card' | 'timeline' | 'symbolic';
export type SafeVoiceRule = 'fact_voice' | 'attributed' | 'opinion_labeled';

export interface ContentStrategy {
  primary_category: ContentCategory;
  secondary_categories: ContentCategory[];
  strategy_domain: StrategyDomain;
  primary_output: PrimaryOutput;
  secondary_outputs: PrimaryOutput[];
  viewer_language: string;
  voiceover_mode: VoiceoverMode;
  hook_style: HookStyle;
  pacing: StrategyPacing;
  visual_policy: VisualPolicy;
  claim_policy: ClaimPolicy;
  sensitivity_level: SensitivityLevel;
  human_review_required: boolean;
  review_reasons: string[];
}

export interface StoryFactPackV3 {
  core_event: string;
  what_changed: string;
  why_now: string;
  key_entities: string[];
  key_numbers: string[];
  key_locations: string[];
  time_reference: string;
  source_attribution: string;
  evidence_level: EvidenceLevel;
  uncertainty_level: UncertaintyLevel;
}

export interface PlanningDecision {
  status: PlanningStatus;
  story_family: StoryFamily;
  editorial_intent: EditorialIntent;
  layout_family: LayoutFamily;
  scene_count: number;
  risk_flags: RiskFlag[];
  reason: string;
}

export interface SceneBlueprint {
  goal: SceneGoal;
  visual_type: VisualType;
  must_include: string[];
  safe_voice_rule: SafeVoiceRule;
}

export interface VerticalVideoBlueprint {
  target_duration_seconds: number;
  scene_blueprints: SceneBlueprint[];
}

export interface CarouselBlueprint {
  slide_count: number;
  cover_angle: string;
  slide_goals: string[];
}

export interface OutputBlueprint {
  vertical_video: VerticalVideoBlueprint | null;
  carousel: CarouselBlueprint | null;
}

export interface VerticalVideoSceneOutput {
  scene_id: string;
  start_second: number;
  duration_seconds: number;
  headline: string;
  body: string;
  voiceover: string;
  overlay_text: string;
  visual_direction: string;
}

export interface VerticalVideoOutput {
  aspect_ratio: '9:16';
  target_platforms: Array<'youtube_shorts' | 'instagram_reels' | 'tiktok'>;
  duration_seconds: number;
  hook: string;
  title: string;
  tts_script: string;
  overlay_text: string[];
  scenes: VerticalVideoSceneOutput[];
  caption: string;
  hashtags: string[];
}

export interface CarouselCardOutput {
  title: string;
  body: string;
  kicker: string;
  image_prompt: string;
}

export interface CarouselOutput {
  cover: CarouselCardOutput;
  slides: CarouselCardOutput[];
  caption: string;
  hashtags: string[];
}

export interface ImagePromptOutput {
  usage: 'cover' | 'scene' | 'supporting';
  prompt: string;
}

export interface PlatformOutputs {
  vertical_video: VerticalVideoOutput | null;
  carousel: CarouselOutput | null;
  image_prompts: ImagePromptOutput[];
}

export interface TopicBrief {
  topic_id: string;
  category: ContentCategory;
  secondary_categories: ContentCategory[];
  aggregation_type: 'shared' | 'unique';
  story_language: string;
  editorial_type: string;
  quality_status: 'publishable' | 'review';
  quality_score: number;
  review_reasons: string[];
  video_quality_status: 'publishable' | 'review' | 'reject';
  video_quality_score: number;
  video_review_reasons: string[];
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
  strategy: ContentStrategy;
  platform_outputs: PlatformOutputs;
  story_fact_pack?: StoryFactPackV3 | null;
  planning_decision?: PlanningDecision | null;
  output_blueprint?: OutputBlueprint | null;
  remotion_storyboard: RemotionStoryboard;
  planning_debug?: PlanningDebug | null;
}

export interface TopicGroup {
  category: ContentCategory;
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
  video_publishable_topics_generated: number;
  video_review_topics_generated: number;
  video_rejected_topics_generated: number;
  rejected_unique_candidates: number;
  dropped_unique_articles: number;
  source_breakdown: AnalysisSourceDebug[];
  cluster_previews: AnalysisClusterDebug[];
  rejection_breakdown: { reason: string; count: number }[];
  review_breakdown: { reason: string; count: number }[];
  video_review_breakdown: { reason: string; count: number }[];
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
  debug?: boolean;
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
  video_publishable_topics: number;
  video_review_topics: number;
  video_rejected_topics: number;
  feedback_count: number;
  feedback_coverage_percent: number;
  score_distribution: TopicQualityScoreBand[];
  rejection_breakdown: TopicQualityReasonCount[];
  input_rejection_breakdown: TopicQualityReasonCount[];
  review_breakdown: TopicQualityReasonCount[];
  video_review_breakdown: TopicQualityReasonCount[];
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
  category: ContentCategory;
  aggregation_type: 'shared' | 'unique';
  quality_status: 'publishable' | 'review';
  quality_score: number;
  video_quality_status: 'publishable' | 'review' | 'reject';
  video_quality_score: number;
  source_count: number;
  article_count: number;
  sources: string[];
  source_slugs: string[];
  review_reasons: string[];
  video_review_reasons: string[];
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
  category: ContentCategory | null;
  totals: TopicScoreTuningTotals;
  current_weights: Record<string, number>;
  recommendations: TopicScoreWeightRecommendation[];
  calibration_summary: TopicScoreTuningCalibrationSummary;
  mismatch_samples: TopicScoreTuningMismatchSamples;
  notes: string[];
}

export interface RemotionPromptPayload {
  headline: string;
  category: ContentCategory;
  secondaryCategories?: ContentCategory[];
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
  strategy?: ContentStrategy | null;
  platformOutputs?: PlatformOutputs | null;
  storyFactPack?: StoryFactPackV3 | null;
  planningDecision?: PlanningDecision | null;
  outputBlueprint?: OutputBlueprint | null;
  storyboard: RemotionStoryboard;
}
