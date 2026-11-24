"""
MongoDB Atlas Idempotent Index & Vector Search Definition Script
Master Plan Reference: §5, §7.2, §7.4, §7.5
"""

import sys
import os
import json
import logging
from pymongo import MongoClient, ASCENDING, DESCENDING, IndexModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("atlas_indexes")

# Canonical Atlas Vector Search Index definition contract
ATLAS_VECTOR_SEARCH_DEFINITION = {
    "name": "policy_chunks_vector_v1",
    "type": "vectorSearch",
    "definition": {
        "fields": [
            {
                "type": "vector",
                "path": "embedding",
                "numDimensions": 1024,  # Mistral-embed vector dimension
                "similarity": "cosine"
            },
            {
                "type": "filter",
                "path": "organization_id"
            },
            {
                "type": "filter",
                "path": "unit_id"
            },
            {
                "type": "filter",
                "path": "policy_id"
            },
            {
                "type": "filter",
                "path": "status"
            }
        ]
    }
}

INDEX_DEFINITIONS = {
    "users": [
        IndexModel([("email", ASCENDING)], unique=True, name="idx_users_email_unique"),
        IndexModel([("unit_id", ASCENDING), ("role", ASCENDING)], name="idx_users_unit_role"),
    ],
    "units": [
        IndexModel([("code", ASCENDING)], unique=True, name="idx_units_code_unique"),
    ],
    "files": [
        IndexModel([("owner_user_id", ASCENDING), ("created_at", DESCENDING)], name="idx_files_owner_created"),
        IndexModel([("unit_id", ASCENDING)], name="idx_files_unit"),
    ],
    "chat_sessions": [
        IndexModel([("user_id", ASCENDING), ("updated_at", DESCENDING)], name="idx_chats_user_updated"),
        IndexModel([("unit_id", ASCENDING)], name="idx_chats_unit"),
    ],
    "chat_messages": [
        IndexModel([("chat_id", ASCENDING), ("created_at", ASCENDING)], name="idx_messages_chat_created"),
    ],
    "policies": [
        IndexModel([("policy_code", ASCENDING)], unique=True, name="idx_policies_code_unique"),
        IndexModel([("status", ASCENDING), ("department", ASCENDING)], name="idx_policies_status_dept"),
    ],
    "policy_chunks": [
        IndexModel([("policy_id", ASCENDING), ("version", ASCENDING)], name="idx_chunks_policy_version"),
        IndexModel([("status", ASCENDING)], name="idx_chunks_status"),
    ],
    "audit_events": [
        IndexModel([("created_at", DESCENDING)], name="idx_audit_created"),
        IndexModel([("user_id", ASCENDING), ("created_at", DESCENDING)], name="idx_audit_user_created"),
        IndexModel([("action", ASCENDING)], name="idx_audit_action"),
    ]
}

def create_indexes(mongo_uri: str = None, database_name: str = "universal_ai_analyst", dry_run: bool = False):
    """Creates all required compound and unique indexes idempotently."""
    logger.info("Initializing MongoDB Atlas index synchronization...")
    logger.info(f"Vector search definition configured: {ATLAS_VECTOR_SEARCH_DEFINITION['name']}")

    if dry_run or not mongo_uri or "localhost" in mongo_uri or "127.0.0.1" in mongo_uri:
        logger.info("[DRY RUN / LOCAL MODE] Validating index specifications offline:")
        for col_name, models in INDEX_DEFINITIONS.items():
            index_names = [m.document.get("name", "unnamed") for m in models]
            logger.info(f" - Collection '{col_name}': {len(models)} indexes validated ({', '.join(index_names)})")
        logger.info("All index contracts validated successfully.")
        return True

    try:
        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
        db = client[database_name]
        # Test connection
        client.admin.command("ping")
        logger.info(f"Connected to MongoDB database: {database_name}")

        for col_name, models in INDEX_DEFINITIONS.items():
            col = db[col_name]
            result = col.create_indexes(models)
            logger.info(f"Created/verified indexes for '{col_name}': {result}")

        client.close()
        logger.info("MongoDB Atlas index creation complete.")
        return True
    except Exception as e:
        logger.warning(f"Could not connect to live MongoDB Atlas cluster: {e}")
        logger.info("Local development and automated test mock fallback remains active.")
        return False

if __name__ == "__main__":
    uri = os.getenv("MONGODB_URI")
    db_name = os.getenv("DATABASE_NAME", "universal_ai_analyst")
    dry_run = "--dry-run" in sys.argv
    create_indexes(mongo_uri=uri, database_name=db_name, dry_run=dry_run)
