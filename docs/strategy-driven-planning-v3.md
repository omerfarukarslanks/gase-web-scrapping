# Strategy-Driven Planning V3

Bu dokuman, mevcut `strategy + platform_outputs + video_plan` yapisini koruyarak,
haberleri once dogru sekilde "anlayan", sonra uygun output formatina yonlendiren
bir V3 planning contract onerir.

Amac:

- Ham `category` alanina fazla bagimli kalmamak
- Her haberi zorla ayni 3 sahneli short formatina sokmamak
- Hassas haberlerde risk/review kararini sistematiklestirmek
- Frontend layout secimini icerik tipine baglamak
- Mevcut `TopicBrief`, `strategy`, `platform_outputs`, `video_plan`,
  `video_content` alanlariyla geriye donuk uyumlulugu korumak

Bu taslak mevcut backend yapisina additif olarak dusunulmustur.

## 1. Tasarim Ilkeleri

V3 pipeline su sirayla calismalidir:

1. `article preprocessing`
2. `fact extraction`
3. `planning decision`
4. `strategy normalization`
5. `output blueprint generation`
6. `platform output rendering`
7. `legacy compatibility hydration`

Ana fikir:

- Ilk model gecisi metin yazari degil, planner gibi davranmali
- Once "bu haber ne?" karari alinmali
- Sonra "buna hangi format uygun?" karari alinmali
- En son "hangi metin ve sahnelerle anlatayim?" sorusuna gecilmeli

## 2. Problem Ozetleri

Mevcut veri setinde asagidaki sorunlar var:

- `category` alani tutarsiz: `1`, `20`, `Report`, `Real Madrid`, `News`
- `content_text` icinde boilerplate cok fazla:
  - score blocks
  - recommended stories
  - letters boilerplate
  - editorial footer
  - CTA / subscription / watch links
- Ayni category altinda cok farkli story behavior var:
  - `sports` = result, profile, preview, betting
  - `general` = war, court, rescue, TV listing
- Bazi icerikler short video icin uygun degil:
  - guest listings
  - letters roundups
  - pure opinion editorials

Bu nedenle V3'te canonical `content category` kalmali, ama asil editor karari
`story_family` uzerinden verilmelidir.

## 3. Onerilen Yeni Enum'lar

### 3.1 StoryFamily

```python
StoryFamily = Literal[
    "result_update",
    "profile_feature",
    "preview_watchlist",
    "schedule_listing",
    "betting_pick",
    "conflict_breaking",
    "disaster_update",
    "legal_case",
    "court_ruling",
    "consumer_impact",
    "institutional_review",
    "obituary_profile",
    "culture_controversy",
    "commentary_recap",
    "policy_shift",
    "social_trend",
    "opinion_editorial",
    "rescue_operation",
    "general_update",
]
```

### 3.2 PlanningStatus

```python
PlanningStatus = Literal[
    "produce",
    "review",
    "carousel_only",
    "skip",
]
```

### 3.3 EditorialIntent

```python
EditorialIntent = Literal[
    "break",
    "explain",
    "profile",
    "memorial",
    "debate",
    "guide",
    "warning",
    "watchlist",
]
```

### 3.4 LayoutFamily

Bu enum frontend preview ve Remotion renderer tarafinda dikey layout secimini
kontrol etmelidir.

```python
LayoutFamily = Literal[
    "scoreboard_stack",
    "hero_detail_stack",
    "panel_listing_stack",
    "map_casualty_stack",
    "document_context_stack",
    "quote_context_stack",
    "price_impact_stack",
    "timeline_stack",
    "memorial_profile_stack",
    "reaction_split_stack",
    "rescue_sequence_stack",
    "generic_story_stack",
]
```

### 3.5 RiskFlag

```python
RiskFlag = Literal[
    "conflict_or_casualty",
    "legal_allegation",
    "election_process",
    "medical_claim",
    "minor_involved",
    "opinion_content",
    "gambling_content",
    "hate_speech_context",
    "obituary_sensitive",
    "speculative_claim",
]
```

