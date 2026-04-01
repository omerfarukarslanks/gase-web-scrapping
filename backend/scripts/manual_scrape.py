"""Manuel scrape script - tum aktif kaynaklari aninda scrape eder."""
import asyncio
import sys

from sqlalchemy import select

from app.db.session import async_session_factory
from app.models import Article, ScrapeRun, Source  # noqa: F401
from app.services.scraper_orchestrator import scrape_all_sources, scrape_source


async def run(slug: str | None = None):
    async with async_session_factory() as db:
        # Kaynak adlarini ONCEDEN yukle — lazy load yasagi nedeniyle
        all_sources_result = await db.execute(select(Source))
        source_map: dict[str, str] = {
            str(s.id): s.name for s in all_sources_result.scalars().all()
        }

        if slug:
            result = await db.execute(select(Source).where(Source.slug == slug))
            source = result.scalar_one_or_none()
            if not source:
                print(f"Kaynak bulunamadi: {slug}")
                return
            runs = [await scrape_source(db, source)]
        else:
            runs = await scrape_all_sources(db)

        # commit'ten ONCE run verilerini topla (nesne expire olmadan)
        summary = [
            {
                "source": source_map.get(str(r.source_id), str(r.source_id)),
                "status": r.status,
                "found": r.articles_found,
                "new": r.articles_new,
                "duration": r.duration_seconds,
            }
            for r in runs
        ]

        await db.commit()

    print(f"\n{'='*52}")
    print(f"{'Kaynak':<20} {'Durum':<12} {'Bulunan':>8} {'Yeni':>6} {'Sure':>8}")
    print(f"{'='*52}")
    for row in summary:
        sure = f"{row['duration']:.1f}s" if row["duration"] else "-"
        print(
            f"{row['source']:<20} "
            f"{row['status']:<12} "
            f"{row['found']:>8} "
            f"{row['new']:>6} "
            f"{sure:>8}"
        )
    print(f"{'='*52}")
    print(f"Toplam {len(summary)} kaynak islendi.")


if __name__ == "__main__":
    slug = sys.argv[1] if len(sys.argv) > 1 else None
    asyncio.run(run(slug))
