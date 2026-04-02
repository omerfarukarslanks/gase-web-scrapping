import apiClient from './client';
import type {
  TopicBriefFilters,
  TopicBriefsResponse,
  TopicFeedbackDeleteResponse,
  TopicFeedbackResponse,
  TopicFeedbackUpsertRequest,
  TopicQualityReportResponse,
  TopicScoreTuningReportResponse,
} from '../types/analysis';

export async function fetchTopicBriefs(filters: TopicBriefFilters): Promise<TopicBriefsResponse> {
  const params = Object.fromEntries(
    Object.entries(filters).filter(([_, value]) => value !== undefined && value !== '')
  );
  const { data } = await apiClient.get('/analysis/topic-briefs', { params });
  return data;
}

export async function fetchTopicQualityReport(
  filters: Omit<TopicBriefFilters, 'limit_topics' | 'include_review'>
): Promise<TopicQualityReportResponse> {
  const params = Object.fromEntries(
    Object.entries(filters).filter(([_, value]) => value !== undefined && value !== '')
  );
  const { data } = await apiClient.get('/analysis/topic-quality-report', { params });
  return data;
}

export async function saveTopicFeedback(payload: TopicFeedbackUpsertRequest): Promise<TopicFeedbackResponse> {
  const { data } = await apiClient.put('/analysis/topic-feedback', payload);
  return data;
}

export async function deleteTopicFeedback(topicId: string): Promise<TopicFeedbackDeleteResponse> {
  const { data } = await apiClient.delete(`/analysis/topic-feedback/${topicId}`);
  return data;
}

export async function fetchTopicScoreTuningReport(filters: {
  days?: number;
  source_category?: string;
  category?: string;
}): Promise<TopicScoreTuningReportResponse> {
  const params = Object.fromEntries(
    Object.entries(filters).filter(([_, value]) => value !== undefined && value !== '')
  );
  const { data } = await apiClient.get('/analysis/topic-score-tuning-report', { params });
  return data;
}
