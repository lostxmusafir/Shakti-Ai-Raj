from __future__ import annotations

import csv
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence

from openpyxl import Workbook


DEPARTMENTS = ["Engineering", "Finance", "Human Resources", "Sales", "Operations", "Legal"]
UNITS = ["North", "South", "East", "West"]
POLICIES = [
    ("EMAIL-001", "Email Security Policy"),
    ("DATA-002", "External Data Sharing Policy"),
    ("INFO-003", "Information Classification Policy"),
]
EVENT_TYPES = ["internal_email", "external_email", "file_upload", "usb_transfer", "cloud_sharing", "security_alert"]
FILE_TYPES = [".csv", ".xlsx", ".pdf", ".docx", ".zip"]


def _employee(index: int) -> Dict[str, str]:
    names = ["Aarav Mehta", "Anika Shah", "Kabir Rao", "Mira Iyer", "Rohan Sen", "Tara Nair"]
    return {
        "employee_id": f"EMP-{index:04d}",
        "employee_name": f"{names[index % len(names)]} {index}",
        "department": DEPARTMENTS[index % len(DEPARTMENTS)],
        "unit": UNITS[index % len(UNITS)],
        "sender_email": f"employee{index:04d}@example.test",
    }


def generate_dlp(rows: int, seed: int = 20261123) -> List[Dict[str, Any]]:
    rng = random.Random(seed + rows)
    employees = [_employee(index) for index in range(1, max(12, min(rows, 120)) + 1)]
    records: List[Dict[str, Any]] = []
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    approved_domains = {"partner.example.test", "vendor.example.test"}
    personal_domains = {"gmail.com", "outlook.com", "yahoo.com"}
    for index in range(rows):
        employee = rng.choice(employees)
        event_type = rng.choice(EVENT_TYPES)
        external = rng.random() < 0.34
        if external:
            domain = rng.choice(sorted(approved_domains | personal_domains | {"unknown.example.test"}))
        else:
            domain = "example.test"
        is_approved = external and domain in approved_domains
        high_risk = external and domain in personal_domains and event_type in {"external_email", "file_upload"}
        blocked = high_risk and rng.random() < 0.65
        action = "BLOCKED" if blocked else ("APPROVED" if is_approved else "ALLOWED")
        status = "blocked" if blocked else "completed"
        size = 0 if blocked else rng.randint(1_000, 5_000_000)
        timestamp = start + timedelta(minutes=rng.randint(0, 365 * 24 * 60))
        policy_id, policy_title = rng.choice(POLICIES)
        records.append({
            "event_id": f"DLP-{index + 1:07d}",
            "timestamp": timestamp.isoformat(),
            **employee,
            "recipient_email": f"contact{index:05d}@{domain}",
            "recipient_domain": domain,
            "source_system": rng.choice(["email_gateway", "endpoint_agent", "cloud_dlp"]),
            "destination_type": "external" if external else "internal",
            "action": action,
            "status": status,
            "incident_category": event_type,
            "severity": "High" if high_risk else rng.choice(["Low", "Medium"]),
            "data_size_bytes": size,
            "file_name": f"document_{index:05d}{rng.choice(FILE_TYPES)}",
            "file_type": rng.choice(FILE_TYPES),
            "policy_id": policy_id,
            "policy_action": "block_external_personal" if high_risk else "monitor",
            "approval_status": "not_required" if not external else ("approved" if is_approved else "pending"),
            "is_external": external,
            "is_approved_destination": is_approved,
            "policy_title": policy_title,
        })
    return records


def generate_hr(seed: int = 20261123, employees: int = 60) -> Dict[str, List[Dict[str, Any]]]:
    rng = random.Random(seed)
    master = [_employee(index) | {"employment_status": "active" if index % 9 else "inactive"} for index in range(1, employees + 1)]
    payroll = [
        {"employee_id": employee["employee_id"], "month": "2026-01", "gross_pay": rng.randint(4_000, 18_000), "currency": "USD"}
        for employee in master if rng.random() > 0.08
    ]
    attendance = [
        {"employee_id": employee["employee_id"], "month": "2026-01", "days_present": rng.randint(15, 23), "days_absent": rng.randint(0, 4)}
        for employee in master
    ]
    return {"employees": master, "payroll_summary": payroll, "attendance": attendance}


def generate_finance(seed: int = 20261123, claims: int = 250) -> Dict[str, List[Dict[str, Any]]]:
    rng = random.Random(seed)
    rows = []
    for index in range(1, claims + 1):
        amount = round(rng.uniform(25, 2_500), 2)
        rows.append({
            "claim_id": f"CLM-{index:06d}",
            "employee_id": f"EMP-{rng.randint(1, 60):04d}",
            "department": rng.choice(DEPARTMENTS),
            "claim_date": f"2026-{rng.randint(1, 3):02d}-{rng.randint(1, 28):02d}",
            "amount": amount,
            "currency": "USD",
            "status": rng.choice(["approved", "rejected", "pending"]),
            "receipt_present": rng.random() > 0.12,
        })
    return {"expense_claims": rows}


def generate_sales(seed: int = 20261123, rows: int = 500) -> Dict[str, List[Dict[str, Any]]]:
    rng = random.Random(seed)
    records = []
    for index in range(1, rows + 1):
        quantity = rng.randint(1, 20)
        unit_price = round(rng.uniform(10, 500), 2)
        records.append({
            "sale_id": f"SALE-{index:07d}",
            "sale_date": f"2026-{rng.randint(1, 6):02d}-{rng.randint(1, 28):02d}",
            "department": rng.choice(DEPARTMENTS),
            "region": rng.choice(UNITS),
            "product": f"Product-{rng.randint(1, 20):02d}",
            "quantity": quantity,
            "unit_price": unit_price,
            "revenue": round(quantity * unit_price, 2),
            "returned": rng.random() < 0.04,
        })
    return {"sales": records}


def write_csv(path: str | Path, rows: Sequence[Mapping[str, Any]]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        target.write_text("\n", encoding="utf-8")
        return
    headers = list(rows[0].keys())
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def write_xlsx(path: str | Path, sheets: Mapping[str, Sequence[Mapping[str, Any]]]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    workbook.remove(workbook.active)
    for sheet_name, rows in sheets.items():
        sheet = workbook.create_sheet(sheet_name[:31])
        if not rows:
            continue
        headers = list(rows[0].keys())
        sheet.append(headers)
        for row in rows:
            sheet.append([row.get(header) for header in headers])
    workbook.save(target)


def write_policy_rules(path: str | Path) -> None:
    policies = [
        {
            "policy_id": "SYNTH-EMAIL-001",
            "title": "Synthetic Email Security Policy",
            "version": "1.0",
            "classification": "SYNTHETIC_TEST_POLICY",
            "effective_from": "2026-01-01",
            "rules": [{"when": {"is_external": True, "recipient_domain_in": ["gmail.com", "outlook.com", "yahoo.com"]}, "action": "block", "severity": "high"}],
            "exceptions": [{"is_approved_destination": True, "action": "allow"}],
        },
        {
            "policy_id": "SYNTH-EXPENSE-001",
            "title": "Synthetic Expense Reimbursement Policy",
            "version": "1.0",
            "classification": "SYNTHETIC_TEST_POLICY",
            "effective_from": "2026-01-01",
            "rules": [{"when": {"amount_greater_than": 1000, "receipt_present": False}, "action": "review", "severity": "medium"}],
            "exceptions": [],
        },
    ]
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(policies, indent=2) + "\n", encoding="utf-8")
