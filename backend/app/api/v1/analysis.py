from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.analysis import (
    TopicBriefsResponse,
    TopicFeedbackDeleteResponse,
    TopicFeedbackResponse,
    TopicFeedbackUpsertRequest,
    TopicQualityReportResponse,
    TopicScoreTuningReportResponse,
)
from app.services.topic_analysis import (
    delete_topic_feedback,
    generate_topic_briefs,
    generate_topic_quality_report,
    generate_topic_score_tuning_report,
    upsert_topic_feedback,
)

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
    include_review: bool = Query(False),
    debug: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    return await generate_topic_briefs(
        db,
        source_category=source_category,
        category=category,
        hours=hours,
        limit_topics=limit_topics,
        include_review=include_review,
        include_debug=debug,
    )


@router.get("/topic-quality-report", response_model=TopicQualityReportResponse)
async def topic_quality_report(
    source_category: SourceCategory | None = None,
    category: ContentCategory | None = None,
    hours: int = Query(1, ge=1, le=168),
    db: AsyncSession = Depends(get_db),
):
    return await generate_topic_quality_report(
        db,
        source_category=source_category,
        category=category,
        hours=hours,
    )


@router.put("/topic-feedback", response_model=TopicFeedbackResponse)
async def topic_feedback(
    payload: TopicFeedbackUpsertRequest,
    db: AsyncSession = Depends(get_db),
):
    return await upsert_topic_feedback(db, payload)


@router.delete("/topic-feedback/{topic_id}", response_model=TopicFeedbackDeleteResponse)
async def remove_topic_feedback(
    topic_id: str,
    db: AsyncSession = Depends(get_db),
):
    return await delete_topic_feedback(db, topic_id)


@router.get("/topic-score-tuning-report", response_model=TopicScoreTuningReportResponse)
async def topic_score_tuning_report(
    source_category: SourceCategory | None = None,
    category: ContentCategory | None = None,
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    return await generate_topic_score_tuning_report(
        db,
        source_category=source_category,
        category=category,
        days=days,
    )
