import { useQuery } from '@tanstack/react-query';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import { Newspaper, Activity, Database, Clock } from 'lucide-react';
import { fetchDashboardStats } from '../api/sources';
import LoadingSpinner from '../components/common/LoadingSpinner';

function StatCard({
  icon: Icon,
  label,
  value,
  color,
}: {
  icon: React.ElementType;
  label: string;
  value: string | number;
  color: string;
}) {
  return (
    <div className="bg-white rounded-lg border border-gray-200 p-5">
      <div className="flex items-center gap-3">
        <div className={`p-2 rounded-lg ${color}`}>
          <Icon className="w-5 h-5 text-white" />
        </div>
        <div>
          <p className="text-sm text-gray-500">{label}</p>
          <p className="text-2xl font-bold">{value}</p>
        </div>
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const { data: stats, isLoading } = useQuery({
    queryKey: ['dashboard'],
    queryFn: fetchDashboardStats,
    refetchInterval: 60000,
  });

  if (isLoading || !stats) return <LoadingSpinner />;

  return (
    <div>
      <h2 className="text-2xl font-bold mb-6">Dashboard</h2>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <StatCard icon={Newspaper} label="Bugün Çekilen Haberler" value={stats.articles_today} color="bg-blue-600" />
        <StatCard icon={Database} label="Toplam Çekilen Haber" value={stats.total_articles} color="bg-green-600" />
        <StatCard icon={Activity} label="Aktif Kaynaklar" value={`${stats.active_sources}/${stats.total_sources}`} color="bg-purple-600" />
        <StatCard
          icon={Clock}
          label="Son Scrape"
          value={stats.last_scrape_at ? new Date(stats.last_scrape_at).toLocaleTimeString('tr-TR') : '-'}
          color="bg-orange-600"
        />
      </div>

      {stats.articles_by_source.length > 0 && (
        <div className="bg-white rounded-lg border border-gray-200 p-6 mb-8">
          <h3 className="text-lg font-semibold mb-4">Kaynağa Göre Çekilen Haberler (Bugün)</h3>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={stats.articles_by_source}>
              <XAxis dataKey="name" angle={-45} textAnchor="end" height={80} fontSize={12} />
              <YAxis />
              <Tooltip />
              <Bar dataKey="count" fill="#2563eb" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {stats.recent_runs.length > 0 && (
        <div className="bg-white rounded-lg border border-gray-200 p-6">
          <h3 className="text-lg font-semibold mb-4">Son Scrape Islemleri</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200">
                  <th className="text-left py-2 px-3 font-medium text-gray-500">Kaynak</th>
                  <th className="text-left py-2 px-3 font-medium text-gray-500">Durum</th>
                  <th className="text-right py-2 px-3 font-medium text-gray-500">Bulunan</th>
                  <th className="text-right py-2 px-3 font-medium text-gray-500">Yeni</th>
                  <th className="text-right py-2 px-3 font-medium text-gray-500">Sure</th>
                  <th className="text-left py-2 px-3 font-medium text-gray-500">Zaman</th>
                </tr>
              </thead>
              <tbody>
                {stats.recent_runs.map((run) => (
                  <tr key={run.id} className="border-b border-gray-100">
                    <td className="py-2 px-3 font-medium">{run.source_name}</td>
                    <td className="py-2 px-3">
                      <span
                        className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${
                          run.status === 'completed'
                            ? 'bg-green-100 text-green-700'
                            : run.status === 'failed'
                            ? 'bg-red-100 text-red-700'
                            : 'bg-yellow-100 text-yellow-700'
                        }`}
                      >
                        {run.status}
                      </span>
                    </td>
                    <td className="py-2 px-3 text-right">{run.articles_found}</td>
                    <td className="py-2 px-3 text-right">{run.articles_new}</td>
                    <td className="py-2 px-3 text-right">
                      {run.duration_seconds ? `${run.duration_seconds.toFixed(1)}s` : '-'}
                    </td>
                    <td className="py-2 px-3 text-gray-500">
                      {new Date(run.started_at).toLocaleTimeString('tr-TR')}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
