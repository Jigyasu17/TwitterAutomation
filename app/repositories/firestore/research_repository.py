import datetime
import logging
from typing import List, Optional, Any
from google.cloud import firestore
from app.domain.models import ResearchReportData, ResearchSourceData, ResearchFactData, ResearchConflictData
from app.repositories.interfaces import ResearchRepository
from app.repositories.firestore.client import get_firestore_client
from app.repositories.firestore.story_repository import normalize_timestamp

logger = logging.getLogger(__name__)

# --- Helper Serialization Functions ---

def map_report_dict_to_domain(doc_id: str, data: dict) -> ResearchReportData:
    return ResearchReportData(
        id=doc_id,
        story_id=data.get("story_id"),
        status=data.get("status", "QUEUED"),
        what_happened=data.get("what_happened"),
        why_it_matters=data.get("why_it_matters"),
        confidence_score=data.get("confidence_score", 0),
        sources=[],
        facts=[],
        conflicts=[],
        created_at=normalize_timestamp(data.get("created_at")),
        updated_at=normalize_timestamp(data.get("updated_at"))
    )

def map_report_domain_to_dict(report: ResearchReportData) -> dict:
    return {
        "story_id": report.story_id,
        "status": report.status,
        "what_happened": report.what_happened,
        "why_it_matters": report.why_it_matters,
        "confidence_score": report.confidence_score,
        "created_at": normalize_timestamp(report.created_at or datetime.datetime.utcnow()),
        "updated_at": normalize_timestamp(report.updated_at or datetime.datetime.utcnow())
    }

def map_res_source_dict_to_domain(doc_id: str, data: dict) -> ResearchSourceData:
    return ResearchSourceData(
        id=doc_id,
        report_id=data.get("report_id"),
        source_name=data.get("source_name", ""),
        title=data.get("title", ""),
        url=data.get("url", ""),
        raw_content=data.get("raw_content"),
        extraction_status=data.get("extraction_status", "PENDING"),
        content_hash=data.get("content_hash"),
        last_fetched=normalize_timestamp(data.get("last_fetched")),
        source_type=data.get("source_type", "RSS"),
        priority=data.get("priority", 3)
    )

def map_res_source_domain_to_dict(src: ResearchSourceData) -> dict:
    return {
        "report_id": src.report_id,
        "source_name": src.source_name,
        "title": src.title,
        "url": src.url,
        "raw_content": src.raw_content,
        "extraction_status": src.extraction_status,
        "content_hash": src.content_hash,
        "last_fetched": normalize_timestamp(src.last_fetched),
        "source_type": src.source_type,
        "priority": src.priority
    }

def map_fact_dict_to_domain(doc_id: str, data: dict) -> ResearchFactData:
    return ResearchFactData(
        id=doc_id,
        report_id=data.get("report_id"),
        fact_type=data.get("fact_type", ""),
        original_value=data.get("original_value", ""),
        normalized_value=data.get("normalized_value", ""),
        currency=data.get("currency"),
        unit=data.get("unit"),
        source_id=data.get("source_id"),
        confidence=data.get("confidence", 0),
        context=data.get("context")
    )

def map_fact_domain_to_dict(fact: ResearchFactData) -> dict:
    return {
        "report_id": fact.report_id,
        "fact_type": fact.fact_type,
        "original_value": fact.original_value,
        "normalized_value": fact.normalized_value,
        "currency": fact.currency,
        "unit": fact.unit,
        "source_id": fact.source_id,
        "confidence": fact.confidence,
        "context": fact.context
    }

def map_conflict_dict_to_domain(doc_id: str, data: dict) -> ResearchConflictData:
    return ResearchConflictData(
        id=doc_id,
        report_id=data.get("report_id"),
        conflict_type=data.get("conflict_type", ""),
        fact_type=data.get("fact_type", ""),
        source_a=data.get("source_a", ""),
        value_a=data.get("value_a", ""),
        source_b=data.get("source_b", ""),
        value_b=data.get("value_b", ""),
        severity=data.get("severity", "MEDIUM"),
        status=data.get("status", "OPEN")
    )

