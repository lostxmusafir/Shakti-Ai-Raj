# Universal AI Analyst — Complete System Architecture

**Evidence date:** 24 November 2026  
**Repository:** `C:\Users\DREAM\Desktop\AI`  
**Scope:** architecture, system flow, hardware/runtime assumptions, dataset analysis, AI intelligence, learning, security, testing, and operational status.

> This document is an evidence-backed architecture record. It separates what is implemented from what is configured, mocked, planned, or not confirmed. Secrets, private records, credentials, and raw customer data are intentionally omitted.

## 1. Executive summary

Universal AI Analyst is a Next.js frontend backed by a FastAPI service. The backend exposes health, authentication, chat, file, analysis, and policy routes below `/api/v1`. Data analysis is designed around deterministic execution (DuckDB/Polars in the verified benchmark path), while the AI layer provides intent interpretation, semantic mapping, retrieval, insight synthesis, and policy-aware orchestration.

The repository currently provides a working offline/development path. The health check was verified with the in-memory MongoDB adapter and reports the deterministic analysis engine as `duckdb_polars`. A live MongoDB Atlas connection, live Mistral inference, production deployment, and full vector-search lifecycle were not live-verified in this audit and must not be represented as production-ready.

### Status legend

| Label | Meaning |
|---|---|
| **VERIFIED IMPLEMENTATION** | Confirmed from source and/or a successful local test or command. |
| **CONFIGURED BUT NOT LIVE-VERIFIED** | Code/configuration exists, but a live external dependency or production path was not confirmed. |
| **MOCK / TEST-ONLY** | Deliberately local, deterministic, synthetic, or test behavior. |
| **PLANNED / NOT IMPLEMENTED** | Described as a target but not found as a working implementation. |
| **UNKNOWN / NOT CONFIRMED** | Insufficient evidence; no assumption is made. |

## 2. Architecture at a glance

```text
Browser (Next.js)
        |
        | JSON / multipart HTTP, JWT session
        v
FastAPI /api/v1
  | health/auth/chats/files/analysis/policies
  |
  +--> policy and permission checks
  +--> AI orchestration: intent -> mapping -> retrieval -> synthesis
  +--> deterministic analysis: DuckDB + Polars
  +--> file ingestion and profiling
  +--> MongoDB adapter (mock in verified local path; Atlas configured)
  +--> Mistral provider (configured; live calls not verified here)
  +--> learning/evaluation artifacts and benchmark harness
```

The editable diagram sources for the report are in [`docs/architecture/`](./architecture/).

## 3. Repository and runtime topology

### 3.1 Main components

| Component | Location | Status | Evidence |
|---|---|---|---|
| Web application | `frontend/` | **VERIFIED IMPLEMENTATION** | Next.js build and ESLint pass. |
| API service | `backend/app/` | **VERIFIED IMPLEMENTATION** | FastAPI app and 60 backend tests pass. |
| Deterministic analytics | `backend/app/analysis/`, benchmark scripts | **VERIFIED IMPLEMENTATION** | DuckDB/Polars benchmark and Nexus file tests pass. |
| MongoDB abstraction | `backend/app/db/mongodb.py` | **VERIFIED IMPLEMENTATION** | Mock adapter is exercised by health/tests. |
| Mistral integration | `backend/app/ai/providers/` | **CONFIGURED BUT NOT LIVE-VERIFIED** | Provider and settings exist; live calls were not used as acceptance evidence. |
| AI skills | `backend/app/ai/skills/` | **VERIFIED IMPLEMENTATION** | Microsoft Excel plus seven native skill manifests present. |
| Learning/evaluation | `backend/app/learning/`, `backend/app/ai/learning/` | **VERIFIED IMPLEMENTATION** | 310 canonical approved examples and offline evaluation artifacts. |
| Production deployment | repository/deployment configuration | **UNKNOWN / NOT CONFIRMED** | No production endpoint was used for this audit. |

### 3.2 Frontend routes

The Next.js app contains pages for the landing experience, chat, chat detail, files, login, and policies. The frontend build completed successfully on Next.js 16.4.6 after the lint configuration was migrated to ESLint flat config.

### 3.3 Backend routes

The FastAPI router includes:

- `GET /api/v1/health`
- `/api/v1/auth`
- `/api/v1/chats`
- `/api/v1/files`
- `/api/v1/analysis`
- `/api/v1/policies`

