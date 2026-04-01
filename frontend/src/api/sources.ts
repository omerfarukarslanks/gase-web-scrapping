import apiClient from './client';
import type { DashboardStats, Source, ScrapeRun } from '../types/source';

export async function fetchSources(): Promise<Source[]> {
  const { data } = await apiClient.get('/sources');
  return data;
}

export async function fetchSource(slug: string): Promise<Source> {
  const { data } = await apiClient.get(`/sources/${slug}`);
  return data;
}

export async function triggerScrape(sourceSlug?: string, category?: string) {
  const params: Record<string, string> = {};
  if (sourceSlug) params.source_slug = sourceSlug;
  if (category) params.category = category;
  const { data } = await apiClient.post('/sources/scrape/trigger', null, { params });
  return data;
}

export async function fetchDashboardStats(): Promise<DashboardStats> {
  const { data } = await apiClient.get('/scrape-runs/dashboard');
  return data;
}

export async function fetchScrapeRuns(sourceSlug?: string): Promise<ScrapeRun[]> {
  const params = sourceSlug ? { source_slug: sourceSlug } : {};
  const { data } = await apiClient.get('/scrape-runs', { params });
  return data;
}
