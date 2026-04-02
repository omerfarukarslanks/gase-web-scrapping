import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, ExternalLink, Lock, RefreshCw } from 'lucide-react';
import { Link, useParams } from 'react-router-dom';
import { fetchArticle } from '../api/articles';
import LoadingSpinner from '../components/common/LoadingSpinner';

function formatDateTime(value: string | null): string {
  if (!value) return 'Tarih yok';
  return new Date(value).toLocaleString('tr-TR');
}

function formatContent(content: string | null): string[] {
  if (!content) return [];
  return content
    .split(/\n{2,}/)
    .map((part) => part.trim())
    .filter(Boolean);
}

export default function ArticleDetailPage() {
  const { articleId } = useParams<{ articleId: string }>();

  const { data, isLoading, isFetching, isError } = useQuery({
    queryKey: ['article-detail', articleId],
    queryFn: () => fetchArticle(articleId ?? ''),
    enabled: Boolean(articleId),
  });

  if (!articleId) {
    return (
      <section className="rounded-3xl border border-dashed border-slate-300 bg-white p-10 text-center">
        <h2 className="text-2xl font-bold text-slate-900">Gecerli bir haber secilmedi</h2>
        <p className="mt-3 text-sm text-slate-600">Listeye donup gecerli bir haber secerek tekrar deneyebilirsin.</p>
      </section>
    );
  }

  if (isLoading && !data) {
    return <LoadingSpinner />;
  }

  if (isError || !data) {
    return (
      <section className="rounded-3xl border border-dashed border-slate-300 bg-white p-10 text-center">
        <h2 className="text-2xl font-bold text-slate-900">Haber detayi yuklenemedi</h2>
        <p className="mt-3 text-sm text-slate-600">Kayit bulunamadi ya da detay zenginlestirme bu istekte tamamlanamadi.</p>
        <Link
          to="/articles"
          className="mt-6 inline-flex items-center gap-2 rounded-2xl bg-slate-950 px-4 py-3 text-sm font-semibold text-white transition hover:bg-slate-800"
        >
          <ArrowLeft className="h-4 w-4" />
          Listeye don
        </Link>
      </section>
    );
  }

  const contentParagraphs = formatContent(data.content_text);

  return (
    <div className="space-y-8">
      <section className="rounded-[32px] bg-slate-950 px-8 py-10 text-white shadow-xl">
        <div className="flex flex-col gap-6 xl:flex-row xl:items-start xl:justify-between">
          <div className="max-w-4xl">
            <div className="flex flex-wrap items-center gap-2 text-xs font-semibold uppercase tracking-[0.18em] text-slate-300">
              <span className="rounded-full bg-white/10 px-3 py-1">{data.source_name ?? 'Kaynak yok'}</span>
              {data.category ? <span className="rounded-full bg-white/10 px-3 py-1">{data.category}</span> : null}
              {data.has_paywall ? (
                <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/20 px-3 py-1 text-amber-200">
                  <Lock className="h-3 w-3" />
                  Paywall
                </span>
              ) : null}
            </div>

            <h1 className="mt-4 text-4xl font-bold tracking-tight">{data.title}</h1>

            {data.summary ? (
              <p className="mt-4 max-w-3xl text-base leading-7 text-slate-200">{data.summary}</p>
            ) : null}

            <div className="mt-5 flex flex-wrap items-center gap-4 text-sm text-slate-300">
              <span>Yayin: {formatDateTime(data.published_at)}</span>
              <span>Kaydedildi: {formatDateTime(data.created_at)}</span>
              {data.author ? <span>Yazar: {data.author}</span> : null}
              {data.detail_fetched_at ? <span>Detay cekildi: {formatDateTime(data.detail_fetched_at)}</span> : null}
            </div>
          </div>

          <div className="flex flex-wrap gap-3">
            <Link
              to="/articles"
              className="inline-flex items-center gap-2 rounded-2xl border border-white/15 px-4 py-3 text-sm font-semibold text-white transition hover:bg-white/10"
            >
              <ArrowLeft className="h-4 w-4" />
              Listeye don
            </Link>
            <a
              href={data.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 rounded-2xl bg-white px-4 py-3 text-sm font-semibold text-slate-900 transition hover:bg-slate-100"
            >
              <ExternalLink className="h-4 w-4" />
              Orijinal kaynaga git
            </a>
          </div>
        </div>
      </section>

      {data.image_url ? (
        <section className="overflow-hidden rounded-[32px] border border-slate-200 bg-white shadow-sm">
          <img src={data.image_url} alt={data.title} className="h-[360px] w-full object-cover" />
        </section>
      ) : null}

      <section className="grid gap-6 xl:grid-cols-[1.5fr_0.5fr]">
        <article className="rounded-[32px] border border-slate-200 bg-white p-8 shadow-sm">
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">Haber metni</p>
              <h2 className="mt-2 text-2xl font-bold tracking-tight text-slate-900">
                {contentParagraphs.length > 0 ? 'Zenginlestirilmis detay' : 'Sinirli detay mevcut'}
              </h2>
            </div>
            {isFetching ? <RefreshCw className="h-5 w-5 animate-spin text-slate-400" /> : null}
          </div>

          {contentParagraphs.length > 0 ? (
            <div className="mt-6 space-y-5 text-base leading-8 text-slate-700">
              {contentParagraphs.map((paragraph, index) => (
                <p key={`${index}-${paragraph.slice(0, 24)}`}>{paragraph}</p>
              ))}
            </div>
          ) : (
            <div className="mt-6 rounded-3xl border border-dashed border-slate-300 bg-slate-50 p-6">
              <p className="text-sm leading-7 text-slate-600">
                Bu haber icin tam metin cekilemedi. Yine de kaynak, tarih ve mevcut ozet bilgileri korunuyor. Daha fazla
                detay icin orijinal kaynaga gidebilirsin.
              </p>
            </div>
          )}
        </article>

        <aside className="space-y-4">
          <section className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">Durum</p>
            <div className="mt-4 space-y-3 text-sm text-slate-700">
              <div className="rounded-2xl bg-slate-50 px-4 py-3">
                <p className="text-xs uppercase tracking-[0.16em] text-slate-500">Detail enriched</p>
                <p className="mt-1 font-semibold text-slate-900">{data.detail_enriched ? 'true' : 'false'}</p>
              </div>
              <div className="rounded-2xl bg-slate-50 px-4 py-3">
                <p className="text-xs uppercase tracking-[0.16em] text-slate-500">Source slug</p>
                <p className="mt-1 font-semibold text-slate-900">{data.source_slug ?? '-'}</p>
              </div>
              <div className="rounded-2xl bg-slate-50 px-4 py-3">
                <p className="text-xs uppercase tracking-[0.16em] text-slate-500">Dil</p>
                <p className="mt-1 font-semibold text-slate-900">{data.language}</p>
              </div>
            </div>
          </section>
        </aside>
      </section>
    </div>
  );
}