Error responses use a normalized envelope containing an error code, message, request ID, and optional details. CORS defaults are local frontend origins; production origins must be explicitly configured.

## 4. End-to-end request flow

1. A user opens the Next.js client and authenticates through the API.
2. The client uploads or selects a file and sends a chat or analysis request.
3. FastAPI validates the request, applies authentication and policy context, and selects the orchestration path.
4. The orchestrator identifies intent and maps user language to schema fields and metrics.
5. Deterministic code executes the calculation in DuckDB/Polars or the relevant file-analysis path.
6. The result is verified, summarized, and returned with provenance-oriented metadata where available.
7. Feedback and evaluation artifacts can be retained for offline learning; the current continuous runner does not establish automatic production model updates.

## 5. AI intelligence architecture

### 5.1 Intelligence pipeline

The intended separation is: language understanding proposes an operation; deterministic tools perform the operation; verification checks the result; synthesis explains the result. This avoids using free-form model output as the numerical source of truth.

**VERIFIED IMPLEMENTATION:** semantic mapping, example retrieval, feedback/evaluation services, deterministic analysis, and orchestration evaluation are present.  
**CONFIGURED BUT NOT LIVE-VERIFIED:** Mistral provider and external embeddings.  
**PLANNED / NOT IMPLEMENTED:** claims of autonomous continual model training or fully autonomous production skill creation were not found as a verified production loop.

### 5.2 Skills

The checked-in skill registry contains eight visible skill areas: Microsoft Excel and seven native analysis skills covering programmatic EDA, data-quality audit, schema mapping, metric reconciliation, business-metrics calculation, time-series analysis, and insight synthesis.

The Microsoft Excel skill is pinned to a repository commit and uses OpenPyXL for deterministic workbook operations in the local path. Office Scripts, Power Query, VBA, pivot/export operations, and advanced formatting are guidance or capability boundaries unless a separate runtime is provided.

## 6. Dataset analysis and evidence

### 6.1 Verified benchmark assets

| Dataset family | Rows | Columns | Role |
|---|---:|---:|---|
| Microsoft public sample | 700 | 16 | Profiling and analysis benchmark |
| UCI Online Retail | 541,909 | 8 | Public transactional benchmark |
| UCI Bank Marketing | 41,188 | 21 | Public classification/profile benchmark |
| NYC TLC Yellow Taxi, January 2025 | 3,475,226 | 20 | Large public analytical benchmark |
| NexusDynamics incidents | 5,000 | repository fixture | Deterministic file/semantic mapping test |

The public-source manifest records checksums and quality profiles. Raw public and synthetic source files remain local/ignored where appropriate; reports and manifests are the reviewable evidence.

### 6.2 Golden examples and evaluation

- **310** canonical examples are complete, verified, and approved.
- The current split is **114 train / 103 validation / 93 test**.
- The held-out deterministic evaluator reports **93/93** for intent, mapping, execution, and numerical checks in the latest run.
- Latest recorded latency is **P50 0.75 ms / P95 20.84 ms** for the offline evaluator, not end-to-end AI or network latency.
- Evidence coverage is approximately **2.26%**; many examples do not yet carry a complete evidence artifact. This is a known limitation, not a hidden success criterion.
- A two-hour offline learning window completed 24 checkpoints with no recorded failures; weights were not updated.

### 6.3 What the evidence does not prove

The benchmark does not prove model generalization to arbitrary customer data, production throughput, live Mistral reliability, Atlas availability, or business correctness outside the benchmark schema. Those require separate staging/production validation with approved data and operational controls.

## 7. Storage, ingestion, and data lifecycle

The application has a MongoDB abstraction with a thread-safe in-memory implementation for offline development and tests. When mock mode is disabled, the code attempts a MongoDB connection and falls back to the mock adapter if the connection fails. The verified local health path reported the mock engine, so Atlas connectivity is **CONFIGURED BUT NOT LIVE-VERIFIED**.

Uploads are stored below the configured data upload directory with a 50 MB default maximum. A production deployment should add malware scanning, content-type validation, retention rules, tenant isolation, encryption-at-rest confirmation, and deletion/audit workflows before accepting sensitive data.

## 8. Security and governance

Implemented controls include JWT-style authentication, policy routes, normalized errors, CORS configuration, and DLP/benchmark artifacts. Security-sensitive configuration is environment-dependent and values are intentionally excluded from this document.

