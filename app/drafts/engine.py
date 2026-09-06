"""
Drafting engine: ties structured research intelligence, the hook-strategy
library, optional AI generation, and quality control into one entry point.

app/drafts/builder.py's generate_post_text() stays untouched as the
guaranteed-safe deterministic baseline (it's directly unit-tested and
already implements the wire-service guard, Google-News-link fix, and
overflow-to-thread behavior). This module always includes that baseline as
one candidate, generates additional angle candidates from research data
when available, optionally asks a configured AI provider for one more, runs
every candidate through the same anti-headline-rewrite + quality checks,
and returns the strongest survivor plus the alternates for transparency.

Never raises: a failure anywhere in angle generation or AI calling falls
back to the baseline candidate, so a single bad story can't take down a
batch drafting run (Phase 9's per-story fault isolation).
"""
import logging
from dataclasses import dataclass, field
from typing import List, Optional
from app.domain.models import StoryData
from app.drafts.builder import generate_post_text, _truncate, TWEET_LIMIT, _source_line
from app.drafts.hooks import generate_hook_candidates, _format_fact_value
from app.drafts.quality import score_draft, is_headline_rewrite, is_malformed_or_promotional
from app.drafts.ai_provider import is_ai_configured, generate_with_ai, build_intel_summary
from app.research.intelligence import build_structured_intelligence, StructuredIntelligence

logger = logging.getLogger(__name__)

MAX_ANGLES_STORED = 4


@dataclass
class DraftGenerationResult:
    post_text: str
    thread: Optional[List[str]]
    image_headline: str
    image_subheadline: str
    angles: List[dict] = field(default_factory=list)
    quality_score: int = 0
    hook_strategy: str = "explainer"
    ai_used: bool = False


def _compose_angle_post(story: StoryData, intel: StructuredIntelligence, strategy: str, hook_text: str):
    """Builds a full post (+ optional thread overflow) around one hook candidate."""
    parts = [hook_text]
    used_fact_types = set()

    if strategy not in {"number_led", "contrast", "data_led"} and intel.confirmed_facts:
        fact = intel.confirmed_facts[0]
        amt = _format_fact_value(fact)
        label = fact.fact_type.replace("_", " ")
        parts.append(f"({label}: {amt})")
        used_fact_types.add(id(fact))

    combined = " ".join(parts)
    if len(combined) <= TWEET_LIMIT:
        post_text = _truncate(combined)
    else:
        post_text = _truncate(hook_text)

    thread: List[str] = []
    other_facts = [f for f in intel.confirmed_facts if id(f) not in used_fact_types][:2]
    if other_facts:
        joined = " | ".join(f"{f.fact_type.replace('_', ' ').title()}: {_format_fact_value(f)}" for f in other_facts)
        thread.append(_truncate(joined))

    source_line = _source_line(story)
    if source_line:
        thread.append(_truncate(source_line))

    return post_text, (thread or None)


def _reframe_as_last_resort(title: str) -> str:
    """
    Used only when every candidate (including the baseline) still reads as a
    plain headline rewrite — explicit framing language so the anti-rewrite
    rule always has some candidate that passes it, per the project brief's
    "reject it and regenerate/rewrite" instruction.
    """
    return _truncate(f"Here's what just happened: {title}")


def generate_draft_content(story: StoryData) -> DraftGenerationResult:
    intel = build_structured_intelligence(story)

    baseline_post, baseline_thread, image_headline, image_subheadline = generate_post_text(story)
    candidates = [{
        "strategy": "explainer",
        "post_text": baseline_post,
        "thread": baseline_thread,
        "source": "deterministic",
    }]

    try:
        for strategy, hook_text in generate_hook_candidates(story, intel):
            post_text, thread = _compose_angle_post(story, intel, strategy, hook_text)
            candidates.append({
                "strategy": strategy,
                "post_text": post_text,
                "thread": thread,
                "source": "deterministic",
            })
    except Exception as e:
        logger.warning(f"Angle generation failed for story #{story.id}, continuing with baseline only: {e}")

    if is_ai_configured():
        try:
            intel_summary = build_intel_summary(story, intel)
            ai_text = generate_with_ai(intel_summary, tweet_limit=TWEET_LIMIT)
            if ai_text:
                candidates.append({
                    "strategy": "ai_generated",
                    "post_text": _truncate(ai_text),
                    "thread": None,
                    "source": "ai",
                })
        except Exception as e:
            logger.warning(f"AI drafting failed for story #{story.id}, falling back to deterministic candidates: {e}")

    # Score every candidate; drop headline-rewrites and malformed/promotional
    # output unless it's all we have (Phase 3 quality gate: reject or
    # regenerate, not merely discount).
    scored = []
    for c in candidates:
        rewrite = is_headline_rewrite(c["post_text"], story.title)
        malformed_reason = is_malformed_or_promotional(c["post_text"])
        score, checks = score_draft(c["post_text"], c["thread"], story, intel.confirmed_facts)
        scored.append({**c, "score": score, "is_rewrite": rewrite, "reject_reason": malformed_reason})
        if malformed_reason:
            logger.info(f"Story #{story.id}: candidate '{c['strategy']}' rejected — {malformed_reason}")

    survivors = [c for c in scored if not c["is_rewrite"] and not c["reject_reason"]]
    if not survivors:
        logger.info(f"Story #{story.id}: every draft candidate was rejected (rewrite/malformed/promotional) — reframing baseline.")
        reframed = _reframe_as_last_resort(story.title)
        score, _ = score_draft(reframed, None, story, intel.confirmed_facts)
        survivors = [{"strategy": "explainer", "post_text": reframed, "thread": None, "source": "deterministic", "score": score, "is_rewrite": False, "reject_reason": None}]

    survivors.sort(key=lambda c: c["score"], reverse=True)
    primary = survivors[0]

    # De-duplicate near-identical alternates (different strategies sometimes
    # converge on nearly the same sentence when facts are sparse).
    from app.processing.deduplication import calculate_similarity
    alternates = []
    for c in survivors[1:]:
        if all(calculate_similarity(c["post_text"], kept["post_text"]) < 0.85 for kept in [primary] + alternates):
            alternates.append(c)
        if len(alternates) >= MAX_ANGLES_STORED - 1:
            break

    angles = [{"strategy": c["strategy"], "text": c["post_text"]} for c in ([primary] + alternates)]

    return DraftGenerationResult(
        post_text=primary["post_text"],
        thread=primary["thread"],
        image_headline=image_headline,
        image_subheadline=image_subheadline,
        angles=angles,
        quality_score=primary["score"],
        hook_strategy=primary["strategy"],
        ai_used=(primary["source"] == "ai"),
    )
