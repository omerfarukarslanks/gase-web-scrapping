"""Update script - mevcut kaynaklarin rss_feeds alanini seed_sources.py'deki son haliyle gunceller."""
import asyncio

from sqlalchemy import select

from app.db.session import async_session_factory
from app.models import Article, ScrapeRun, Source  # noqa: F401 - registers all models
from scripts.seed_sources import SOURCES


async def update():
    async with async_session_factory() as session:
        updated = 0
        skipped = 0

        for source_data in SOURCES:
            result = await session.execute(
                select(Source).where(Source.slug == source_data["slug"])
            )
            source = result.scalar_one_or_none()

            if not source:
                print(f"  [SKIP] '{source_data['slug']}' veritabaninda bulunamadi — once 'make seed' calistirin.")
                skipped += 1
                continue

            old_feeds = source.rss_feeds or []
            new_feeds = source_data["rss_feeds"]

            # URL setlerini karsilastir (dict veya string formatina bakilmaksizin)
            def extract_urls(feeds):
                return {f["url"] if isinstance(f, dict) else f for f in feeds}

            if extract_urls(old_feeds) == extract_urls(new_feeds):
                print(f"  [OK]   {source_data['name']} — degisiklik yok")
                continue

            source.rss_feeds = new_feeds
            updated += 1
            print(f"  [UPDATE] {source_data['name']}")
            print(f"           Eski: {len(old_feeds)} feed  →  Yeni: {len(new_feeds)} feed")

        await session.commit()
        print(f"\nTamamlandi: {updated} kaynak guncellendi, {skipped} kaynak atlatildi.")


if __name__ == "__main__":
    asyncio.run(update())
