# Firestore Database Mapping Schema

This document maps the MarketPulse plain domain objects to their corresponding Firestore document paths, attribute formats, and subcollection structures.

---

## 1. Document Hierarchies

Firestore is structured as top-level collections containing documents. We will structure our relationships using subcollections to allow natural scalability.

### A. Stories Collection
- **Collection Path**: `stories`
- **Document Path**: `stories/{story_id}`
- **Document Attributes**:
  ```json
  {
    "title": "String",
    "source_name": "String",
    "source_url": "String",
    "article_url": "String",
    "published_at": "Timestamp",
    "collected_at": "Timestamp",
    "category": "String",
    "company": "String | null",
    "country": "String | null",
    "summary": "String | null",
    "image_url": "String | null",
    "content_hash": "String",
    "event_type": "String | null",
    "secondary_tags": "Array of Strings",
    "entities": "Map (Companies: List, Sectors: List, Countries: List)",
    "importance_score": "Integer",
    "postability_score": "Integer",
    "confidence_score": "Integer",
    "final_score": "Integer",
    "scoring_breakdown": "Map",
    "status": "String ('NEW', 'READY_FOR_REVIEW', 'APPROVED', 'REJECTED', 'FILTERED')",
    "created_at": "Timestamp",
    "updated_at": "Timestamp"
  }
  ```

#### Subcollection: Sources
- **Subcollection Path**: `stories/{story_id}/sources`
- **Document Path**: `stories/{story_id}/sources/{source_id}`
- **Document Attributes**:
  ```json
  {
    "source_name": "String",
    "url": "String",
    "published_at": "Timestamp",
    "title": "String"
  }
  ```

---

### B. Research Reports Collection
- **Collection Path**: `research_reports`
- **Document Path**: `research_reports/{report_id}`
- **Document Attributes**:
  ```json
  {
    "story_id": "String (Reference ID pointing to stories collection)",
    "status": "String ('QUEUED', 'RESEARCHING', 'COMPLETED', 'NEEDS_REVIEW', 'FAILED')",
    "what_happened": "String | null",
    "why_it_matters": "String | null",
    "confidence_score": "Integer",
    "created_at": "Timestamp",
    "updated_at": "Timestamp"
  }
  ```

#### Subcollection: Sources
- **Subcollection Path**: `research_reports/{report_id}/sources`
- **Document Path**: `research_reports/{report_id}/sources/{source_id}`
- **Document Attributes**:
  ```json
  {
    "source_name": "String",
    "title": "String",
    "url": "String",
    "canonical_url": "String | null",
    "published_date": "Timestamp | null",
    "discovered_date": "Timestamp",
    "source_type": "String ('rss', 'google_news')",
    "priority": "Integer",
    "extraction_status": "String ('NOT_EXTRACTED', 'COMPLETED', 'FAILED')",
    "content_hash": "String | null",
    "raw_content": "String | null",
    "last_fetched": "Timestamp | null"
  }
  ```

#### Subcollection: Facts
- **Subcollection Path**: `research_reports/{report_id}/facts`
- **Document Path**: `research_reports/{report_id}/facts/{fact_id}`
- **Document Attributes**:
  ```json
  {
    "fact_type": "String",
    "original_value": "String",
    "normalized_value": "Any (Number, Range String, or Object)",
    "currency": "String | null",
    "unit": "String",
    "confidence": "Integer",
    "context": "String | null",
    "source_id": "String (Reference to research source doc ID)"
  }
  ```

#### Subcollection: Conflicts
- **Subcollection Path**: `research_reports/{report_id}/conflicts`
- **Document Path**: `research_reports/{report_id}/conflicts/{conflict_id}`
- **Document Attributes**:
  ```json
  {
    "conflict_type": "String ('VALUE_MISMATCH')",
    "fact_type": "String",
    "source_a": "String",
    "value_a": "String",
    "source_b": "String",
    "value_b": "String",
    "severity": "String ('LOW', 'MEDIUM', 'HIGH')",
    "status": "String ('OPEN', 'RESOLVED')"
  }
  ```

---

## 2. Firestore Composite Index Requirements

Unlike SQLite, which executes ad-hoc database scans, Firestore requires pre-defined indexes for queries that filter on multiple properties or combine filters with sorting.

We will require the following composite indexes:

1. **Index 1**: Querying Story feed filters
   - Collection: `stories`
   - Fields: `status` (Ascending), `final_score` (Descending), `published_at` (Descending)
2. **Index 2**: Querying Story feed category filters
   - Collection: `stories`
   - Fields: `category` (Ascending), `status` (Ascending), `final_score` (Descending), `published_at` (Descending)
3. **Index 3**: Querying Story feed priority category filters
   - Collection: `stories`
   - Fields: `category` (Ascending), `final_score` (Descending), `published_at` (Descending)
4. **Index 4**: Research queue crawler checks
   - Collection: `stories`
   - Fields: `status` (Ascending), `final_score` (Descending)
