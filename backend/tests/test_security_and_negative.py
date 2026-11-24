import os
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.auth.service import auth_service
from app.policies.service import policy_service
from app.models.policy import Policy, PolicyRule
from app.analysis.execution.sanitizer import SQLSanitizer
from app.core.exceptions import ExecutionError, ForbiddenError, AppException
from app.storage.local import storage_service

@pytest.mark.asyncio
async def test_unauthenticated_role_elevation_rejected():
    """Negative Test: Unauthenticated users attempting to register as super_admin or tech_admin must be 403 Forbidden."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/auth/register", json={
            "email": "malicious_actor@test.internal",
            "password": "Password123!",
            "name": "Malicious Actor",
            "role": "tech_admin"
        })
        assert resp.status_code == 403
        assert "forbidden" in resp.json()["error"]["message"].lower()

@pytest.mark.asyncio
async def test_super_admin_cannot_grant_admin_roles():
    """Negative Test: Master Plan §2.1: SUPER_ADMIN cannot create or grant admin roles. Only TECH_ADMIN can."""
    await auth_service.ensure_seed_admin()
    
    # Create an employee and a super_admin
    emp = await auth_service.register("emp_test@test.internal", "Pass123!", "Employee Test", role="employee")
    s_admin = await auth_service.register("super_test@test.internal", "Pass123!", "Super Test", role="super_admin")
    
    s_token = auth_service.create_token_for_user(s_admin)
    headers = {"Authorization": f"Bearer {s_token}"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/auth/admin/role-grants", json={
            "user_id": emp.id,
            "new_role": "unit_admin",
            "reason": "Unauthorized promotion attempt"
        }, headers=headers)
        assert resp.status_code == 403
        assert "not authorized" in resp.json()["error"]["message"].lower()

@pytest.mark.asyncio
async def test_tech_admin_can_grant_roles():
    """Positive Test: TECH_ADMIN may promote employees to unit_admin."""
    tech_admin = await auth_service.register("tech_master@test.internal", "Pass123!", "Tech Admin Master", role="tech_admin")
    target_emp = await auth_service.register("target_emp@test.internal", "Pass123!", "Target Emp", role="employee")
    
    t_token = auth_service.create_token_for_user(tech_admin)
    headers = {"Authorization": f"Bearer {t_token}"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/auth/admin/role-grants", json={
            "user_id": target_emp.id,
            "new_role": "unit_admin",
            "reason": "Promoted to Unit Admin for Ahmedabad"
        }, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["role"] == "unit_admin"

@pytest.mark.asyncio
async def test_employee_cross_file_access_blocked():
    """Negative Test (IDOR): Employee B must not access private files uploaded by Employee A."""
    emp_a = await auth_service.register("emp_a@test.internal", "Pass123!", "Employee A", role="employee", unit_id="unit_1")
    emp_b = await auth_service.register("emp_b@test.internal", "Pass123!", "Employee B", role="employee", unit_id="unit_1")

    token_a = auth_service.create_token_for_user(emp_a)
    token_b = auth_service.create_token_for_user(emp_b)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Emp A uploads a file
        sample_path = os.path.abspath("data/samples/incidents.csv")
        with open(sample_path, "rb") as f:
            upload_resp = await ac.post("/api/v1/files", files={"file": ("incidents.csv", f, "text/csv")}, headers={"Authorization": f"Bearer {token_a}"})
        file_id_a = upload_resp.json()["id"]

        # Emp B attempts to read Emp A's file
        read_resp = await ac.get(f"/api/v1/files/{file_id_a}", headers={"Authorization": f"Bearer {token_b}"})
        assert read_resp.status_code == 403
        assert "cannot access" in read_resp.json()["error"]["message"].lower()

@pytest.mark.asyncio
async def test_unit_admin_cross_unit_access_blocked():
    """Negative Test (Multi-Tenancy): Unit Admin from unit_alpha cannot access files from unit_beta."""
    u_admin_alpha = await auth_service.register("u_admin_alpha@test.internal", "Pass123!", "Unit Admin Alpha", role="unit_admin", unit_id="unit_alpha")
    emp_beta = await auth_service.register("emp_beta@test.internal", "Pass123!", "Employee Beta", role="employee", unit_id="unit_beta")

    token_alpha = auth_service.create_token_for_user(u_admin_alpha)
    token_beta = auth_service.create_token_for_user(emp_beta)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Emp Beta uploads a file
        sample_path = os.path.abspath("data/samples/incidents.csv")
        with open(sample_path, "rb") as f:
            upload_resp = await ac.post("/api/v1/files", files={"file": ("incidents.csv", f, "text/csv")}, headers={"Authorization": f"Bearer {token_beta}"})
        file_id_beta = upload_resp.json()["id"]

        # Unit Admin Alpha attempts to read Emp Beta's file
        read_resp = await ac.get(f"/api/v1/files/{file_id_beta}", headers={"Authorization": f"Bearer {token_alpha}"})
        assert read_resp.status_code == 403

@pytest.mark.asyncio
async def test_draft_policy_hidden_from_employees():
    """Negative Test: Draft policies must never be retrieved by or exposed to employees."""
    # Seed a draft policy
    draft_policy = Policy(
        policy_code="DRAFT-CONFIDENTIAL-999",
        title="Unapproved Draft Security Policy",
        department="IT",
        unit_ids=["global"],
        version=1,
        status="draft",
        rules=[PolicyRule(rule_id="R_DRAFT", description="Draft rule", condition={"field": "test", "operator": "equals", "value": 1})]
    )
    await policy_service.policy_repo.create(draft_policy)

    emp = await auth_service.register("emp_viewer@test.internal", "Pass123!", "Viewer", role="employee")
    token = auth_service.create_token_for_user(emp)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        list_resp = await ac.get("/api/v1/policies", headers={"Authorization": f"Bearer {token}"})
        policy_codes = [p["policy_code"] for p in list_resp.json()]
        assert "DRAFT-CONFIDENTIAL-999" not in policy_codes

        # Attempt direct lookup
        direct_resp = await ac.get("/api/v1/policies/DRAFT-CONFIDENTIAL-999", headers={"Authorization": f"Bearer {token}"})
        assert direct_resp.status_code == 404

def test_sql_sanitizer_blocks_injections_and_unsafe_statements():
    """Negative Tests: SQLSanitizer must strictly reject DDL/DML, injections, and filesystem operations."""
    allowed = ["incidents", "departments"]

    # 1. Multi-statement injection
    with pytest.raises(ExecutionError) as exc1:
        SQLSanitizer.validate_sql("SELECT * FROM incidents; DROP TABLE incidents", allowed)
    assert "SEMICOLON_NOT_ALLOWED" in str(exc1.value.details)

    # 2. Dangerous keyword: ATTACH
    with pytest.raises(ExecutionError) as exc2:
        SQLSanitizer.validate_sql("ATTACH 'database.db' AS db", allowed)
    assert exc2.value.details.get("violation") in ["FORBIDDEN_KEYWORD", "INVALID_STATEMENT_TYPE"]

    # 2b. Injected forbidden keyword within SELECT query
    with pytest.raises(ExecutionError) as exc2b:
        SQLSanitizer.validate_sql("SELECT * FROM incidents WHERE 1=1 AND (ATTACH 'db.db' IS NULL)", allowed)
    assert "FORBIDDEN_KEYWORD" in str(exc2b.value.details)

    # 3. Dangerous keyword: COPY
    with pytest.raises(ExecutionError) as exc3:
        SQLSanitizer.validate_sql("COPY incidents TO 'out.csv'", allowed)
    assert exc3.value.details.get("violation") in ["FORBIDDEN_KEYWORD", "INVALID_STATEMENT_TYPE"]

    # 4. Dangerous keyword: PRAGMA
    with pytest.raises(ExecutionError) as exc4:
        SQLSanitizer.validate_sql("PRAGMA show_tables", allowed)
    assert exc4.value.details.get("violation") in ["FORBIDDEN_KEYWORD", "INVALID_STATEMENT_TYPE"]

    # 5. Dangerous function: read_csv_auto
    with pytest.raises(ExecutionError) as exc5:
        SQLSanitizer.validate_sql("SELECT * FROM read_csv_auto('/etc/passwd')", allowed)
    assert "FORBIDDEN_FUNCTION" in str(exc5.value.details)

    # 6. Unauthorized table reference
    with pytest.raises(ExecutionError) as exc6:
        SQLSanitizer.validate_sql("SELECT * FROM users", allowed)
    assert "UNAUTHORIZED_TABLE" in str(exc6.value.details)

@pytest.mark.asyncio
async def test_unsupported_file_extension_rejected():
    """Negative Test: Uploading disallowed file extensions (.sh, .exe, .py) must be rejected."""
    emp = await auth_service.register("uploader@test.internal", "Pass123!", "Uploader", role="employee")
    token = auth_service.create_token_for_user(emp)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/files",
            files={"file": ("exploit.sh", b"#!/bin/bash\necho bad", "application/x-sh")},
            headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 400
        assert "UNSUPPORTED_FILE_TYPE" in resp.json()["error"]["code"]
