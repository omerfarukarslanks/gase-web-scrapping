from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.analysis import TopicBriefsResponse
from app.services.topic_analysis import generate_topic_briefs

router = APIRouter()

SourceCategory = Literal["general", "finance", "sports"]
ContentCategory = Literal[
    "world",
    "politics",
    "business",
    "technology",
    "sports",
    "entertainment",
    "science",
    "health",
    "opinion",
    "general",
]


@router.get("/topic-briefs", response_model=TopicBriefsResponse)
async def topic_briefs(
    source_category: SourceCategory | None = None,
    category: ContentCategory | None = None,
    hours: int = Query(1, ge=1, le=168),
    limit_topics: int = Query(10, ge=1, le=50),
    debug: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    return await generate_topic_briefs(
        db,
        source_category=source_category,
        category=category,
        hours=hours,
        limit_topics=limit_topics,
        include_debug=debug,
    )
