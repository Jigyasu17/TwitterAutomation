import pytest
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock
from app.domain.models import StoryData, StorySourceData, ResearchReportData, ResearchSourceData, ResearchFactData, ResearchConflictData
from app.repositories.sqlite.story_repository import SQLStoryRepository
from app.repositories.sqlite.research_repository import SQLResearchRepository
from app.repositories.firestore.story_repository import FirestoreStoryRepository
from app.repositories.firestore.research_repository import FirestoreResearchRepository

# --- Mock Firestore Client for Offline Contract Testing ---

class MockDocumentSnapshot:
    def __init__(self, doc_id, data, doc_ref=None):
        self.id = doc_id
        self._data = data
        self.exists = data is not None
        self.reference = doc_ref

    def to_dict(self):
        return self._data

class MockDocumentReference:
    def __init__(self, doc_id, data_store, path):
        self.id = doc_id
        self.data_store = data_store
        self.path = path
        self.reference = self

    def get(self):
        return MockDocumentSnapshot(self.id, self.data_store.get(self.path), self)

    def set(self, data):
        self.data_store[self.path] = data

    def delete(self):
        if self.path in self.data_store:
            del self.data_store[self.path]

    def collection(self, col_name):
        return MockCollectionReference(self.data_store, f"{self.path}/{col_name}")

class MockCountQuery:
    def __init__(self, docs):
        self.docs = docs

    def get(self):
        agg = MagicMock()
        agg.value = len(self.docs)
        return [[agg]]

class MockQueryBuilder:
    def __init__(self, data_store, path, filters=None, orders=None, limit_val=None, offset_val=0):
        self.data_store = data_store
        self.path = path
        self.filters = filters or []
        self.orders = orders or []
        self.limit_val = limit_val
        self.offset_val = offset_val

    def where(self, field, op, value):
        new_filters = self.filters + [(field, op, value)]
        return MockQueryBuilder(self.data_store, self.path, new_filters, self.orders, self.limit_val, self.offset_val)

    def order_by(self, field, direction=None):
        new_orders = self.orders + [(field, direction)]
        return MockQueryBuilder(self.data_store, self.path, self.filters, new_orders, self.limit_val, self.offset_val)

    def limit(self, val):
        return MockQueryBuilder(self.data_store, self.path, self.filters, self.orders, val, self.offset_val)

    def offset(self, val):
        return MockQueryBuilder(self.data_store, self.path, self.filters, self.orders, self.limit_val, val)

    def count(self):
        return MockCountQuery(self.get())

    def get(self):
        docs = []
        for p, data in self.data_store.items():
            if "/" not in self.path:
                # Collection group match
                parts = p.split("/")
                if len(parts) >= 2 and parts[-2] == self.path:
                    docs.append((parts[-1], data))
            else:
                if "/" in p:
                    parent_path, doc_id = p.rsplit("/", 1)
                    if parent_path == self.path:
                        docs.append((doc_id, data))

        # Apply filters
        for field, op, value in self.filters:
            filtered = []
            for doc_id, data in docs:
                val = data.get(field)
                match = False
                if op == "==":
                    match = (val == value)
                elif op == "in":
                    match = (val in value)
                elif op == "!=":
                    match = (val != value)
                elif op == ">=":
                    match = (val is not None and val >= value)
                elif op == "<":
                    match = (val is not None and val < value)
                if match:
                    filtered.append((doc_id, data))
            docs = filtered

        # Apply orders (simple mock sort)
        for field, direction in self.orders:
            docs.sort(key=lambda x: x[1].get(field) if x[1].get(field) is not None else "", reverse=True)

        # Apply offset and limit
        if self.offset_val:
            docs = docs[self.offset_val:]
        if self.limit_val:
            docs = docs[:self.limit_val]

        snapshots = []
        for doc_id, data in docs:
            doc_path = f"{self.path}/{doc_id}"
            doc_ref = MockDocumentReference(doc_id, self.data_store, doc_path)
            snapshots.append(MockDocumentSnapshot(doc_id, data, doc_ref))
        return snapshots

class MockCollectionReference(MockQueryBuilder):
    def __init__(self, data_store, path):
        super().__init__(data_store, path)

    def document(self, doc_id=None):
        if doc_id is None:
            doc_id = str(uuid.uuid4())[:8]
        return MockDocumentReference(doc_id, self.data_store, f"{self.path}/{doc_id}")

class MockBatch:
    def __init__(self, client):
        self.client = client
        self.deletes = []

    def delete(self, doc_ref):
        self.deletes.append(doc_ref)

    def commit(self):
        for ref in self.deletes:
            ref.delete()

class MockFirestoreClient:
    def __init__(self):
        self.data_store = {}

    def collection(self, col_name):
        return MockCollectionReference(self.data_store, col_name)

    def collection_group(self, col_name):
        return MockQueryBuilder(self.data_store, col_name)

    def batch(self):
        return MockBatch(self)


# --- Shared Contracts Executions ---

