import logging
from typing import List, Optional
from app.db.repository import BaseRepository
from app.models.policy import Policy, PolicyRule

logger = logging.getLogger(__name__)

class PolicyService:
    def __init__(self):
        self.policy_repo = BaseRepository("policies", Policy)

    async def ensure_seed_policies(self):
        """Seed initial company policies if empty."""
        count = await self.policy_repo.count()
        if count == 0:
            logger.info("Seeding default company policy rule books...")
            p1 = Policy(
                policy_code="SEC-EMAIL-001",
                title="External Recipient Security Policy",
                department="IT Security",
                unit_ids=["global", "default_unit"],
                version=1,
                effective_from="2026-01-01",
                description="Governs outgoing communications to prevent data exfiltration.",
                rules=[
                    PolicyRule(
                        rule_id="RULE_EMAIL_DOMAIN_RESTRICTION",
                        description="External emails must not be sent to unauthorized domain 'suspicious.com'",
                        condition={
                            "field": "recipient_domain",
                            "operator": "equals",
                            "value": "suspicious.com"
                        },
                        severity="high"
                    )
                ]
            )
            p2 = Policy(
                policy_code="FIN-EXPENSE-002",
                title="Discretionary Expense Limit Policy",
                department="Finance",
                unit_ids=["global", "default_unit"],
                version=2,
                effective_from="2026-01-01",
                description="Flags single transactions exceeding policy thresholds.",
                rules=[
                    PolicyRule(
                        rule_id="RULE_EXPENSE_CAP_EXCEEDED",
                        description="Single transaction expense must not exceed 5000",
                        condition={
                            "field": "amount",
                            "operator": "greater_than",
                            "value": 5000
                        },
                        severity="medium"
                    )
                ]
            )
            await self.policy_repo.create(p1)
            await self.policy_repo.create(p2)

    async def list_policies(self, unit_id: Optional[str] = None) -> List[Policy]:
        return await self.policy_repo.find_many({})

    async def get_by_code(self, code: str) -> Optional[Policy]:
        return await self.policy_repo.find_one({"policy_code": code.upper().strip()})

policy_service = PolicyService()
