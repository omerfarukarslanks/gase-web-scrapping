import copy

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from .analysis_test_utils import assert_golden_case, load_golden_cases, seed_case


GOLDEN_CASES = load_golden_cases()


@pytest.mark.asyncio
@pytest.mark.parametrize("case", GOLDEN_CASES, ids=[case["case_id"] for case in GOLDEN_CASES])
async def test_topic_briefs_golden_regression_cases(
    client,
    db_session: AsyncSession,
    monkeypatch,
    case: dict,
) -> None:
    await seed_case(db_session, case)

    async def fake_analyze_cluster(self, cluster, visual_assets=None):
        payloads = copy.deepcopy(case.get("ollama_topics", []))
        if not payloads:
            raise AssertionError(f"Unexpected Ollama call for golden case: {case['case_id']}")

        article_ids = [str(item.article.id) for item in cluster]
        normalized_payloads: list[dict] = []
        for payload in payloads:
            payload.setdefault("article_ids", article_ids)
            normalized_payloads.append(payload)
        return normalized_payloads

    monkeypatch.setattr(
        "app.services.topic_analysis.OllamaTopicAnalyzer.analyze_cluster",
        fake_analyze_cluster,
    )

    params = {
        "hours": case.get("hours", 3),
        "limit_topics": case.get("limit_topics", 10),
        "debug": True,
    }
    if case.get("source_category") is not None:
        params["source_category"] = case["source_category"]
    if case.get("category") is not None:
        params["category"] = case["category"]
    if case.get("include_review") is not None:
        params["include_review"] = case["include_review"]

    response = await client.get("/api/v1/analysis/topic-briefs", params=params)

    assert response.status_code == 200
    payload = response.json()
    assert payload["analysis_status"] == "ok"
    assert_golden_case(payload, case)
