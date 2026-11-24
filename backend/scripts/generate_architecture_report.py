"""Build the architecture PDF without reading secrets or private data."""
from pathlib import Path
import os
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, PageBreak,
    Table, TableStyle, KeepTogether, Flowable
)
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
OUT = Path(os.path.expanduser("~")) / "Downloads" / "UNIVERSAL_AI_ANALYST_COMPLETE_SYSTEM_ARCHITECTURE.pdf"

NAVY = colors.HexColor("#101a2c")
INK = colors.HexColor("#172033")
MUTED = colors.HexColor("#5c6b82")
PURPLE = colors.HexColor("#5548e8")
TEAL = colors.HexColor("#0b8f8c")
PALE = colors.HexColor("#eef2f8")
PALE_PURPLE = colors.HexColor("#f0efff")
GREEN = colors.HexColor("#dff5eb")
AMBER = colors.HexColor("#fff2d2")

DIAGRAMS = [
    ("01-system-context.mmd", "System context", ["Analyst", "Next.js web app", "FastAPI API", "Deterministic engine", "AI + policy services"]),
    ("02-runtime-topology.mmd", "Runtime component topology", ["Browser pages", "API client", "FastAPI routes", "Domain services", "DB + compute"]),
    ("03-request-sequence.mmd", "Request sequence", ["User", "Frontend", "API", "Orchestrator", "Engine", "Response"]),
    ("04-auth-policy-boundary.mmd", "Authentication and policy boundary", ["Request", "JWT validation", "Identity", "Policy evaluation", "Allowed tool / denied error"]),
    ("05-ingestion-lifecycle.mmd", "Dataset ingestion lifecycle", ["Upload", "Validate", "Store", "Profile", "Register", "Analyze"]),
    ("06-deterministic-analysis.mmd", "Deterministic analysis path", ["Question", "Mapping", "DuckDB / Polars", "Verification", "Result", "Synthesis"]),
    ("07-ai-intelligence-pipeline.mmd", "AI intelligence pipeline", ["Prompt", "Intent", "Semantic mapping", "Retrieval", "Tool plan", "Execution", "Synthesis"]),
    ("08-skill-registry.mmd", "Skill registry and Excel boundary", ["Registry", "Excel", "EDA", "Quality", "Schema", "Metrics / time-series / insight"]),
    ("09-learning-loop.mmd", "Learning and evaluation loop", ["Approved examples", "Offline split", "Evaluation", "Evidence report", "Human review", "Release gate"]),
    ("10-storage-retention.mmd", "Storage and retention boundary", ["Files", "Production scan", "Storage", "Mongo metadata", "Audit / retention", "Deletion"]),
    ("11-deployment-boundary.mmd", "Deployment and hardware boundary", ["Browser", "Next.js", "FastAPI", "MongoDB", "Mistral", "Disk"]),
    ("12-verification-gate.mmd", "Verification and release gate", ["Source", "Tests", "Security", "Benchmark", "Human review", "Release / hold"]),
]

def styles():
    s = getSampleStyleSheet()
    s.add(ParagraphStyle("CoverTitle", parent=s["Title"], fontName="Helvetica-Bold", fontSize=28, leading=34, textColor=colors.white, alignment=TA_LEFT, spaceAfter=12))
    s.add(ParagraphStyle("CoverSub", parent=s["Normal"], fontSize=12, leading=18, textColor=colors.HexColor("#d9e3f3")))
    s.add(ParagraphStyle("H1x", parent=s["Heading1"], fontName="Helvetica-Bold", fontSize=19, leading=24, textColor=NAVY, spaceBefore=8, spaceAfter=10))
    s.add(ParagraphStyle("H2x", parent=s["Heading2"], fontName="Helvetica-Bold", fontSize=13, leading=17, textColor=PURPLE, spaceBefore=8, spaceAfter=6))
    s.add(ParagraphStyle("Bodyx", parent=s["BodyText"], fontSize=9.4, leading=14, textColor=INK, spaceAfter=7))
    s.add(ParagraphStyle("Smallx", parent=s["BodyText"], fontSize=8, leading=11, textColor=MUTED))
    s.add(ParagraphStyle("CodeX", parent=s["Code"], fontName="Courier", fontSize=7.8, leading=10, textColor=INK, backColor=PALE, borderPadding=7, spaceAfter=8))
    s.add(ParagraphStyle("DiagramTitle", parent=s["Heading1"], fontSize=18, leading=22, alignment=TA_CENTER, textColor=NAVY, spaceAfter=18))
    return s

