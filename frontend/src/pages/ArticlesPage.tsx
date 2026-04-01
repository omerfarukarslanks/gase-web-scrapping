import { useQuery } from '@tanstack/react-query';
import { fetchArticles } from '../api/articles';
import { fetchSources } from '../api/sources';
import ArticleList from '../components/articles/ArticleList';
import ArticleFilters from '../components/articles/ArticleFilters';
import Pagination from '../components/common/Pagination';
import LoadingSpinner from '../components/common/LoadingSpinner';
import { useArticleStore } from '../stores/articleStore';

export default function ArticlesPage() {
  const { filters, setFilters } = useArticleStore();

  const { data: sources = [] } = useQuery({
    queryKey: ['sources'],
    queryFn: fetchSources,
  });

  const { data, isLoading } = useQuery({
    queryKey: ['articles', filters],
    queryFn: () => fetchArticles(filters),
  });

  return (
    <div>
      <h2 className="text-2xl font-bold mb-6">Haberler</h2>

      <ArticleFilters
        sources={sources}
        currentFilters={filters}
        onFilter={(f) => setFilters(f)}
      />

      {isLoading ? (
        <LoadingSpinner />
      ) : data ? (
        <>
          <div className="text-sm text-gray-500 mb-4">
            {data.total} haber bulundu
          </div>
          <ArticleList articles={data.items} />
          <Pagination
            page={data.page}
            pages={data.pages}
            onPageChange={(page) => setFilters({ page })}
          />
        </>
      ) : null}
    </div>
  );
}
