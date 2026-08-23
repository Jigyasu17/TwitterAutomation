import json
import logging
from google.cloud import firestore
from google.oauth2 import service_account
from app.config import settings

logger = logging.getLogger(__name__)

_firestore_client = None

def get_firestore_client() -> firestore.Client:
    """
    Initializes and returns a singleton Firestore client instance.
    Supports local service account injection as well as GCP Application Default Credentials (ADC).
    """
    global _firestore_client
    if _firestore_client is None:
        project_id = settings.GCP_PROJECT_ID or None
        credentials_source = settings.FIRESTORE_CREDENTIALS_JSON
        
        if credentials_source:
            # 1. Attempt to load credentials as inline JSON string content
            try:
                creds_dict = json.loads(credentials_source)
                creds = service_account.Credentials.from_service_account_info(creds_dict)
                _firestore_client = firestore.Client(project=project_id, credentials=creds)
                logger.info(f"Firestore client initialized successfully using inline service account configuration (Project: {project_id})")
                return _firestore_client
            except json.JSONDecodeError:
                # Not inline JSON string; treat as local file path reference
                pass
            except Exception as e:
                logger.error(f"Failed to parse inline credentials JSON: {e}")
            
            # 2. Attempt to load credentials as local filesystem json file path
            try:
                _firestore_client = firestore.Client.from_service_account_json(credentials_source, project=project_id)
                logger.info(f"Firestore client initialized successfully using service account JSON file '{credentials_source}' (Project: {project_id})")
                return _firestore_client
            except Exception as e:
                logger.error(f"Failed to load credentials from file path '{credentials_source}': {e}")
                
        # 3. Fall back to Application Default Credentials (ADC)
        logger.info(f"Initializing Firestore client with default environment configurations (Project: {project_id})")
        _firestore_client = firestore.Client(project=project_id)
        
    return _firestore_client