Required production hardening:

- rotate any credential that has ever appeared in source, examples, logs, or a blocked Git history;
- remove development fallback credentials and require deployment-time secrets;
- use a managed secret store and least-privilege database users;
- add upload scanning, rate limiting, audit logs, and tenant-level authorization tests;
- verify that model prompts and returned previews cannot disclose private rows;
- keep GitHub push protection enabled.

## 9. Hardware and deployment assumptions

The repository is suitable for local Windows development with Python, Node.js, and a browser. Exact workstation CPU/RAM/GPU specifications are **UNKNOWN / NOT CONFIRMED** in this architecture record and should be captured from the deployment target rather than inferred from source.

The deterministic benchmark is CPU-oriented and can run without a GPU. Live model inference, embedding throughput, concurrent uploads, and large-file memory pressure require an environment-specific capacity test. A production sizing exercise should record CPU cores, RAM, disk IOPS, network egress, container limits, MongoDB tier, and model-provider quotas.

## 10. Operations and observability

The backend logs startup, shutdown, database mode, and unhandled exceptions with request IDs. The health route reports service and database status. For production, add structured logs, metrics for request latency and tool execution, traces across upload/orchestration/analysis, dead-letter handling for failed learning events, and alerts for provider quota/rate-limit errors.

## 11. Verification matrix

| Check | Result | Classification |
|---|---|---|
| Backend test suite | 60 passed | **VERIFIED IMPLEMENTATION** |
| Frontend lint | Passed | **VERIFIED IMPLEMENTATION** |
| Frontend production build | Passed | **VERIFIED IMPLEMENTATION** |
| Production dependency audit | 0 high vulnerabilities reported | **VERIFIED IMPLEMENTATION** |
| Public dataset profiling | 4 datasets profiled | **VERIFIED IMPLEMENTATION** |
| Orchestrator held-out evaluator | 93/93, all four checks 100% | **MOCK / TEST-ONLY** |
| Nexus file semantics | 5,000 source rows, blocked-incident checks pass | **MOCK / TEST-ONLY** |
| Health route | Local health passed with mock DB | **VERIFIED IMPLEMENTATION** |
| Live MongoDB Atlas | Not tested as acceptance evidence | **CONFIGURED BUT NOT LIVE-VERIFIED** |
| Live Mistral | Not tested as acceptance evidence | **CONFIGURED BUT NOT LIVE-VERIFIED** |
| GPU/infrastructure sizing | Not captured | **UNKNOWN / NOT CONFIRMED** |

## 12. Risks and next actions

1. **Credential hygiene:** rotate and remove historical credentials; GitHub currently blocks a normal push because an older commit contains a detected Mistral key. Do not bypass push protection.
2. **External dependency validation:** run a controlled staging test for Atlas and Mistral with temporary credentials and approved data.
3. **Evidence completeness:** attach reproducible evidence artifacts to the remaining golden examples.
4. **Production controls:** implement upload scanning, retention, tenant authorization, rate limits, and observability.
5. **Learning governance:** define approval, rollback, drift thresholds, and human review before any automatic model or prompt updates.
6. **Capacity planning:** benchmark large files and concurrent requests on the target deployment hardware.

## 13. Glossary

| Term | Meaning |
|---|---|
| DuckDB | Embedded analytical SQL engine used for deterministic local queries. |
| Polars | Columnar DataFrame engine used in the analysis path. |
| Golden example | Approved input/expected-output evaluation record. |
| Evidence coverage | Share of benchmark examples with a complete supporting evidence artifact. |
| Mock DB | In-memory MongoDB-compatible adapter for tests/offline development. |
| Semantic mapping | Mapping user language to dataset fields, dimensions, metrics, and filters. |
| DLP | Data-loss-prevention checks that detect or block sensitive content. |
| P50/P95 | 50th/95th percentile latency. |

## 14. Diagram index

The PDF includes the following 12 diagrams, with editable Mermaid sources:

1. System context
2. Runtime component topology
3. Request sequence
4. Authentication and policy boundary
5. Dataset ingestion lifecycle
6. Deterministic analysis path
7. AI intelligence pipeline
8. Skill registry and Excel boundary
9. Learning and evaluation loop
10. Storage and retention boundary
11. Deployment and hardware boundary
12. Verification and release gate

