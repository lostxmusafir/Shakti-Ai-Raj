# Universal AI Analyst

An enterprise-grade, policy-aware internal AI Data Analyst with a deterministic calculation engine and MongoDB Atlas tenancy isolation.

---

## 🌟 Key Features

1. **Non-LLM Mental Arithmetic (Deterministic Computation)**:
   - Does **not** trust LLMs to calculate sums, counts, averages, or medians from text.
   - Converts user intent into structured, declarative `AnalysisPlan` ASTs.
   - Compiles AST plans into parameterized SQL queries executed inside isolated **DuckDB** memory sessions.

2. **Server-Side Data Profiling**:
   - Ingests CSV and Excel (`.xlsx`, `.xls`) files.
   - Extracts schema profiles (column types, null counts, unique counts, distributions) without saturating LLM context windows with raw rows.

3. **Multi-File Join & Analysis**:
   - Supports cross-file analysis with automated schema relationship detection and candidate join key matching.

4. **Company Rule Book & Policy Evaluation**:
   - Stores versioned company policies (`policy_code`, `version`, `effective_from`, `rules`).
   - Evaluates datasets deterministically against machine-readable policy rules.
   - Returns row-level evidence with exact source row indices, policy sections, and violation details.

5. **Tenancy & RBAC Isolation**:
   - Role-Based Access Control (`employee`, `unit_admin`, `super_admin`, `tech_admin`).
   - Server-enforced data isolation by `unit_id` and `user_id`.

6. **Auditability & Provenance**:
   - Logs every critical security and analytical event to MongoDB Atlas `audit_events`.
   - Records provenance metadata: source files, sheet names, row indices, execution latency, and SHA-256 query/result hashes.

7. **Real-Time Streaming**:
   - Server-Sent Events (SSE) stream backend status transitions (`Understanding` → `Planning` → `Executing DuckDB` → `Verifying` → `Completed`) directly to the chat interface.

---

## 📁 Repository Structure

```
SHAKTI-AI/
├── backend/             # FastAPI, Python 3.12+, Motor/PyMongo, DuckDB, Polars
│   ├── app/
│   │   ├── api/v1/      # REST API endpoints & SSE streaming
│   │   ├── auth/        # RBAC, JWT, Password hashing
│   │   ├── core/        # Config, logging, exceptions
│   │   ├── db/          # Mongo client & repositories
│   │   ├── models/      # MongoDB document domain models
│   │   ├── schemas/     # Pydantic v2 schemas
│   │   ├── ai/          # Orchestrator, providers, planner, explainer
│   │   ├── analysis/    # Profiler, query compiler, DuckDB engine
│   │   ├── policies/    # Policy ingestion, versioning, evaluation
│   │   ├── storage/     # Storage engine
│   │   └── audit/       # Security & analytical audit logging
│   └── tests/           # Comprehensive Pytest test suite
│
├── frontend/            # Next.js 15, TypeScript, Tailwind CSS
│   ├── src/
│   │   ├── app/         # App router (login, chat, files, policies)
│   │   ├── components/  # Chat, Results, Tables, Status, Sidebar
│   │   └── lib/         # API client & types
│
├── data/
│   ├── samples/             # Sample datasets (incidents.csv, email_logs.csv, departments.csv)
│   └── uploads/             # Storage for uploaded datasets
├── packages/
│   └── contracts/           # Shared API contracts & JSON schemas
├── .env.example
└── README.md
```

---

## 🚀 Quickstart Guide

### 1. Backend Setup
```bash
cd backend

# Create virtualenv and install dependencies
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt

# Start backend server
.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
API Documentation & Interactive Swagger UI: `http://localhost:8000/docs`

### 2. Frontend Setup
```bash
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev
```
Access the application at `http://localhost:3000`

### 3. Default Demo Credentials
- **Email**: `admin@company.internal`
- **Password**: `AdminSecret123!`
- **Role**: `super_admin`

---

## 🧪 Running Tests

### Backend Test Suite
```bash
python -m pytest backend/tests -v
```
All 13 automated unit, integration, and end-to-end tests verify:
- Authentication, JWT, and password hashing
- Storage security and path sanitization
- CSV/Excel schema profiling
- Declarative AST planning and semantic validation
- Query compiler & parameterized DuckDB execution
- Multi-file joins
- Policy evaluation & row violation evidence
- Full end-to-end analyst pipeline