### 3.6 EvidenceLevel / UncertaintyLevel

```python
EvidenceLevel = Literal[
    "full_text",
    "summary_only",
    "headline_only",
]

UncertaintyLevel = Literal[
    "confirmed",
    "mixed",
    "speculative",
]
```

### 3.7 Blueprint Enum'lari

```python
SceneGoal = Literal[
    "hook",
    "setup",
    "main_fact",
    "context",
    "impact",
    "reaction",
    "close",
]

VisualType = Literal[
    "action_photo",
    "portrait",
    "scoreboard",
    "map",
    "document",
    "quote_card",
    "data_card",
    "timeline",
    "symbolic",
]

SafeVoiceRule = Literal[
    "fact_voice",
    "attributed",
    "opinion_labeled",
]
```

## 4. Onerilen Pydantic Taslagi

Bu siniflar mevcut `ContentStrategy` ve `PlatformOutputs`'un ustune eklenmelidir.

```python
from typing import Literal
from pydantic import BaseModel, Field


class StoryFactPackV3(BaseModel):
    core_event: str = ""
    what_changed: str = ""
    why_now: str = ""
    key_entities: list[str] = Field(default_factory=list)
    key_numbers: list[str] = Field(default_factory=list)
    key_locations: list[str] = Field(default_factory=list)
    time_reference: str = ""
    source_attribution: str = ""
    evidence_level: EvidenceLevel = "full_text"
    uncertainty_level: UncertaintyLevel = "confirmed"


class PlanningDecision(BaseModel):
    status: PlanningStatus = "produce"
    story_family: StoryFamily = "general_update"
    editorial_intent: EditorialIntent = "break"
    layout_family: LayoutFamily = "generic_story_stack"
    scene_count: int = Field(default=3, ge=1, le=6)
    risk_flags: list[RiskFlag] = Field(default_factory=list)
    reason: str = ""


class SceneBlueprint(BaseModel):
    goal: SceneGoal
    visual_type: VisualType
    must_include: list[str] = Field(default_factory=list)
    safe_voice_rule: SafeVoiceRule = "fact_voice"


class VerticalVideoBlueprint(BaseModel):
    target_duration_seconds: int = Field(default=15, ge=8, le=45)
    scene_blueprints: list[SceneBlueprint] = Field(default_factory=list)


class CarouselBlueprint(BaseModel):
    slide_count: int = Field(default=4, ge=2, le=8)
    cover_angle: str = ""
    slide_goals: list[str] = Field(default_factory=list)


class OutputBlueprint(BaseModel):
    vertical_video: VerticalVideoBlueprint | None = None
    carousel: CarouselBlueprint | None = None


class TopicBriefV3Mixin(BaseModel):
    story_fact_pack: StoryFactPackV3 = Field(default_factory=StoryFactPackV3)
    planning_decision: PlanningDecision = Field(default_factory=PlanningDecision)
    output_blueprint: OutputBlueprint = Field(default_factory=OutputBlueprint)
```

## 5. TopicBrief Uzerindeki Hedef Durum

Mevcut `TopicBrief` korunur; sadece su alanlar eklenir:

```python
class TopicBrief(BaseModel):
    ...
    strategy: ContentStrategy = Field(default_factory=ContentStrategy)
    platform_outputs: PlatformOutputs = Field(default_factory=PlatformOutputs)

    story_fact_pack: StoryFactPackV3 = Field(default_factory=StoryFactPackV3)
    planning_decision: PlanningDecision = Field(default_factory=PlanningDecision)
    output_blueprint: OutputBlueprint = Field(default_factory=OutputBlueprint)
```

Boylece:

- mevcut API tuketicileri bozulmaz
- eski preview hattini `video_plan` ile calistirmaya devam ederiz
- yeni planlayici kararlarini ayri alanlarda goruruz

## 6. Story Family -> Strategy Varsayimlari

