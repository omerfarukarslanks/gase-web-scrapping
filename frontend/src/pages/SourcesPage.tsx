import { useQuery } from '@tanstack/react-query';
import { CheckCircle, XCircle, Lock, RefreshCw } from 'lucide-react';
import { fetchSources, triggerScrape } from '../api/sources';
import LoadingSpinner from '../components/common/LoadingSpinner';

export default function SourcesPage() {
  const { data: sources, isLoading, refetch } = useQuery({
    queryKey: ['sources'],
    queryFn: fetchSources,
  });

  const handleTrigger = async (slug: string) => {
    await triggerScrape(slug);
    setTimeout(() => refetch(), 2000);
  };

  if (isLoading || !sources) return <LoadingSpinner />;

  const generalSources = sources.filter((s) => s.category === 'general');
  const financeSources = sources.filter((s) => s.category === 'finance');

  const renderTable = (items: typeof sources, title: string) => (
    <div className="bg-white rounded-lg border border-gray-200 p-6 mb-6">
      <h3 className="text-lg font-semibold mb-4">{title}</h3>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200">
              <th className="text-left py-2 px-3 font-medium text-gray-500">Kaynak</th>
              <th className="text-left py-2 px-3 font-medium text-gray-500">Durum</th>
              <th className="text-right py-2 px-3 font-medium text-gray-500">Bugun</th>
              <th className="text-right py-2 px-3 font-medium text-gray-500">Toplam</th>
              <th className="text-left py-2 px-3 font-medium text-gray-500">Son Scrape</th>
              <th className="text-left py-2 px-3 font-medium text-gray-500">Tip</th>
              <th className="text-center py-2 px-3 font-medium text-gray-500">Islem</th>
            </tr>
          </thead>
          <tbody>
            {items.map((source) => (
              <tr key={source.id} className="border-b border-gray-100">
                <td className="py-2 px-3">
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{source.name}</span>
                    {source.has_paywall && (
                      <Lock className="w-3 h-3 text-amber-500" />
                    )}
                  </div>
                  <span className="text-xs text-gray-400">{source.base_url}</span>
                </td>
                <td className="py-2 px-3">
                  {source.is_active ? (
                    <span className="flex items-center gap-1 text-green-600">
                      <CheckCircle className="w-4 h-4" /> Aktif
                    </span>
                  ) : (
                    <span className="flex items-center gap-1 text-gray-400">
                      <XCircle className="w-4 h-4" /> Pasif
                    </span>
                  )}
                </td>
                <td className="py-2 px-3 text-right font-medium">{source.articles_today}</td>
                <td className="py-2 px-3 text-right">{source.total_articles}</td>
                <td className="py-2 px-3 text-gray-500">
                  {source.last_scraped_at
                    ? new Date(source.last_scraped_at).toLocaleString('tr-TR')
                    : '-'}
                </td>
                <td className="py-2 px-3">
                  <span className="bg-gray-100 px-2 py-0.5 rounded text-xs">
                    {source.scraper_type}
                  </span>
                </td>
                <td className="py-2 px-3 text-center">
                  <button
                    onClick={() => handleTrigger(source.slug)}
                    className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-600"
                    title="Manuel scrape tetikle"
                  >
                    <RefreshCw className="w-4 h-4" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );

  return (
    <div>
      <h2 className="text-2xl font-bold mb-6">Kaynaklar</h2>
      {renderTable(generalSources, 'Genel Haber Kaynaklari')}
      {renderTable(financeSources, 'Finans & Ekonomi Kaynaklari')}
    </div>
  );
}
