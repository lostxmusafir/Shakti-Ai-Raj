import logging
from typing import Optional, Dict, Any
from app.db.repository import BaseRepository
from app.models.audit import AuditEvent

logger = logging.getLogger(__name__)

class AuditService:
    def __init__(self):
        self.audit_repo = BaseRepository("audit_events", AuditEvent)

    async def log_event(
        self,
        event_type: str,
        user_id: Optional[str] = None,
        unit_id: Optional[str] = None,
        request_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> AuditEvent:
        event = AuditEvent(
            event_type=event_type,
            user_id=user_id,
            unit_id=unit_id,
            request_id=request_id,
            details=details or {}
        )
        try:
            return await self.audit_repo.create(event)
        except Exception as e:
            logger.error(f"Failed to record audit event '{event_type}': {e}")
            return event

audit_service = AuditService()
