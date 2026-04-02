"""Purge removed sources and their live article data while preserving scrape history."""
import asyncio

from app.db.session import async_session_factory, engine
from app.source_policy import REMOVED_SOURCE_SLUGS
from app.services.source_purge_service import purge_sources_by_slug


async def purge() -> None:
    engine.echo = False
    async with async_session_factory() as session:
        summary = await purge_sources_by_slug(session, REMOVED_SOURCE_SLUGS)
        await session.commit()

    print("Purged removed sources:")
    print(f"  Sources deleted: {summary['sources_deleted']}")
    print(f"  Articles deleted: {summary['articles_deleted']}")
    print(f"  Runs detached: {summary['runs_detached']}")
    print(f"  Deleted slugs: {', '.join(summary['deleted_slugs']) or '-'}")


if __name__ == "__main__":
    asyncio.run(purge())