def execute_story_contract(story_repo):
    """Executes identical story repository behavior contracts."""
    # 1. Save new story
    story = StoryData(
        title="India Startup surge DRHP",
        source_name="MoneyControl",
        source_url="https://moneycontrol.com",
        article_url="https://moneycontrol.com/drhp-surge",
        published_at=datetime.now(timezone.utc),
        category="INVESTMENT",
        content_hash="hash_contract_test",
        status="NEW",
        final_score=85,
        importance_score=80,
        postability_score=90
    )
    story.sources.append(StorySourceData(
        source_name="MoneyControl",
        url="https://moneycontrol.com/drhp-surge",
        published_at=story.published_at,
        title=story.title
    ))
    
    saved = story_repo.save(story)
    assert saved.id is not None
    assert saved.title == "India Startup surge DRHP"
    
    # 2. Retrieve by ID
    fetched = story_repo.get_by_id(saved.id)
    assert fetched is not None
    assert str(fetched.id) == str(saved.id)
    assert len(fetched.sources) == 1
    
    # 3. Retrieve by URL
    fetched_url = story_repo.get_by_url("https://moneycontrol.com/drhp-surge")
    assert fetched_url is not None
    assert str(fetched_url.id) == str(saved.id)
    
    # 4. Retrieve by hash
    fetched_hash = story_repo.get_by_hash("hash_contract_test")
    assert fetched_hash is not None
    assert str(fetched_hash.id) == str(saved.id)
    
    # 5. List and unprocessed
    unprocessed = story_repo.get_unprocessed_new()
    assert len(unprocessed) >= 1
    assert any(str(u.id) == str(saved.id) for u in unprocessed)
    
    # 6. Update Status
    saved.status = "APPROVED"
    updated = story_repo.save(saved)
    assert updated.status == "APPROVED"
    
    # 7. Aggregate metrics stats
    stats = story_repo.get_stats()
    assert stats["total_articles"] >= 1
    assert stats["unique_events"] >= 1

def execute_research_contract(research_repo, story_id):
    """Executes identical research repository behavior contracts."""
    # 1. Create blank report
    report = research_repo.create_report(story_id=story_id, status="QUEUED")
    assert report.id is not None
    assert str(report.story_id) == str(story_id)
    assert report.status == "QUEUED"
    
    # 2. Retrieve report
    fetched = research_repo.get_report_by_id(report.id)
    assert fetched is not None
    assert str(fetched.story_id) == str(story_id)
    
    fetched_story = research_repo.get_report_by_story_id(story_id)
    assert fetched_story is not None
    assert str(fetched_story.id) == str(report.id)
    
    # 3. Save report details
    report.status = "COMPLETED"
    report.what_happened = "Rule-based analysis report output text summary."
    report.why_it_matters = "IPO surge factors."
    saved = research_repo.save_report(report)
    assert saved.status == "COMPLETED"
    
    # 4. Save and fetch sources cache
    source = ResearchSourceData(
        report_id=report.id,
        source_name="Mint",
        title="Mint IPO report",
        url="https://livemint.com/ipo-report",
        source_type="CRAWLED",
        priority=1
    )
    saved_src = research_repo.save_source(source)
    assert saved_src.id is not None
    
    cached_src = research_repo.get_source_by_url(report.id, "https://livemint.com/ipo-report")
    assert cached_src is not None
    assert str(cached_src.id) == str(saved_src.id)
    
    # 5. Save facts and conflicts
    fact = ResearchFactData(
        report_id=report.id,
        fact_type="VALUATION",
        original_value="2500 crore",
        normalized_value="25000000000",
        currency="INR",
        confidence=95
    )
    saved_fact = research_repo.save_fact(fact)
    assert saved_fact.id is not None
    
    conflict = ResearchConflictData(
        report_id=report.id,
        conflict_type="DIVERGING_DATES",
        fact_type="IPO_DATE",
        source_a="Mint",
        value_a="September 10",
        source_b="VCCircle",
        value_b="September 15",
        severity="HIGH",
        status="OPEN"
    )
    saved_conf = research_repo.save_conflict(conflict)
    assert saved_conf.id is not None
    
    # Fetch unresolved open conflicts
    unresolved = research_repo.get_unresolved_conflicts(report.id)
    assert len(unresolved) == 1
    assert str(unresolved[0].id) == str(saved_conf.id)
    
    # 6. Clear facts and conflicts
    research_repo.clear_report_facts_and_conflicts(report.id)
    unresolved_after = research_repo.get_unresolved_conflicts(report.id)
    assert len(unresolved_after) == 0


# --- Pytest Contract Runner Triggers ---

def test_sqlite_story_contract(db_session):
    """Runs StoryRepository contracts against SQLite adapter."""
    story_repo = SQLStoryRepository(db_session)
    execute_story_contract(story_repo)

def test_sqlite_research_contract(db_session):
    """Runs ResearchRepository contracts against SQLite adapter."""
    research_repo = SQLResearchRepository(db_session)
    execute_research_contract(research_repo, story_id=123)

def test_firestore_story_contract():
    """Runs StoryRepository contracts against mocked Firestore adapter."""
    mock_client = MockFirestoreClient()
    story_repo = FirestoreStoryRepository(client=mock_client)
    execute_story_contract(story_repo)

def test_firestore_research_contract():
    """Runs ResearchRepository contracts against mocked Firestore adapter."""
    mock_client = MockFirestoreClient()
    research_repo = FirestoreResearchRepository(client=mock_client)
    execute_research_contract(research_repo, story_id="story_firestore_123")