Asagidaki mapping backend tarafinda canonical default olarak tutulabilir.

| story_family | default primary_output | default layout_family | review default |
| --- | --- | --- | --- |
| `result_update` | `vertical_video` | `scoreboard_stack` | no |
| `profile_feature` | `vertical_video` | `hero_detail_stack` | no |
| `preview_watchlist` | `vertical_video` | `hero_detail_stack` | no |
| `schedule_listing` | `carousel` | `panel_listing_stack` | no |
| `betting_pick` | `carousel` | `quote_context_stack` | yes |
| `conflict_breaking` | `vertical_video` | `map_casualty_stack` | yes |
| `disaster_update` | `vertical_video` | `map_casualty_stack` | yes |
| `legal_case` | `carousel` | `document_context_stack` | yes |
| `court_ruling` | `carousel` | `document_context_stack` | no |
| `consumer_impact` | `carousel` | `price_impact_stack` | no |
| `institutional_review` | `carousel` | `document_context_stack` | no |
| `obituary_profile` | `carousel` | `memorial_profile_stack` | no |
| `culture_controversy` | `carousel` | `reaction_split_stack` | yes |
| `commentary_recap` | `carousel` | `quote_context_stack` | yes |
| `policy_shift` | `carousel` | `timeline_stack` | no |
| `social_trend` | `carousel` | `quote_context_stack` | yes |
| `opinion_editorial` | `carousel` | `quote_context_stack` | yes |
| `rescue_operation` | `vertical_video` | `rescue_sequence_stack` | no |
| `general_update` | `vertical_video` | `generic_story_stack` | no |

## 7. Story Family Tespit Kurallari

Bu karar sadece raw `category` ile verilmemelidir. Asagidaki sinyaller
beraber kullanilmalidir:

- normalized source category
- source slug
- headline pattern
- `editorial_type`
- fact pack fields
- article full text
- boilerplate temizligi sonrasi kalan body yapisi

Ornek heuristic'ler:

### 7.1 Sports

- Skor, dakika, attendance, gol listesi varsa `result_update`
- "returns", "proves he belongs", "profile", quoted player journey varsa `profile_feature`
- "decisive month", "can he", "ahead of Bayern" gibi ileriye donuk framing varsa `preview_watchlist`
- betting odds, lock, your pick, prediction varsa `betting_pick`

### 7.2 Politics / Legal

- lawsuit, sues, filed, petition, detained, court, judge, subpoenas varsa
  `legal_case` veya `court_ruling`
- opinion/editorial/column markers varsa `opinion_editorial`

### 7.3 World / Conflict / Disaster

- shot down, killed, missing crew, clashes, airstrike, conflict escalation varsa
  `conflict_breaking`
- earthquake, flood, deaths, alert, rescue, aftershocks varsa `disaster_update`

### 7.4 Culture / Commentary

- TV recap, comedian reaction, late-night monologue varsa `commentary_recap`
- artist comeback + controversy + public reaction varsa `culture_controversy`

### 7.5 Obituary

- "obituary", "has died aged", legacy profile structure varsa `obituary_profile`

### 7.6 Skip / Low-fit Cases

Asagidaki tipler dogrudan `skip` veya `carousel_only` olmalidir:

- guest listings
- pure letters
- multi-topic roundup
- weak-fact teaser pages
- betting tips if product scope does not want gambling-style packaging

## 8. Planning Decision Kurallari

`planning_decision.status` icin backend risk wrapper su mantigi izlemelidir:

### 8.1 `skip`

- low information
- teaser/roundup page
- output icin yeterli concrete fact yok
- repeated boilerplate, unique development yok

### 8.2 `carousel_only`

- list-style icerik
- guest/program schedule
- cizelge ve panel duyurulari
- opinion/commentary recap

### 8.3 `review`

Asagidaki durumlarda varsayilan:

- `conflict_breaking`
- `disaster_update`
- `legal_case`
- `opinion_editorial`
- `betting_pick`
- `culture_controversy`
- `social_trend` + minors
- `medical_claim`
- `election_process`

