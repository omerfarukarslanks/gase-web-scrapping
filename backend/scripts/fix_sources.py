"""
AFP'yi DB'den kaldirir, France 24 ekler.
Reuters ve AP News feed URL'lerini gunceller.
WSJ zaten calisiyor, dokunulmaz.
"""
import asyncio

from sqlalchemy import delete, select

from app.db.session import async_session_factory
from app.models import Article, ScrapeRun, Source  # noqa: F401 - registers all models
from scripts.seed_sources import SOURCES

# Kaldırılacak kaynaklar (slug listesi)
# lequipe: 404, cricbuzz: 403, globo: 404
REMOVE_SLUGS = ["lequipe", "cricbuzz", "globo"]

# Eklenecek yeni kaynaklar (seed_sources.py'den slug ile secilir)
ADD_SLUGS = []

# Guncellenecek feed'ler (slug -> yeni rss_feeds listesi)
UPDATE_FEEDS = {
    slug: next((s["rss_feeds"] for s in SOURCES if s["slug"] == slug), None)
    for slug in ["apnews", "france24", "aljazeera", "ft", "marca"]
}


async def fix():
    async with async_session_factory() as session:

        # 1. Eski kaynaklari kaldir (article + scrape_run + source)
        for slug in REMOVE_SLUGS:
            result = await session.execute(select(Source).where(Source.slug == slug))
            source = result.scalar_one_or_none()
            if not source:
                print(f"  [SKIP] '{slug}' zaten DB'de yok")
                continue

            # Once ilgili article'lari sil
            art_del = await session.execute(
                delete(Article).where(Article.source_id == source.id)
            )
            print(f"  [DELETE] {source.name} — {art_del.rowcount} makale silindi")

            # Scrape run'lari sil
            run_del = await session.execute(
                delete(ScrapeRun).where(ScrapeRun.source_id == source.id)
            )
            print(f"  [DELETE] {source.name} — {run_del.rowcount} scrape run silindi")

            # Kaynagi sil
            await session.delete(source)
            print(f"  [DELETE] '{slug}' kaynagi DB'den kaldirildi")

        # 2. Feed'leri guncelle
        for slug, new_feeds in UPDATE_FEEDS.items():
            if not new_feeds:
                print(f"  [SKIP] '{slug}' icin seed_sources.py'de tanim bulunamadi")
                continue
            result = await session.execute(select(Source).where(Source.slug == slug))
            source = result.scalar_one_or_none()
            if not source:
                print(f"  [SKIP] '{slug}' DB'de bulunamadi")
                continue
            old_count = len(source.rss_feeds or [])
            source.rss_feeds = new_feeds
            print(f"  [UPDATE] {source.name} — {old_count} feed -> {len(new_feeds)} feed")

        # 3. Yeni kaynaklari ekle
        for slug in ADD_SLUGS:
            source_data = next((s for s in SOURCES if s["slug"] == slug), None)
            if not source_data:
                print(f"  [SKIP] '{slug}' seed_sources.py'de tanimli degil")
                continue
            existing = await session.execute(select(Source).where(Source.slug == slug))
            if existing.scalar_one_or_none():
                print(f"  [SKIP] '{slug}' zaten DB'de mevcut")
                continue
            source = Source(
                scraper_type="rss",
                scrape_interval_minutes=60,
                rate_limit_rpm=10,
                is_active=True,
                **source_data,
            )
            session.add(source)
            print(f"  [ADD] '{source_data['name']}' eklendi")

        await session.commit()
        print("\nTamamlandi!")


if __name__ == "__main__":
    asyncio.run(fix())
