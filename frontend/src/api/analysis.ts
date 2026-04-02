import apiClient from './client';
import type { TopicBriefFilters, TopicBriefsResponse } from '../types/analysis';

export async function fetchTopicBriefs(filters: TopicBriefFilters): Promise<TopicBriefsResponse> {
  const params = Object.fromEntries(
    Object.entries(filters).filter(([_, value]) => value !== undefined && value !== '')
  );
  const { data } = await apiClient.get('/analysis/topic-briefs', { params });
  return data;
}
