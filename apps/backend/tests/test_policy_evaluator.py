import os
import pytest
from app.models.policy import Policy, PolicyRule
from app.policies.evaluator import PolicyEvaluator

def test_policy_evaluator_email_security():
    sample_path = os.path.abspath("data/samples/email_logs.csv")
    policy = Policy(
        policy_code="SEC-EMAIL-001",
        title="External Email Security",
        department="IT",
        version=1,
        rules=[
            PolicyRule(
                rule_id="RULE_SUSPICIOUS_DOMAIN",
                description="Email sent to blacklisted domain suspicious.com",
                condition={
                    "field": "recipient_domain",
                    "operator": "equals",
                    "value": "suspicious.com"
                },
                severity="critical"
            )
        ]
    )

    result = PolicyEvaluator.evaluate_file_against_policy(sample_path, policy)
    assert result["total_violations"] == 3  # rows 2, 4, 7 in email_logs.csv
    assert result["policy_code"] == "SEC-EMAIL-001"
    assert result["evidence_rows"] == [2, 4, 7]
    assert len(result["violations"]) == 3
    assert result["violations"][0]["offending_value"] == "suspicious.com"
