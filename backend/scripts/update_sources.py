"""Update script - mevcut kaynaklarin discovery config'ini seed_sources.py ile senkronize eder."""
import asyncio

from sqlalchemy import select

from app.db.session import async_session_factory, engine
from app.models import Article, ScrapeRun, Source  # noqa: F401 - registers all models
from scripts.seed_sources import SOURCES, build_source_payload


async def update():
    engine.echo = False
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

            payload = build_source_payload(source_data)
            new_feeds = payload.get("rss_feeds", [])
            new_scraper_type = payload.get("scraper_type", "rss")
            new_config = payload.get("config")

            old_feeds = source.rss_feeds or []
            same_feeds = old_feeds == new_feeds
            same_scraper_type = source.scraper_type == new_scraper_type
            same_config = (source.config or None) == (new_config or None)

            if same_feeds and same_scraper_type and same_config:
                print(f"  [OK]   {source_data['name']} — degisiklik yok")
                continue

            source.rss_feeds = new_feeds
            source.scraper_type = new_scraper_type
            source.config = new_config
            updated += 1
            print(f"  [UPDATE] {source_data['name']}")
            print(f"           Feed: {len(old_feeds)} → {len(new_feeds)}")
            print(f"           Scraper: {source.scraper_type}")

        await session.commit()
        print(f"\nTamamlandi: {updated} kaynak guncellendi, {skipped} kaynak atlatildi.")


if __name__ == "__main__":
    asyncio.run(update())
