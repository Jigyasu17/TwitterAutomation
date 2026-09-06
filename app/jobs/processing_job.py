import logging
from app.repositories.interfaces import StoryRepository
from app.processing.classifier import (
    classify_category, identify_event_type, extract_entities, calculate_scores,
    resolve_main_company, extract_financial_amount,
)
from app.processing.content_type import classify_content_type

logger = logging.getLogger(__name__)

def run_story_processing(story_repo: StoryRepository) -> int:
    """
    Processes all unprocessed NEW stories in the database.
    Operates strictly via StoryRepository boundaries and plain domain dataclasses.
    """
    unprocessed_stories = story_repo.get_unprocessed_new()
    processed_count = 0
    ready_count = 0
    filtered_count = 0
    noise_count = 0

    for story in unprocessed_stories:
        try:
            # 1. Classification & secondary tags
            category, tags = classify_category(story.title, story.summary or "")
            
            # 2. Event type identification
            event_type = identify_event_type(story.title)
            
            # 3. Entity extraction
            entities = extract_entities(story.title, story.summary or "")
            fin_amount = extract_financial_amount(story.title)
            content_type = classify_content_type(
                story.title, story.summary or "",
                company_count=len(entities.get("Companies", [])),
                has_large_financial_figure=(fin_amount >= 1000.0),
            )
            # Never guess a single subject company for a roundup/calendar
            # covering many companies, and never fall back to a wire
            # service/regulator name that slipped through as story.company
            # from an earlier pass (resolve_main_company only ever returns
            # a real company or None, never a non-company entity).
            main_company = resolve_main_company(entities, content_type=content_type, fallback=story.company)
            main_country = entities["Countries"][0] if entities["Countries"] else story.country
            
            # 4. Scoring calculations (Importance, Postability, Confidence, Final Weighted Score)
            imp_score, post_score, conf_score, final_score, breakdown = calculate_scores(
                story.title,
                story.summary or "",
                story.source_name,
                len(story.sources),
                entities=entities,
                event_type=event_type,
                country=main_country,
                published_at=story.published_at,
            )
            
            # 5. Domain object updates
            story.category = category
            story.event_type = event_type
            story.secondary_tags = tags
            story.entities = entities
            story.company = main_company
            story.country = main_country
            story.importance_score = imp_score
            story.postability_score = post_score
            story.confidence_score = conf_score
            story.final_score = final_score
            story.scoring_breakdown = breakdown
            
            # Move stories below threshold to FILTERED queue (so they are archived/ignored),
            # while stories with score >= 40 go to READY_FOR_REVIEW.
            if final_score >= 40:
                story.status = "READY_FOR_REVIEW"
                ready_count += 1
            else:
                story.status = "FILTERED"
                filtered_count += 1

            if breakdown.get("noise_penalty", 0) > 0:
                noise_count += 1
                logger.info(
                    f"Story #{story.id} noise-penalized ({breakdown['noise_penalty']} pts): "
                    f"{breakdown.get('noise_reasons')} | final_score={final_score} status={story.status}"
                )

            logger.debug(
                f"Scored story #{story.id}: final={final_score} (imp={imp_score}, post={post_score}, "
                f"conf={conf_score}) india_relevance={breakdown.get('india_relevance')} "
                f"source_tier={breakdown.get('source_quality_tier')} status={story.status}"
            )

            story_repo.save(story)
            processed_count += 1
        except Exception as e:
            logger.error(f"Error processing story #{story.id} ({story.title}): {e}", exc_info=True)

    if processed_count > 0:
        logger.info(
            f"Processing run finished. Processed={processed_count} "
            f"ready_for_review={ready_count} filtered={filtered_count} noise_penalized={noise_count}"
        )

    return processed_count
