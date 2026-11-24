# Universal AI Analyst — Master Product, Architecture & Implementation Plan

**Status:** Build-ready engineering blueprint (not implemented)  
**Edition:** 1.0 — MongoDB Atlas architecture  
**Prepared:** 23 November 2026  
**Audience:** Product owner, engineering team, Codex, Antigravity, AI coding agents, security/QA reviewers  
**Source baseline:** 15-page Universal AI Analyst plan with MongoDB Atlas, DuckDB, FastAPI, and Next.js.

## 0. Executive decisions (read first)

| Decision | Final choice | Why |
|---|---|---|
| Product | Company-internal, policy-aware conversational data analyst | Data questions + policy evaluation + evidence |
| Primary database | **MongoDB Atlas** | Users, units, permissions, sessions, file metadata, policies, versions, logs, jobs, results |
| RAG | **MongoDB Atlas Vector Search + Atlas Search** | Policy embeddings, semantic and keyword retrieval with unit/role/time filters |
| Uploaded binary files | **S3-compatible object storage** (MinIO locally; managed S3-compatible storage in production) | Avoid pushing full Excel/CSV/PDF bytes into MongoDB; use encrypted, private objects |
| Large analytical datasets | Parquet objects + isolated DuckDB/Polars worker | Accurate large-file calculations without turning Atlas into a BI computation engine |
| Frontend | Next.js App Router + TypeScript + Tailwind CSS | Web chat, uploads, policy admin, tables/charts, progress |
| Backend | Python FastAPI + Pydantic v2 + PyMongo Async | One typed Python AI/analytics orchestration service |
| Worker/queue | Redis + Python job queue | Ingestion, embeddings, long-running analyses and retries |
| AI providers | Provider-adapter interface; one configurable primary model, optional vision/advanced models | Do not bake uncertain dated model names into business logic |
| Embeddings | Configurable hosted embedding model; persist model identifier/dimensions | Re-index explicitly when embedding model changes |
| Analytics | DuckDB, Polars, pandas, OpenPyXL | Numeric results are computed, never improvised by the LLM |
| Execution isolation | Independent sandbox runner backed by gVisor or microVM-grade isolation for arbitrary code; strict AST SQL limits for Mode A/B | Never run LLM-generated Python on the API host |
| Auth | Enterprise OIDC/SAML; secure server-side sessions, no vulnerable localStorage long-lived tokens | Deny-by-default, auditable RBAC |
| Privilege hierarchy | **TECH_ADMIN > SUPER_ADMIN > UNIT_ADMIN > EMPLOYEE** | TECH_ADMIN manages all admins; SUPER_ADMIN cannot manage admins |
| Phase 1 scope | Auth, RBAC, upload, single-file analysis, chat, policy RAG, sandbox/approved computations, verification, audit | Deliver a secure working vertical slice first |

## 2. Role model and permission rules

- `TECH_ADMIN`: highest authority, including system and business operations; only role that may create, grant, revoke or manage `UNIT_ADMIN` and `SUPER_ADMIN` accounts.
- `SUPER_ADMIN`: cross-unit analysis, global and unit policies, company-wide employees and business records, reporting and audit; **cannot create, promote or manage UNIT_ADMIN/SUPER_ADMIN/TECH_ADMIN accounts**.
- `UNIT_ADMIN`: assigned unit employee management, unit policies/exceptions, unit datasets and logs; no privilege outside assigned units (`managedUnitIds`).
- `EMPLOYEE`: own files/chats/results, analysis of data explicitly granted to them, and policies visible to their unit. No access to other employees' private files.

## 7. MongoDB Atlas collections & indexes
Collections: `organizations`, `units`, `users`, `role_grants`, `sessions`, `chats`, `messages`, `files`, `datasets`, `analysis_jobs`, `analysis_results`, `policies`, `policy_versions`, `policy_chunks`, `policy_rules`, `policy_exceptions`, `verification_reports`, `audit_events`.
Indexes: unique `(organizationId, email)`, `(policyId, version)`, vector index `policy_chunks_vector_v1`.

## 9. Backend API conventions
- Authentication: Secure cookie / session bearer handling with CSRF protection; no localStorage long-lived tokens.
- Versioned endpoints under `/api/v1`.

## 10. AI Orchestration & Execution Isolation
- Mode A: Typed AST Operations compiled to parameterized DuckDB SQL.
- Mode B: Verified SQL with strict keyword blacklist (`ATTACH`, `COPY`, `INSTALL`, `LOAD`, `PRAGMA`, filesystem access).
- Mode C: Sandboxed code runner.

## 12. Verification Gates
- `V1_EXECUTION`: Clean exit, valid schema.
- `V2_SANITY`: Non-negative/plausible counts.
- `V3_RECOMPUTE`: Independent re-computation check.
- `V4_LINEAGE`: Every finding maps to valid source row index.
- `V5_POLICY`: Applicable published policy & exceptions applied.
- `V6_CITATION`: Every cited clause exists and is published.
- `V7_NARRATIVE`: Assertions match computed JSON numbers.
- `V8_PRIVACY`: No cross-unit leakage.

## 16. Negative test cases
20 critical negative tests ensuring unauthorized access, SQL injections, invalid roles, and boundary leaks are rejected.
