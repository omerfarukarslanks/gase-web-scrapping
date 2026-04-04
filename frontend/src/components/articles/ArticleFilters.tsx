import { Search, X } from 'lucide-react';
import { useState } from 'react';
import type { ArticleFilters as ArticleFiltersShape } from '../../types/article';
import type { Source } from '../../types/source';

interface Props {
  sources: Source[];
  onFilter: (filters: Partial<ArticleFiltersShape>) => void;
  currentFilters: ArticleFiltersShape;
}

// Kaynak türü (source.category): haberin hangi tür kaynaktan geldiği
const SOURCE_CATEGORIES = [
  { value: 'general', label: 'Genel Haber' },
  { value: 'finance', label: 'Finans / Ekonomi' },
  { value: 'sports', label: 'Spor' },
];

// İçerik kategorisi (article.category): haberin konusu
const CONTENT_CATEGORIES = [
  { value: 'world',         label: '🌍 Dünya' },
  { value: 'politics',      label: '🏛️ Politika' },
  { value: 'business',      label: '💼 İş Dünyası' },
  { value: 'economy',       label: '📈 Ekonomi' },
  { value: 'technology',    label: '💻 Teknoloji' },
  { value: 'sports',        label: '⚽ Spor' },
  { value: 'culture',       label: '🎭 Kültür' },
  { value: 'arts',          label: '🎨 Sanat' },
  { value: 'science',       label: '🔬 Bilim' },
  { value: 'environment',   label: '🌿 Çevre' },
  { value: 'health',        label: '🏥 Sağlık' },
  { value: 'opinion',       label: '✍️ Köşe' },
  { value: 'analysis',      label: '🧠 Analiz' },
  { value: 'general',       label: '📰 Genel' },
];

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
    <div className="bg-white rounded-lg border border-gray-200 p-4 mb-6 space-y-3">
      {/* Arama + Kaynak + Temizle */}
      <div className="flex flex-wrap items-center gap-3">
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
          <option value="">Tüm Kaynaklar</option>
          {sources.map((s) => (
            <option key={s.slug} value={s.slug}>
              {s.name}
            </option>
          ))}
        </select>

        {hasFilters && (
          <button
            onClick={clearFilters}
            className="flex items-center gap-1 px-3 py-2 text-sm text-red-600 hover:bg-red-50 rounded-lg transition-colors"
          >
            <X className="w-4 h-4" /> Temizle
          </button>
        )}
      </div>

      {/* Kaynak Türü + İçerik Kategorisi */}
      <div className="flex flex-wrap gap-3">
        {/* Kaynak Türü */}
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-500 font-medium whitespace-nowrap">Kaynak Türü:</span>
          <div className="flex flex-wrap gap-1">
            {SOURCE_CATEGORIES.map(({ value, label }) => (
              <button
                key={value}
                onClick={() =>
                  onFilter({
                    ...currentFilters,
                    source_category: currentFilters.source_category === value ? undefined : value,
                  })
                }
                className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                  currentFilters.source_category === value
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        {/* İçerik Kategorisi */}
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-500 font-medium whitespace-nowrap">Konu:</span>
          <div className="flex flex-wrap gap-1">
            {CONTENT_CATEGORIES.map(({ value, label }) => (
              <button
                key={value}
                onClick={() =>
                  onFilter({
                    ...currentFilters,
                    category: currentFilters.category === value ? undefined : value,
                  })
                }
                className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                  currentFilters.category === value
                    ? 'bg-indigo-600 text-white'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
