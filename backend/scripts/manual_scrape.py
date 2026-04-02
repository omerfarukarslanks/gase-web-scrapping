"""Manuel scrape script - tum aktif kaynaklari aninda scrape eder."""
import asyncio
import sys

from sqlalchemy import select

from app.db.session import async_session_factory, engine
from app.models import Article, ScrapeRun, Source  # noqa: F401
from app.services.scraper_orchestrator import scrape_source


async def run(slug: str | None = None):
    engine.echo = False
    async with async_session_factory() as db:
        summary = []

        if slug:
            result = await db.execute(select(Source).where(Source.slug == slug))
            source = result.scalar_one_or_none()
            if not source:
                print(f"Kaynak bulunamadi: {slug}")
                return
            print(f"[1/1] {source.name} ({source.slug}) scrape basladi...", flush=True)
            run = await scrape_source(db, source)
            await db.commit()
            summary.append(
                {
                    "source": source.name,
                    "status": run.status,
                    "found": run.articles_found,
                    "new": run.articles_new,
                    "duration": run.duration_seconds,
                    "method": run.discovery_method_used,
                }
            )
            sure = f"{run.duration_seconds:.1f}s" if run.duration_seconds else "-"
            print(
                f"[1/1] tamamlandi: durum={run.status} bulunan={run.articles_found} "
                f"yeni={run.articles_new} yontem={run.discovery_method_used or '-'} sure={sure}",
                flush=True,
            )
        else:
            result = await db.execute(
                select(Source)
                .where(Source.is_active.is_(True))
                .order_by(Source.name.asc())
            )
            sources = list(result.scalars().all())
            total = len(sources)

            for index, source in enumerate(sources, start=1):
                print(f"[{index}/{total}] {source.name} ({source.slug}) scrape basladi...", flush=True)
                run = await scrape_source(db, source)
                summary.append(
                    {
                        "source": source.name,
                        "status": run.status,
                        "found": run.articles_found,
                        "new": run.articles_new,
                        "duration": run.duration_seconds,
                        "method": run.discovery_method_used,
                    }
                )
                await db.commit()

                sure = f"{run.duration_seconds:.1f}s" if run.duration_seconds else "-"
                print(
                    f"[{index}/{total}] tamamlandi: durum={run.status} bulunan={run.articles_found} "
                    f"yeni={run.articles_new} yontem={run.discovery_method_used or '-'} sure={sure}",
                    flush=True,
                )

    print(f"\n{'='*72}")
    print(f"{'Kaynak':<20} {'Durum':<12} {'Bulunan':>8} {'Yeni':>6} {'Yontem':<14} {'Sure':>8}")
    print(f"{'='*72}")
    for row in summary:
        sure = f"{row['duration']:.1f}s" if row["duration"] else "-"
        print(
            f"{row['source']:<20} "
            f"{row['status']:<12} "
            f"{row['found']:>8} "
            f"{row['new']:>6} "
            f"{(row['method'] or '-'): <14}"
            f"{sure:>8}"
        )
    print(f"{'='*72}")
    print(f"Toplam {len(summary)} kaynak islendi.")


if __name__ == "__main__":
    slug = sys.argv[1] if len(sys.argv) > 1 else None
    asyncio.run(run(slug))
