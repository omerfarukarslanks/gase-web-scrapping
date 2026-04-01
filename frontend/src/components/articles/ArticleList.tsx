import type { Article } from '../../types/article';
import ArticleCard from './ArticleCard';

interface Props {
  articles: Article[];
}

export default function ArticleList({ articles }: Props) {
  if (articles.length === 0) {
    return (
      <div className="text-center py-12 text-gray-500">
        Haber bulunamadi.
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {articles.map((article) => (
        <ArticleCard key={article.id} article={article} />
      ))}
    </div>
  );
}
