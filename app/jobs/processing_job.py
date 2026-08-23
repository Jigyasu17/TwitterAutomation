import logging
from app.repositories.interfaces import StoryRepository
from app.processing.classifier import classify_category, identify_event_type, extract_entities, calculate_scores

logger = logging.getLogger(__name__)

def run_story_processing(story_repo: StoryRepository) -> int:
    """
    Processes all unprocessed NEW stories in the database.
    Operates strictly via StoryRepository boundaries and plain domain dataclasses.
    """
    unprocessed_stories = story_repo.get_unprocessed_new()
    processed_count = 0
    
    for story in unprocessed_stories:
        try:
            # 1. Classification & secondary tags
            category, tags = classify_category(story.title, story.summary or "")
            
            # 2. Event type identification
            event_type = identify_event_type(story.title)
            
            # 3. Entity extraction
            entities = extract_entities(story.title, story.summary or "")
            main_company = entities["Companies"][0] if entities["Companies"] else story.company
            main_country = entities["Countries"][0] if entities["Countries"] else story.country
            
            # 4. Scoring calculations (Importance, Postability, Confidence, Final Weighted Score)
            imp_score, post_score, conf_score, final_score, breakdown = calculate_scores(
                story.title,
                story.summary or "",
                story.source_name,
                len(story.sources)
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
            else:
                story.status = "FILTERED"
                
            story_repo.save(story)
            processed_count += 1
        except Exception as e:
            logger.error(f"Error processing story #{story.id} ({story.title}): {e}", exc_info=True)
            
    if processed_count > 0:
        logger.info(f"Manual/Auto processing run finished. Processed {processed_count} stories.")
        
    return processed_count