class Diagram(Flowable):
    def __init__(self, title, labels):
        super().__init__(); self.title = title; self.labels = labels; self.width = 170*mm; self.height = 145*mm
    def draw(self):
        c = self.canv; c.saveState()
        c.setFillColor(PALE_PURPLE); c.roundRect(7*mm, 8*mm, self.width-14*mm, self.height-16*mm, 6*mm, fill=1, stroke=0)
        n = len(self.labels); x0 = 18*mm; x1 = self.width-18*mm; y = self.height-38*mm
        if n <= 6:
            cols = 3; rows = 2
        else:
            cols = 3; rows = (n+2)//3
        boxw = 42*mm; boxh = 17*mm; gapx = 8*mm; gapy = 22*mm
        for i, label in enumerate(self.labels):
            col = i % cols; row = i // cols
            bx = x0 + col*(boxw+gapx); by = y - row*(boxh+gapy)
            if bx + boxw > self.width-8*mm: bx = self.width-8*mm-boxw
            c.setFillColor(colors.white if i % 2 == 0 else colors.HexColor("#e5fbf7"))
            c.setStrokeColor(TEAL if i % 2 else PURPLE); c.setLineWidth(1)
            c.roundRect(bx, by, boxw, boxh, 3*mm, fill=1, stroke=1)
            c.setFillColor(INK); c.setFont("Helvetica-Bold", 7.5)
            words = label.split(); line = ""; lines=[]
            for word in words:
                if c.stringWidth((line+" "+word).strip(), "Helvetica-Bold", 7.5) > boxw-5*mm:
                    lines.append(line); line=word
                else: line=(line+" "+word).strip()
            if line: lines.append(line)
            ty = by + boxh/2 + (len(lines)-1)*3
            for ln in lines[:3]: c.drawCentredString(bx+boxw/2, ty, ln); ty -= 8
            if i < n-1:
                ni=i+1; nc=ni%cols; nr=ni//cols; nx=x0+nc*(boxw+gapx); ny=y-nr*(boxh+gapy)
                if nc == 0:
                    c.setStrokeColor(PURPLE); c.line(bx+boxw/2, by, bx+boxw/2, ny+boxh+2*mm)
                else:
                    c.setStrokeColor(PURPLE); c.line(bx+boxw, by+boxh/2, nx-2*mm, ny+boxh/2)
                    c.line(nx-2*mm, ny+boxh/2, nx-4*mm, ny+boxh/2+1.2*mm)
        c.restoreState()

class Report(BaseDocTemplate):
    def __init__(self, filename, st):
        super().__init__(filename, pagesize=A4, leftMargin=18*mm, rightMargin=18*mm, topMargin=18*mm, bottomMargin=17*mm, title="Universal AI Analyst Complete System Architecture", author="OpenAI Codex")
        frame=Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="normal")
        self.addPageTemplates([PageTemplate(id="main", frames=frame, onPage=self._page)])
    def _page(self, canvas, doc):
        canvas.saveState(); w,h=A4
        canvas.setStrokeColor(colors.HexColor("#d7deea")); canvas.line(18*mm, 12*mm, w-18*mm, 12*mm)
        canvas.setFont("Helvetica", 7.5); canvas.setFillColor(MUTED)
        canvas.drawString(18*mm, 7*mm, "Universal AI Analyst · evidence-backed architecture")
        canvas.drawRightString(w-18*mm, 7*mm, f"Page {doc.page}")
        canvas.restoreState()

