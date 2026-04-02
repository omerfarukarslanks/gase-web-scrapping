import { ExternalLink, Lock, Clock } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { Article } from '../../types/article';

interface Props {
  article: Article;
}

function timeAgo(dateStr: string | null): string {
  if (!dateStr) return '';
  const diff = Date.now() - new Date(dateStr).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 60) return `${minutes}dk`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}sa`;
  const days = Math.floor(hours / 24);
  return `${days}g`;
}

export default function ArticleCard({ article }: Props) {
  return (
    <article className="bg-white rounded-lg border border-gray-200 p-4 transition-shadow hover:shadow-md">
      <div className="flex gap-4">
        <Link to={`/articles/${article.id}`} className="flex gap-4 flex-1 min-w-0">
          {article.image_url && (
            <img
              src={article.image_url}
              alt=""
              className="w-24 h-24 object-cover rounded-lg flex-shrink-0"
              onError={(e) => (e.currentTarget.style.display = 'none')}
            />
          )}
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-2">
            <h3 className="font-semibold text-gray-900 line-clamp-2 transition-colors hover:text-blue-700">
              {article.title}
            </h3>
          </div>

          {article.summary && (
            <p className="text-sm text-gray-600 mt-1 line-clamp-2">{article.summary}</p>
          )}

          <div className="flex items-center gap-3 mt-2 text-xs text-gray-500">
            <span className="font-medium text-blue-600">{article.source_name}</span>

            {article.has_paywall && (
              <span className="flex items-center gap-1 text-amber-600">
                <Lock className="w-3 h-3" /> Paywall
              </span>
            )}

            {article.category && (
              <span className="bg-gray-100 px-2 py-0.5 rounded">{article.category}</span>
            )}

            {article.published_at && (
              <span className="flex items-center gap-1">
                <Clock className="w-3 h-3" />
                {timeAgo(article.published_at)}
              </span>
            )}

            {article.author && <span>{article.author}</span>}
          </div>
        </div>
        </Link>
        <a
          href={article.url}
          target="_blank"
          rel="noopener noreferrer"
          className="self-start rounded-full p-2 text-gray-400 transition hover:bg-slate-100 hover:text-gray-700"
          aria-label="Orijinal haberi yeni sekmede ac"
        >
          <ExternalLink className="w-4 h-4" />
        </a>
      </div>
    </article>
  );
}
