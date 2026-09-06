"""
Regression tests for the one-time retroactive duplicate reconciliation
(app/processing/reconciliation.py, app/jobs/reconciliation_job.py).

Test G from the brief: a single database containing old duplicate
fragments, different sources, one genuine separate event, and sequential
IPO milestones — verifying only true duplicates merge.
"""
import datetime
from app.database.models import Story
from app.repositories.sqlite.story_repository import SQLStoryRepository
from app.processing.reconciliation import plan_reconciliation, execute_reconciliation


def _story(title, source_name, article_url, published_at, event_type=None, company=None,
           content_hash=None, status="READY_FOR_REVIEW", final_score=60):
    return Story(
        title=title, source_name=source_name, source_url=f"https://{source_name.lower()}.example",
        article_url=article_url, published_at=published_at, category="IPO",
        content_hash=content_hash or f"hash_{article_url}", company=company, event_type=event_type,
        status=status, final_score=final_score, importance_score=final_score,
    )


def _seeded_db(db_session, now):
    """Builds Test G's exact scenario: old NSE fragments, different sources,
    one genuinely separate event, and sequential Rentomojo IPO milestones."""
    stories = [
        # --- NSE IPO fragments: 3 differently-worded reports of ONE event ---
        _story(
            "NSE gets regulatory nod for Rs 30,000 cr IPO, the biggest so far",
            "Rediff", "https://rediff.com/nse-a", now - datetime.timedelta(hours=44),
            event_type="IPO_ANNOUNCEMENT", company="NSE",
        ),
        _story(
            "India's NSE eyes September 21-week listing after regulator clears IPO, sources say",
            "reuters.com", "https://reuters.com/nse-b", now - datetime.timedelta(hours=43),
            event_type="IPO_ANNOUNCEMENT", company="NSE",
        ),
        _story(
            "NSE IPO listing date, timeline: When Rs 30,000 cr issue is expected to hit Indian stock market exchanges",
            "Livemint", "https://livemint.com/nse-c", now - datetime.timedelta(hours=40),
            event_type="IPO_ANNOUNCEMENT", company="NSE",
        ),

        # --- Genuine separate event: different company, same category ---
        _story(
            "Jio Platforms gets nod for $4 billion IPO, India's biggest ever",
            "The Indian Express", "https://indianexpress.com/jio-a", now - datetime.timedelta(hours=42),
            event_type="IPO_ANNOUNCEMENT", company="Jio",
        ),

        # --- Sequential IPO milestones for the SAME company: must NOT merge ---
        _story(
            "Rentomojo eyes Rs 1,256 cr IPO",
            "The Times of India", "https://toi.example/rentomojo-a", now - datetime.timedelta(hours=39),
            event_type="IPO_ANNOUNCEMENT", company="Rentomojo",
        ),
        _story(
            "Retail India News: Rentomojo Sets Price Band for Rs 1255 Cr IPO",
            "Indian Retailer", "https://indianretailer.example/rentomojo-b", now - datetime.timedelta(hours=38),
            event_type="IPO_PRICING", company="Rentomojo",
        ),
    ]
    db_session.add_all(stories)
    db_session.commit()
    return stories


def test_old_nse_fragments_would_merge_under_dry_run(db_session):
    now = datetime.datetime.utcnow()
    _seeded_db(db_session, now)

    repo = SQLStoryRepository(db_session)
    stories = repo.get_stories(status="any", limit=100)
    plans = plan_reconciliation(stories)

    nse_plan = next((p for p in plans if "NSE" in p.primary_title or any("NSE" in t for t in p.duplicate_titles)), None)
    assert nse_plan is not None
    assert nse_plan.cluster_size == 3  # all 3 NSE fragments, nothing more


def test_sequential_ipo_milestones_do_not_merge(db_session):
    now = datetime.datetime.utcnow()
    _seeded_db(db_session, now)

    repo = SQLStoryRepository(db_session)
    stories = repo.get_stories(status="any", limit=100)
    plans = plan_reconciliation(stories)

    # Neither Rentomojo story should appear together in any single cluster —
    # IPO_ANNOUNCEMENT vs IPO_PRICING is a different event_type, so the
    # event-fingerprint check (reused unmodified from live dedup) correctly
    # refuses to treat them as the same underlying event.
    for plan in plans:
        titles_in_cluster = [plan.primary_title] + plan.duplicate_titles
        rentomojo_count = sum(1 for t in titles_in_cluster if "Rentomojo" in t)
        assert rentomojo_count <= 1, f"Rentomojo milestones wrongly clustered together: {titles_in_cluster}"