def map_conflict_domain_to_dict(c: ResearchConflictData) -> dict:
    return {
        "report_id": c.report_id,
        "conflict_type": c.conflict_type,
        "fact_type": c.fact_type,
        "source_a": c.source_a,
        "value_a": c.value_a,
        "source_b": c.source_b,
        "value_b": c.value_b,
        "severity": c.severity,
        "status": c.status
    }


# --- ResearchRepository Firestore Implementation ---

class FirestoreResearchRepository(ResearchRepository):
    def __init__(self, client: Optional[firestore.Client] = None):
        self.client = client or get_firestore_client()
        self.collection_name = "research_reports"

    def _populate_subcollections(self, report: ResearchReportData) -> ResearchReportData:
        doc_ref = self.client.collection(self.collection_name).document(report.id)
        
        # 1. Populate sources
        sources_docs = doc_ref.collection("sources").get()
        report.sources = [map_res_source_dict_to_domain(d.id, d.to_dict()) for d in sources_docs]
        
        # 2. Populate facts
        facts_docs = doc_ref.collection("facts").get()
        report.facts = [map_fact_dict_to_domain(d.id, d.to_dict()) for d in facts_docs]
        
        # 3. Populate conflicts
        conflicts_docs = doc_ref.collection("conflicts").get()
        report.conflicts = [map_conflict_dict_to_domain(d.id, d.to_dict()) for d in conflicts_docs]
        
        return report

    def get_report_by_story_id(self, story_id: Any) -> Optional[ResearchReportData]:
        try:
            query = self.client.collection(self.collection_name).where("story_id", "==", str(story_id)).limit(1)
            docs = query.get()
            if docs:
                report = map_report_dict_to_domain(docs[0].id, docs[0].to_dict())
                return self._populate_subcollections(report)
            return None
        except Exception as e:
            logger.error(f"Firestore error in get_report_by_story_id: {e}")
            raise RuntimeError(f"Database error: {e}")

    def get_report_by_id(self, report_id: Any) -> Optional[ResearchReportData]:
        try:
            doc_ref = self.client.collection(self.collection_name).document(str(report_id))
            doc = doc_ref.get()
            if doc.exists:
                report = map_report_dict_to_domain(doc.id, doc.to_dict())
                return self._populate_subcollections(report)
            return None
        except Exception as e:
            logger.error(f"Firestore error in get_report_by_id: {e}")
            raise RuntimeError(f"Database error: {e}")

    def create_report(self, story_id: Any, status: str = "NOT_RESEARCHED") -> ResearchReportData:
        try:
            # Generate a stable report ID matching story_id to enforce uniqueness / prevent duplicates
            report_id = f"report_{story_id}"
            
            doc_ref = self.client.collection(self.collection_name).document(report_id)
            report = ResearchReportData(
                id=report_id,
                story_id=str(story_id),
                status=status,
                sources=[],
                facts=[],
                conflicts=[]
            )
            doc_ref.set(map_report_domain_to_dict(report))
            return report
        except Exception as e:
            logger.error(f"Firestore error in create_report: {e}")
            raise RuntimeError(f"Database error: {e}")

    def save_report(self, report: ResearchReportData) -> ResearchReportData:
        try:
            doc_ref = self.client.collection(self.collection_name).document(str(report.id))
            doc_ref.set(map_report_domain_to_dict(report))
            return report
        except Exception as e:
            logger.error(f"Firestore error in save_report: {e}")
            raise RuntimeError(f"Database error: {e}")

    def save_source(self, source: ResearchSourceData) -> ResearchSourceData:
        try:
            doc_ref = self.client.collection(self.collection_name).document(str(source.report_id))
            if source.id:
                src_ref = doc_ref.collection("sources").document(str(source.id))
            else:
                src_ref = doc_ref.collection("sources").document()
                source.id = src_ref.id

            src_data = map_res_source_domain_to_dict(source)
            src_ref.set(src_data)
            return map_res_source_dict_to_domain(src_ref.id, src_data)
        except Exception as e:
            logger.error(f"Firestore error in save_source: {e}")
            raise RuntimeError(f"Database error: {e}")

    def get_source_by_url(self, report_id: Any, url: str) -> Optional[ResearchSourceData]:
        try:
            query = self.client.collection(self.collection_name).document(str(report_id))\
                .collection("sources").where("url", "==", url).limit(1)
            docs = query.get()
            if docs:
                return map_res_source_dict_to_domain(docs[0].id, docs[0].to_dict())
            return None
        except Exception as e:
            logger.error(f"Firestore error in get_source_by_url: {e}")
            raise RuntimeError(f"Database error: {e}")

    def get_sources_for_report(self, report_id: Any) -> List[ResearchSourceData]:
        try:
            docs = self.client.collection(self.collection_name).document(str(report_id))\
                .collection("sources").get()
            return [map_res_source_dict_to_domain(d.id, d.to_dict()) for d in docs]
        except Exception as e:
            logger.error(f"Firestore error in get_sources_for_report: {e}")
            raise RuntimeError(f"Database error: {e}")

    def save_fact(self, fact: ResearchFactData) -> ResearchFactData:
        try:
            doc_ref = self.client.collection(self.collection_name).document(str(fact.report_id))
            if fact.id:
                fact_ref = doc_ref.collection("facts").document(str(fact.id))
            else:
                fact_ref = doc_ref.collection("facts").document()
                fact.id = fact_ref.id

            fact_data = map_fact_domain_to_dict(fact)
            fact_ref.set(fact_data)
            return map_fact_dict_to_domain(fact_ref.id, fact_data)
        except Exception as e:
            logger.error(f"Firestore error in save_fact: {e}")
            raise RuntimeError(f"Database error: {e}")

    def save_conflict(self, conflict: ResearchConflictData) -> ResearchConflictData:
        try:
            doc_ref = self.client.collection(self.collection_name).document(str(conflict.report_id))
            if conflict.id:
                conf_ref = doc_ref.collection("conflicts").document(str(conflict.id))
            else:
                conf_ref = doc_ref.collection("conflicts").document()
                conflict.id = conf_ref.id

            conf_data = map_conflict_domain_to_dict(conflict)
            conf_ref.set(conf_data)
            return map_conflict_dict_to_domain(conf_ref.id, conf_data)
        except Exception as e:
            logger.error(f"Firestore error in save_conflict: {e}")
            raise RuntimeError(f"Database error: {e}")

    def get_unresolved_conflicts(self, report_id: Any) -> List[ResearchConflictData]:
        try:
            docs = self.client.collection(self.collection_name).document(str(report_id))\
                .collection("conflicts").where("status", "==", "OPEN").get()
            return [map_conflict_dict_to_domain(d.id, d.to_dict()) for d in docs]
        except Exception as e:
            logger.error(f"Firestore error in get_unresolved_conflicts: {e}")
            raise RuntimeError(f"Database error: {e}")

    def clear_report_facts_and_conflicts(self, report_id: Any) -> None:
        try:
            doc_ref = self.client.collection(self.collection_name).document(str(report_id))
            
            # Batch write delete for facts and conflicts to respect Firestore limits and reduce write charges
            batch = self.client.batch()
            
            facts = doc_ref.collection("facts").get()
            for f in facts:
                batch.delete(f.reference)
                
            conflicts = doc_ref.collection("conflicts").get()
            for c in conflicts:
                batch.delete(c.reference)
                
            batch.commit()
        except Exception as e:
            logger.error(f"Firestore error in clear_report_facts_and_conflicts: {e}")
            raise RuntimeError(f"Database error: {e}")