def P(text, st): return Paragraph(text, st["Bodyx"])
def bullets(items, st): return [Paragraph("• " + x, st["Bodyx"]) for x in items]
def table(data, st, widths=None):
    converted=[]
    for row in data: converted.append([Paragraph(str(v), st["Smallx"]) for v in row])
    t=Table(converted, colWidths=widths, repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),NAVY),("TEXTCOLOR",(0,0),(-1,0),colors.white),("GRID",(0,0),(-1,-1),0.35,colors.HexColor("#cbd5e1")),("VALIGN",(0,0),(-1,-1),"TOP"),("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,PALE]),("LEFTPADDING",(0,0),(-1,-1),6),("RIGHTPADDING",(0,0),(-1,-1),6),("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5)]))
    return t

def build():
    st=styles(); OUT.parent.mkdir(parents=True, exist_ok=True)
    doc=Report(str(OUT), st); story=[]
    story += [Spacer(1, 30*mm), Paragraph("Universal AI Analyst", st["CoverTitle"]), Paragraph("Complete System Architecture, System Flow & Hardware / Runtime Boundaries", st["CoverSub"]), Spacer(1, 8*mm), Paragraph("Evidence date: 24 November 2026", st["CoverSub"]), Paragraph("Repository: C:\\Users\\DREAM\\Desktop\\AI", st["CoverSub"]), Spacer(1, 70*mm), Paragraph("Prepared as a source-grounded architecture record. Secrets and private records are intentionally omitted.", st["CoverSub"]), PageBreak()]
    story += [Paragraph("Contents and evidence posture", st["H1x"]), P("This report records the current repository architecture and the evidence collected from local tests, manifests, source inspection, and benchmark reports. It does not convert configuration into a claim of production readiness.", st), table([["Section","Coverage"],["1–3","Summary, status legend, repository topology"],["4–5","Request flow and AI intelligence"],["6–8","Datasets, storage, security"],["9–12","Hardware, operations, verification, risks"],["Diagrams","12 component and flow diagrams"],["Glossary","Terms used in the architecture" ]], st, [45*mm, 120*mm]), Spacer(1,8*mm), Paragraph("Evidence labels", st["H2x"]), table([["Label","Interpretation"],["VERIFIED IMPLEMENTATION","Confirmed by source and/or successful local verification."],["CONFIGURED BUT NOT LIVE-VERIFIED","Present in configuration or code; external live dependency not confirmed."],["MOCK / TEST-ONLY","Offline, synthetic, deterministic, or test behavior."],["PLANNED / NOT IMPLEMENTED","Target language without a working implementation found."],["UNKNOWN / NOT CONFIRMED","No reliable evidence available." ]], st, [55*mm,110*mm]), PageBreak()]
    sections=[
        ("1. Executive summary", ["Universal AI Analyst is a Next.js frontend backed by a FastAPI service. The backend exposes health, authentication, chat, file, analysis, and policy routes below /api/v1.", "Data analysis is designed around deterministic execution, while the AI layer provides intent interpretation, semantic mapping, retrieval, insight synthesis, and policy-aware orchestration.", "The verified local path uses the in-memory MongoDB adapter. Live MongoDB Atlas, live Mistral inference, production deployment, and a full vector-search lifecycle were not live-verified in this audit."]),
        ("2. Architecture at a glance", ["Browser (Next.js) → FastAPI /api/v1 → policy checks → AI orchestration → DuckDB/Polars deterministic analysis → verified result and explanation.", "The editable diagram sources are stored in docs/architecture/. The PDF diagrams are rendered as vector-like report pages from the same documented topology."]),
        ("3. Repository and runtime topology", ["Frontend pages cover the landing experience, chat, chat detail, files, login, and policies. Backend routers cover health, auth, chats, files, analysis, and policies.", "The frontend production build and ESLint pass. The backend suite has 60 passing tests. Error responses include a request ID and normalized error fields."]),
        ("4. End-to-end request flow", ["A user authenticates, uploads or selects a file, and sends a chat or analysis request. FastAPI validates it, applies policy context, and selects orchestration.", "The orchestrator maps language to schema and metrics, deterministic code executes the calculation, verification checks the result, and synthesis returns the explanation."]),
        ("5. AI intelligence architecture", ["Semantic mapping, example retrieval, feedback/evaluation services, deterministic analysis, and orchestration evaluation are present. The Mistral provider and external embeddings are configured but not live-verified.", "No verified production loop was found that autonomously trains or deploys model weights. The offline learning window completed checkpoints with weights_updated=false."]),
        ("6. Dataset analysis and evidence", ["The benchmark includes public Microsoft, UCI Online Retail, UCI Bank Marketing, and NYC TLC January 2025 datasets, plus a 5,000-row NexusDynamics fixture.", "There are 310 canonical complete, verified, approved examples split 114/103/93. The held-out deterministic evaluator reports 93/93 for intent, mapping, execution, and numerical checks. Evidence coverage is approximately 2.26%, which remains a known limitation."]),
        ("7. Storage, ingestion, and lifecycle", ["MongoDB is abstracted behind a mock-capable manager. When mock mode is disabled, the app attempts Atlas and falls back to in-memory storage on connection failure.", "Uploads use a configured directory and 50 MB default limit. Production requires malware scanning, content validation, retention, tenant isolation, encryption confirmation, and deletion workflows."]),
        ("8. Security and governance", ["Implemented controls include JWT-style authentication, policy routes, normalized errors, CORS configuration, and DLP/benchmark artifacts. Secret values are excluded.", "Production hardening includes credential rotation, secret management, least-privilege database users, upload scanning, audit logs, tenant authorization, rate limits, and prompt/output privacy controls." ]),
        ("9. Hardware and deployment assumptions", ["Exact workstation CPU, RAM, GPU, and deployment capacity are unknown from source and are not inferred. The deterministic benchmark is CPU-oriented and can run without a GPU.", "Capacity testing must measure large files, concurrent uploads, model-provider quotas, storage IOPS, network egress, and container limits on the actual target." ]),
        ("10. Operations and observability", ["Startup, shutdown, database mode, and unhandled errors are logged; health reports service and database status. Production should add structured metrics, traces, quota alerts, and failed-learning-event handling." ]),
        ("11. Verification matrix", ["Backend tests: 60 passed. Frontend lint/build: passed. Production dependency audit: zero high vulnerabilities reported. Public dataset profiling: four datasets. Held-out evaluator: 93/93, deterministic test-only.", "Live Atlas, live Mistral, GPU sizing, and production deployment remain unverified." ]),
        ("12. Risks and next actions", ["Rotate and remove historical credentials; GitHub currently blocks a normal push because an older commit contains a detected Mistral key. Do not bypass push protection.", "Run controlled staging tests for Atlas and Mistral, improve evidence coverage, add production controls, define learning rollback and human review, and benchmark target capacity." ]),
    ]
    for title, paras in sections:
        story.append(Paragraph(title, st["H1x"])); story.extend([P(x, st) for x in paras]); story.append(Spacer(1,3*mm))
        if title.startswith(("2.","5.","6.","8.","11.")): story.append(PageBreak())
    story += [PageBreak(), Paragraph("Diagram index", st["H1x"]), P("Each diagram below has an editable Mermaid source in docs/architecture/ and a rendered page in this PDF.", st)]
    for i,(fname,title,labels) in enumerate(DIAGRAMS,1):
        story += [PageBreak(), Paragraph(f"Diagram {i:02d} · {title}", st["DiagramTitle"]), Diagram(title,labels), Spacer(1,5*mm), Paragraph(f"Source: docs/architecture/{fname}", st["Smallx"])]
    story += [PageBreak(), Paragraph("Glossary", st["H1x"]), table([["Term","Meaning"],["DuckDB","Embedded analytical SQL engine used for deterministic local queries."],["Polars","Columnar DataFrame engine used in the analysis path."],["Golden example","Approved input/expected-output evaluation record."],["Evidence coverage","Share of benchmark examples with a complete supporting evidence artifact."],["Mock DB","In-memory MongoDB-compatible adapter for tests/offline development."],["Semantic mapping","Mapping user language to fields, dimensions, metrics, and filters."],["DLP","Data-loss-prevention checks that detect or block sensitive content."],["P50/P95","50th/95th percentile latency." ]], st, [45*mm,120*mm]), Spacer(1,10*mm), P("End of report. This document is intentionally conservative where live evidence is unavailable.", st)]
    doc.build(story)
    print(OUT)

if __name__ == "__main__": build()