### 8.4 `produce`

- clear result
- clear consumer impact
- clean court ruling
- rescue story with concrete facts
- profile/preview stories with low sensitivity

## 9. Output Blueprint Mantigi

`output_blueprint`, modeli serbest metin yazmaktan once sinirlamalidir.

Ornek:

```json
{
  "vertical_video": {
    "target_duration_seconds": 15,
    "scene_blueprints": [
      {
        "goal": "hook",
        "visual_type": "scoreboard",
        "must_include": ["hero name", "result"],
        "safe_voice_rule": "fact_voice"
      },
      {
        "goal": "context",
        "visual_type": "action_photo",
        "must_include": ["turning point"],
        "safe_voice_rule": "fact_voice"
      },
      {
        "goal": "impact",
        "visual_type": "data_card",
        "must_include": ["standings impact"],
        "safe_voice_rule": "fact_voice"
      }
    ]
  }
}
```

Bu katmanin faydasi:

- frontend hangi layout'u cizecegini bilir
- 9:16 bos kalmaz, alt alan ne ile dolacak en bastan bilinir
- her story family kendi sahne mantigina kavusur

## 10. Platform Output Uretim Kurallari

`platform_outputs` artik dogrudan planner kararina baglanmalidir.

### 10.1 Vertical Video

- `planning_decision.status in {"produce", "review"}`
- `strategy.primary_output == "vertical_video"`
- `output_blueprint.vertical_video is not None`

### 10.2 Carousel

- her zaman fallback olarak üretilebilir
- `carousel_only` durumunda primary output budur

### 10.3 Image Prompts

- her zaman English
- viewer copy language ile karismamali
- prompt source:
  - `story_fact_pack.core_event`
  - `planning_decision.layout_family`
  - `strategy.visual_policy`
  - `output_blueprint.scene_blueprints[*].visual_type`

## 11. Frontend ve Renderer Etkisi

Frontend tarafinda sadece `master_format` bilgisi yetmez.
Asagidaki alanlar UI ve Remotion tarafina gecmelidir:

- `planning_decision.story_family`
- `planning_decision.layout_family`
- `planning_decision.status`
- `planning_decision.risk_flags`
- `output_blueprint`

### 11.1 Neden?

Cunku 9:16 render sorunu sadece boyut degil, sahne semantigi sorunudur.
Asagidaki ornekler farkli layout ister:

- `scoreboard_stack`
  - ustte score/hook
  - altta key moments + standings impact
- `map_casualty_stack`
  - ustte harita/epicenter
  - altta casualties + response + attribution
- `document_context_stack`
  - ustte court/judge/main ruling
  - altta quote + impact + next step
- `memorial_profile_stack`
  - ustte kimdi
  - altta mirasi / neden onemli

## 12. Prompt Contract Onerisi

Ilk Ollama gecisinde final script yerine asagidaki shape istenmelidir:

```json
{
  "story_fact_pack": {},
  "planning_decision": {},
  "strategy": {},
  "output_blueprint": {}
}
```

Ikinci geciste:

```json
{
  "platform_outputs": {
    "vertical_video": {},
    "carousel": {},
    "image_prompts": []
  }
}
```

Bu iki asamali model secimi, tek prompt icinde her seyi ciktirmaktan daha guvenlidir.

## 13. Boilerplate Temizleme Onerileri

Planner kalitesini en cok arttiracak seylerden biri preprocessing'tir.

Temizlenmesi onerilen bloklar:

- `Recommended Stories`
- `WATCH:`
- `READ MORE:`
- newsletter subscription blocks
- CTA / stream / no contract promos
- letters footer
- donation appeal
- Guardian opinion response footer
- sports app / table / fixtures promos

Temizlenmemesi gerekenler:

- scoreline
- timings
- injury return detail
- death toll
- quoted attribution
- legal filing description
- numerical impact

## 14. Eski Alanlarla Uyum Kurallari