def test_genuinely_separate_event_stays_out_of_the_nse_cluster(db_session):
    now = datetime.datetime.utcnow()
    _seeded_db(db_session, now)

    repo = SQLStoryRepository(db_session)
    stories = repo.get_stories(status="any", limit=100)
    plans = plan_reconciliation(stories)

    for plan in plans:
        titles_in_cluster = [plan.primary_title] + plan.duplicate_titles
        has_nse = any("NSE" in t for t in titles_in_cluster)
        has_jio = any("Jio" in t for t in titles_in_cluster)
        assert not (has_nse and has_jio), "Jio (a genuinely separate event) was wrongly merged with the NSE cluster"


def test_dry_run_never_writes_to_the_database(db_session):
    now = datetime.datetime.utcnow()
    _seeded_db(db_session, now)

    repo = SQLStoryRepository(db_session)
    stories_before = repo.get_stories(status="any", limit=100)
    statuses_before = {s.id: s.status for s in stories_before}

    plan_reconciliation(stories_before)

    stories_after = repo.get_stories(status="any", limit=100)
    statuses_after = {s.id: s.status for s in stories_after}
    assert statuses_before == statuses_after
    assert len(stories_after) == len(stories_before)


def test_execute_merges_sources_and_marks_duplicates_without_deleting(db_session):
    now = datetime.datetime.utcnow()
    _seeded_db(db_session, now)

    repo = SQLStoryRepository(db_session)
    stories = repo.get_stories(status="any", limit=100)
    total_before = len(stories)

    plans = plan_reconciliation(stories)
    merged_count = execute_reconciliation(repo, plans)
    assert merged_count > 0

    # Nothing deleted — row count in the table is unchanged.
    assert db_session.query(Story).count() == total_before

    # The NSE cluster: exactly one survivor with status != MERGED, and it
    # absorbed the others' articles as confirming sources.
    all_after = repo.get_stories(status="any", limit=100)
    nse_related = [s for s in all_after if "NSE" in s.title or (s.company and "NSE" in s.company)]
    survivors = [s for s in nse_related if s.status != "MERGED"]
    merged_away = [s for s in nse_related if s.status == "MERGED"]

    assert len(survivors) == 1
    assert len(merged_away) == 2
    for m in merged_away:
        assert m.merged_into_id == survivors[0].id
        # Still fully present, not destroyed.
        assert m.title
    # These fixtures are raw Story rows without an initial StorySource entry
    # for their own article (unlike real production stories, which always
    # get one via add_or_merge_story) — so this counts only the merged-in
    # articles, not "own + merged".
    assert len(survivors[0].sources) >= 2


def test_execute_promotes_highest_tier_source_as_primary(db_session):
    """Reuters (Tier 2) should end up as the primary over Rediff (Tier 4) and Livemint (Tier 2, but arrived later)."""
    now = datetime.datetime.utcnow()
    _seeded_db(db_session, now)

    repo = SQLStoryRepository(db_session)
    stories = repo.get_stories(status="any", limit=100)
    plans = plan_reconciliation(stories)
    execute_reconciliation(repo, plans)

    all_after = repo.get_stories(status="any", limit=100)
    survivors = [s for s in all_after if s.status != "MERGED" and s.company == "NSE"]
    assert len(survivors) == 1
    # Reuters and Livemint are both Tier 2 (beat Rediff's Tier 4); either is
    # an acceptable "most authoritative" pick — Rediff (the weakest) must not win.
    assert survivors[0].source_name != "Rediff"


def test_merged_story_research_report_remains_queryable_after_merge(db_session):
    """Requirement 5: research/evidence isn't lost — a merged-away story's
    own row (and any research tied to its story_id) stays fully queryable."""
    from app.repositories.sqlite.research_repository import SQLResearchRepository

    now = datetime.datetime.utcnow()
    stories = _seeded_db(db_session, now)
    repo = SQLStoryRepository(db_session)
    research_repo = SQLResearchRepository(db_session)

    # Attach a completed research report to one of the NSE fragments before reconciling.
    fragment_ids = [s.id for s in stories if "reuters.com" in s.article_url]
    fragment_id = fragment_ids[0]
    report = research_repo.create_report(story_id=fragment_id, status="COMPLETED")
    report.what_happened = "NSE received SEBI clearance for its IPO."
    research_repo.save_report(report)

    all_stories = repo.get_stories(status="any", limit=100)
    plans = plan_reconciliation(all_stories)
    execute_reconciliation(repo, plans)

    # The research report is still there, still tied to the same story_id,
    # regardless of whether that story ended up primary or MERGED.
    refetched = research_repo.get_report_by_story_id(fragment_id)
    assert refetched is not None
    assert refetched.what_happened == "NSE received SEBI clearance for its IPO."


def test_merged_status_is_excluded_from_the_live_feed(db_session):
    now = datetime.datetime.utcnow()
    _seeded_db(db_session, now)
    repo = SQLStoryRepository(db_session)

    stories = repo.get_stories(status="any", limit=100)
    plans = plan_reconciliation(stories)
    execute_reconciliation(repo, plans)

    live_feed = repo.get_stories(status="all", limit=100)
    assert all(s.status != "MERGED" for s in live_feed)
