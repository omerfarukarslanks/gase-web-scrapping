export interface Source {
  id: string;
  name: string;
  slug: string;
  base_url: string;
  rss_feeds: string[];
  scraper_type: string;
  category: string;
  is_active: boolean;
  scrape_interval_minutes: number;
  rate_limit_rpm: number;
  has_paywall: boolean;
  last_scraped_at: string | null;
  created_at: string;
  updated_at: string;
  articles_today: number;
  total_articles: number;
  last_run_status: string | null;
}

export interface ScrapeRun {
  id: string;
  source_id: string;
  status: string;
  articles_found: number;
  articles_new: number;
  articles_updated: number;
  error_message: string | null;
  started_at: string;
  completed_at: string | null;
  duration_seconds: number | null;
  created_at: string;
  source_name: string | null;
  source_slug: string | null;
}

export interface DashboardStats {
  total_articles: number;
  articles_today: number;
  active_sources: number;
  total_sources: number;
  last_scrape_at: string | null;
  articles_by_source: { name: string; slug: string; count: number }[];
  articles_by_category: { category: string; count: number }[];
  recent_runs: ScrapeRun[];
}
