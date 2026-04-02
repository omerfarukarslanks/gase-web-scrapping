from fastapi import APIRouter

from app.api.v1 import analysis, articles, sources, scrape_runs

api_router = APIRouter()

api_router.include_router(articles.router, prefix="/articles", tags=["articles"])
api_router.include_router(analysis.router, prefix="/analysis", tags=["analysis"])
api_router.include_router(sources.router, prefix="/sources", tags=["sources"])
api_router.include_router(scrape_runs.router, prefix="/scrape-runs", tags=["scrape-runs"])
