import apiClient from './client';
import type { Article, ArticleFilters, ArticleListResponse } from '../types/article';

export async function fetchArticles(filters: ArticleFilters): Promise<ArticleListResponse> {
  const params = Object.fromEntries(
    Object.entries(filters).filter(([_, v]) => v !== undefined && v !== '')
  );
  const { data } = await apiClient.get('/articles', { params });
  return data;
}

export async function fetchTrendingArticles(hours = 24, limit = 20): Promise<Article[]> {
  const { data } = await apiClient.get('/articles/trending', {
    params: { hours, limit },
  });
  return data;
}

export async function fetchArticle(id: string): Promise<Article> {
  const { data } = await apiClient.get(`/articles/${id}`);
  return data;
}