V3 eklendikten sonra su alanlar hala uretilecek:

- `category`
- `secondary_categories`
- `strategy`
- `video_plan`
- `video_content`
- `platform_outputs`

### 14.1 Legacy Hydration

`planning_decision` ve `output_blueprint` icinden su sekilde turetiriz:

- `category <- strategy.primary_category`
- `video_plan.master_format <- strategy.primary_output`
- `video_plan.scenes <- platform_outputs.vertical_video.scenes` veya blueprint + facts
- `video_content <- first scene + supporting facts`

## 15. Migration Plan

### Phase 1 - Schema Additions

Dosya:

- `backend/app/schemas/analysis.py`
- `frontend/src/types/analysis.ts`

Yapilacaklar:

- yeni enum'lari ekle
- `StoryFactPackV3`, `PlanningDecision`, `OutputBlueprint` siniflarini ekle
- `TopicBrief` tipine yeni alanlari additif olarak ekle

### Phase 2 - Preprocessing Layer

Dosya:

- `backend/app/services/topic_analysis.py`

Yapilacaklar:

- boilerplate cleaner ekle
- story family tespiti icin helper fonksiyonlari ekle
- low-fit / skip heuristics yaz

### Phase 3 - First-pass Planner

Yapilacaklar:

- Ollama prompt'unu two-pass yap
- pass 1:
  - `story_fact_pack`
  - `planning_decision`
  - `strategy`
  - `output_blueprint`
- backend coercion:
  - enum repair
  - risk override
  - skip/carousel_only enforcement

### Phase 4 - Second-pass Output Generation

Yapilacaklar:

- `platform_outputs` uretimini planner sonucuna bagla
- vertical/carousel content rules'u story family bazli kur

### Phase 5 - Frontend Layout Binding

Dosya:

- `frontend/src/lib/remotionPayload.ts`
- `frontend/src/remotion/PromptVideo.tsx`
- `frontend/src/pages/PromptLibraryPage.tsx`

Yapilacaklar:

- `layout_family` bazli scene rendering
- `status` badge
- `story_family` badge
- review/risk flag UI

### Phase 6 - Tests

Eklenmesi gereken test tipleri:

- enum coercion tests
- story family inference tests
- skip/carousel_only decision tests
- risk override tests
- layout family rendering tests
- legacy hydration tests

## 16. Onerilen Test Ornekleri

Bu ornekler canonical fixture olarak tutulabilir:

- Coventry -> `result_update`, `produce`, `scoreboard_stack`
- Face the Nation guests -> `schedule_listing`, `carousel_only`
- UFC betting -> `betting_pick`, `review` veya `skip`
- Iran jet down -> `conflict_breaking`, `review`
- Powell subpoenas -> `court_ruling`, `carousel`
- Telstra prices -> `consumer_impact`, `carousel`
- obituary set -> `obituary_profile`, `carousel`
- Guardian editorials -> `opinion_editorial`, `review`
- Puerto Rico rescue -> `rescue_operation`, `vertical_video`

## 17. Ne Silinebilir?

V3 icin su alan ya da mantiklar silinebilir veya etkisi azaltilabilir:

- prompt icindeki legacy `social_media_content`
- tek adimda hem angle hem output hem caption hem prompt uretmeye calisan serbest flow
- ham scraped `category`'ye fazla guvenen karar mantigi

Tamamen silinmemesi gerekenler:

- `strategy`
- `platform_outputs`
- `video_plan`
- `video_content`

Cunku bunlar mevcut API ve frontend hattinin omurgasi.

## 18. Karar

Onerilen V3 yonu:

- category-driven degil, `story-family driven`
- one-shot generation degil, `two-pass planning`
- format-first degil, `decision-first`
- renderer-driven degil, `layout-family driven`
- destructive rewrite degil, `additive migration`

Bu model, mevcut sistemin ustune kontrollu sekilde oturur ve haber orneklerinizde
istediginiz "ozel planlama" kalitesine dogru daha saglam ilerler.
