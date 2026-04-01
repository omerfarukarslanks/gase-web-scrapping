export interface Article {
  id: string;
  source_id: string;
  title: string;
  url: string;
  url_hash: string;
  summary: string | null;
  content_snippet: string | null;
  author: string | null;
  published_at: string | null;
  scraped_at: string;
  image_url: string | null;
  category: string | null;
  tags: string[] | null;
  language: string;
  source_category: string;
  created_at: string;
  source_name: string | null;
  source_slug: string | null;
  has_paywall: boolean;
}

export interface ArticleListResponse {
  items: Article[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

export interface ArticleFilters {
  source?: string;
  category?: string;
  source_category?: string;
  search?: string;
  from_date?: string;
  to_date?: string;
  page?: number;
  per_page?: number;
}
