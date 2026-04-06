from __future__ import annotations

from dataclasses import dataclass, field

from app.schemas.analysis import RemotionScene, RemotionStat, RemotionStoryboard, VideoContent, VideoPlan, VideoPromptParts, VisualAsset

PURPOSE_TO_SCENE_TYPE = {
    "hook": "hook",
    "explain": "story",
    "detail": "detail",
    "context": "story",
    "comparison": "story",
    "takeaway": "outro",
    "close": "outro",
}


def compact_text(value: str | None) -> str:
    return " ".join((value or "").split()).strip()


def truncate_text(value: str, limit: int = 99999) -> str:
    return compact_text(value)


@dataclass(slots=True)
class RemotionStoryboardContext:
    category: str
    headline: str
    summary: str
    key_points: list[str]
    why_it_matters: str
    prompt_text: str
    prompt_parts: VideoPromptParts
    video_plan: VideoPlan
    sources: list[str] = field(default_factory=list)
    representative_titles: list[str] = field(default_factory=list)
    facts: list[str] = field(default_factory=list)
    style_cues: list[str] = field(default_factory=list)
    stats: list[RemotionStat] = field(default_factory=list)
    article_count: int = 0
    video_content: VideoContent | None = None
    visual_assets: list[VisualAsset] = field(default_factory=list)


class RemotionStoryboardService:
    def build_storyboard(self, context: RemotionStoryboardContext) -> RemotionStoryboard:
        return RemotionStoryboard(
            visual_thesis=self._build_visual_thesis(context),
            scenes=self._build_scenes(context),
        )

    def _build_visual_thesis(self, context: RemotionStoryboardContext) -> str:
        return truncate_text(context.video_plan.title or context.headline, 120)

    def _build_scenes(self, context: RemotionStoryboardContext) -> list[RemotionScene]:
        scenes: list[RemotionScene] = []
        for scene in context.video_plan.scenes:
            stats: list[RemotionStat] = []
            if compact_text(scene.key_data):
                stats.append(RemotionStat(label="Key data", value=truncate_text(scene.key_data, 28)))
            if scene.duration_seconds:
                stats.append(RemotionStat(label="Duration", value=f"{scene.duration_seconds}s"))

            scenes.append(
                RemotionScene(
                    scene_type=PURPOSE_TO_SCENE_TYPE.get(scene.purpose, "story"),
                    duration_seconds=scene.duration_seconds,
                    layout_hint=scene.layout_hint,
                    kicker=scene.purpose.upper(),
                    headline=truncate_text(scene.headline, 10000),
                    body=truncate_text(scene.body, 10000),
                    voiceover=getattr(scene, "voiceover", scene.body) or scene.headline,
                    source_line=scene.source_line,
                    asset_ids=scene.asset_ids[:2],
                    visual_elements=[truncate_text(scene.visual_direction, 10000)] if compact_text(scene.visual_direction) else [],
                    bullet_points=[truncate_text(point, 10000) for point in scene.supporting_points[:10]],
                    stats=stats[:2],
                    chips=scene.key_figures[:4],
                )
            )
        return scenes
