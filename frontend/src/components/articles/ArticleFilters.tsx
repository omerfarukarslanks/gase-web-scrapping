import { Search, X } from 'lucide-react';
import { useState } from 'react';
import type { Source } from '../../types/source';

interface Props {
  sources: Source[];
  onFilter: (filters: {
    source?: string;
    category?: string;
    source_category?: string;
    search?: string;
  }) => void;
  currentFilters: Record<string, string | undefined>;
}

export default function ArticleFilters({ sources, onFilter, currentFilters }: Props) {
  const [search, setSearch] = useState(currentFilters.search || '');

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    onFilter({ ...currentFilters, search: search || undefined });
  };

  const clearFilters = () => {
    setSearch('');
    onFilter({});
  };

  const hasFilters = Object.values(currentFilters).some(Boolean);

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4 mb-6">
      <div className="flex flex-wrap items-center gap-4">
        <form onSubmit={handleSearch} className="flex-1 min-w-[200px]">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Haber ara..."
              className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
        </form>

        <select
          value={currentFilters.source || ''}
          onChange={(e) => onFilter({ ...currentFilters, source: e.target.value || undefined })}
          className="px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="">Tum Kaynaklar</option>
          {sources.map((s) => (
            <option key={s.slug} value={s.slug}>
              {s.name}
            </option>
          ))}
        </select>

        <select
          value={currentFilters.source_category || ''}
          onChange={(e) =>
            onFilter({ ...currentFilters, source_category: e.target.value || undefined })
          }
          className="px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="">Tum Kategoriler</option>
          <option value="general">Genel</option>
          <option value="finance">Finans</option>
        </select>

        {hasFilters && (
          <button
            onClick={clearFilters}
            className="flex items-center gap-1 px-3 py-2 text-sm text-red-600 hover:bg-red-50 rounded-lg"
          >
            <X className="w-4 h-4" /> Temizle
          </button>
        )}
      </div>
    </div>
  );
}
