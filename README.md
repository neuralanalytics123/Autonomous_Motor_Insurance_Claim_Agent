Autonomous Motor Insurance Claim Agent

An Autonomous motor insurance claim agent system that processes claims end-to-end with zero paid external LLM API keys—combining automated policy checks, risk scoring, company approval workflows, email alerts, and full audit logs in Python, LangGraph, FastEmbed + Qdrant, SQLAlchemy / SQLite (or PostgreSQL), Streamlit, and Python smtplib.

--->Intake & Proof: The system captures claim details, incident and payout dates, and supporting proof files submitted with the request.
--->Policy & Rules Check: It looks up the relevant policy record, searches policy clauses using FastEmbed and Qdrant, identifies any exclusions, and determines the applicable deductible and coverage cap.
--->Risk Check & Payout Routing: It evaluates risk flags, calculates the proposed payout, and routes claims for company/human approval prior to payout.
--->Notifications & Audit Trail: It sends email notifications, logs updates, saves full claim history, and supports CSV and Excel exports for reporting.

## Table of Contents

1. [What This Project Is & What It Solves](#1-what-this-project-is--what-it-solves)

2. [How It Works (End-to-End Architecture & Workflow)](#2-how-it-works-end-to-end-architecture--workflow)

3. [Technology Stack](#3-technology-stack)

4. [Project Structure](#4-project-structure)

5. [Running Locally From Scratch](#5-running-locally-from-scratch)

6. [Troubleshooting Guide & Fixes Applied](#6-troubleshooting-guide--fixes-applied)

7. [Deploying for Professional Real-World Use](#7-deploying-for-professional-real-world-use)

8. [Extending & Editing in the Future](#8-extending--editing-in-the-future)

## 1. What This Project Is & What It Solves

### What It Is

**Motor Claim Request & Approval** is an interactive claims intake and decision-support application built with Python and Streamlit. Customers or intake officers enter a policy number, contact details, incident details, repair/damage cost (`₹`), current vehicle/material value (`₹`), key dates, and supporting proof files. A multi-step **LangGraph** workflow evaluates coverage rules, deductibles, limits, and risk flags, routes claims requiring sign-off into a **Company Approval** queue, persists records and step-by-step notes, and sends email notifications to the company.

### Real-World Problems It Solves

* **Currency & Regional Alignment:** Converts and formats monetary figures, deductibles, coverage caps, and thresholds in **Indian Rupees (`₹`)** rather than foreign currencies.

* **Opaque Claim Decisions:** Replaces confusing insurance jargon with plain, easy-to-understand explanations of why a claim is approved, waiting for company approval, or rejected.

* **Missing Approval Controls:** Prevents high-value, risky, or sensitive claims from silently auto-settling without company/human review.

* **Disjointed Company Communication:** Automatically notifies the company (`COMPANY_NOTIFY_EMAIL`) when a claim is requested (explicitly requesting company approval when needed) and when a claim is approved or rejected, while maintaining a local JSONL alert log (`company_claim_alerts.jsonl`).

* **Fragmented Records & Evidence:** Saves structured claim decisions in a relational database (`claimflow.db` by default), stores uploaded supporting files under `data/claim_proofs/<claim_id>/`, and allows one-click export to **CSV** and **Excel (`.xlsx`)**.

* **Zero-Cost Local Execution:** Uses local embeddings (`FastEmbed`), local vector storage (`Qdrant`), and local SQLite persistence so you can develop and test without external LLM API keys.

## 2. How It Works (End-to-End Architecture & Workflow)

### High-Level Flow

```
[Customer / Intake Form or CSV Upload]
                │
                ▼
     [Policy Lookup & Proof Storage]
    (portfolio CSV + data/claim_proofs/)
                │
                ▼
      [LangGraph Claim Workflow]
      ├── 1. Claim Received (Intake)
      ├── 2. Policy & Cover Check (Local RAG + Peril & Lapse Rules)
      ├── 3. Extra Verification Check (Risk & Evidence Score)
      └── 4. Final Decision (Approved / Pending Review / Escalated / Rejected)
                │
                ▼
   [Database Persistence (SQLAlchemy)]
   (SQLite claimflow.db or PostgreSQL)
                │
       ┌────────┴────────┐
       ▼                 ▼
[Company Approval]  [Company Notifications]
(Approve / Reject)  (SMTP Email + company_claim_alerts.jsonl)

```

### Step-by-Step Breakdown

1. **Policy Lookup (`data_loader/portfolio.py`):** When a user enters a `Policy Number`, the app searches `data/raw/Motor vehicle insurance data.csv` to pre-fill vehicle risk type, vehicle market value (`₹`), annual premium (`₹`), seniority, active policies in force, and past lapses. If no matching row exists, it falls back to manual/default form inputs.

2. **Evidence & Date Capture (`app.py`, `core/schemas.py`):** Captures customer contact info (`customer_name`, `customer_email`, `customer_phone`), incident date, reported date, payout-needed date, estimated damage cost (`₹`), current vehicle/material value (`₹`), and uploaded proof files saved under `data/claim_proofs/<claim_id>/`.

3. **LangGraph Evaluation (`agents/graph.py`, `agents/policy_rules.py`, `rag/retriever.py`):**

   * **Claim Received:** Records the incoming claim summary and attached proof count.

   * **Policy & Cover Check:** Queries local policy clauses via `FastEmbed` + `Qdrant` (`comprehensive_motor_policy_schedule.md`), checks policy status and lapse rules (such as inactive policies or repeated missed renewals), computes the deductible (with a 25% loyalty discount after 5+ years when applicable), and calculates the maximum payout cap.

   * **Extra Verification Check:** Evaluates risk indicators—such as claim amount relative to annual premium or vehicle value, claim frequency, new-policy high-severity claims, or missing supporting proof above `₹50,000`—producing a `0.00`–`1.00` verification/risk score.

   * **Final Decision:** Determines whether the claim is `REJECTED` (ineligible/excluded), `ESCALATED` or `PENDING_REVIEW` (awaiting company/human approval), or `APPROVED`.

4. **Persistence & Company Notification (`db/session.py`, `notifications/company_notify.py`):** Saves the decision and step-by-step history to the database, appends a JSON record to `company_claim_alerts.jsonl`, and sends an email via `smtplib` to `COMPANY_NOTIFY_EMAIL` (and optionally a copy to the customer if `SEND_CUSTOMER_EMAILS=true`).

5. **Company / Human Approval (`app.py` → `human_decide_claim`):** Claims awaiting approval appear in the **Company Approval** tab. Approving or rejecting updates the database record, appends an approval/rejection entry to the claim history, and triggers a follow-up company email.

## 3. Technology Stack

| Layer | Tool / Library | Purpose in Project | 
| ----- | ----- | ----- | 
| **Runtime & Package Manager** | Python 3.12+, `uv` | Fast dependency resolution, virtual environments, and script execution | 
| **User Interface** | `streamlit`, `pandas`, `openpyxl` | Interactive multi-tab web UI, tables, and CSV/Excel exports | 
| **Workflow Orchestration** | `langgraph` | Stateful multi-step claim intake, policy check, verification, and decision graph | 
| **Local Vector Search / RAG** | `fastembed`, `qdrant-client` | Local text embeddings and vector search over `data/policies/comprehensive_motor_policy_schedule.md` | 
| **Data & Validation** | `pydantic`, `pydantic-settings`, `python-dotenv` | Request/response schemas, environment variable loading, and configuration management | 
| **Persistence** | `sqlalchemy`, `aiosqlite` (or `asyncpg` / `psycopg` for Postgres) | Async relational storage of claims, statuses, and decision payloads | 
| **Notifications** | Python standard library `smtplib`, `email.message`, `urllib.request` | SMTP email delivery, JSONL alert logging (`company_claim_alerts.jsonl`), and optional webhook alerts | 
| **Build Backend** | `hatchling` | Packaging configuration in `pyproject.toml` | 

## 4. Project Structure

```
Autonomous_Insurance_Claim_Agent/
├── .env                                      # Local secrets & runtime settings (do not commit)
├── .env.example                              # Template for environment variables
├── .python-version                           # Target Python version (e.g., 3.12)
├── pyproject.toml                            # Dependencies and hatchling build configuration
├── README.md                                 # Project documentation
├── app.py                                    # Main Streamlit web application
├── claimflow.db                              # SQLite database (created automatically at runtime)
├── company_claim_alerts.jsonl                # Append-only log of company alerts & email status
├── qdrant_storage/                           # Local Qdrant vector index (created automatically)
├── agents/
│   ├── __init__.py
│   ├── graph.py                              # LangGraph workflow nodes and state definition
│   └── policy_rules.py                       # Peril schedules, deductibles, caps, and multipliers
├── core/
│   ├── __init__.py
│   ├── config.py                             # Pydantic settings loaded from .env
│   └── schemas.py                            # Claim intake, status enums, and decision models
├── data/
│   ├── claim_proofs/                         # Uploaded customer proof files grouped by claim ID
│   ├── policies/
│   │   └── comprehensive_motor_policy_schedule.md
│   └── raw/
│       ├── Descriptive of the variables.xlsx
│       ├── Motor vehicle insurance data.csv
│       └── sample type claim.csv
├── data_loader/
│   ├── __init__.py
│   └── portfolio.py                          # Dataset loaders, policy lookup, and CSV parser
├── db/
│   ├── __init__.py
│   ├── models.py                             # SQLAlchemy ORM models (ClaimRecord, Base)
│   └── session.py                            # Async DB engine, claim evaluation, and human approval
├── notifications/
│   ├── __init__.py
│   └── company_notify.py                     # SMTP email sender, alert logger, and webhook support
├── rag/
│   ├── __init__.py
│   ├── ingest.py                             # Policy document chunking and Qdrant ingestion
│   └── retriever.py                          # Semantic search over policy clauses
└── tests/
    └── test_app_flow.py                      # Automated tests for claim and workflow logic

```

## 5. Running Locally From Scratch

### Step 1: Install Prerequisites

* Install **Python 3.12+** and **`uv`** (`https://docs.astral.sh/uv/`).

* Ensure your data files exist under `data/raw/` and `data/policies/comprehensive_motor_policy_schedule.md`.

### Step 2: Clone or Open the Project & Install Dependencies

```
cd /path/to/Autonomous_Insurance_Claim_Agent
uv sync

```

### Step 3: Configure Gmail App Password & `.env`

If sending real emails via Gmail SMTP:

1. Open your Google Account (`myaccount.google.com`) → **Security & sign-in**.

2. Confirm **2-Step Verification** is turned **On**.

3. Open **App passwords** (`https://myaccount.google.com/apppasswords`), create an app password (for example, named `Autonomous Claim Agent`), and copy the 16-character password.

4. Create `.env` in the project root (remove spaces from the 16-character App Password):

```
CURRENCY=INR
CURRENCY_SYMBOL=₹
DATABASE_URL=sqlite+aiosqlite:///./claimflow.db
QDRANT_LOCAL_PATH=./qdrant_storage
QDRANT_COLLECTION=comprehensive_motor_policies
AUTO_APPROVE_THRESHOLD=135000.0
FRAUD_SCORE_THRESHOLD=0.65

COMPANY_NOTIFY_EMAIL=santhoshbharathi82@gmail.com
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-sender-account@gmail.com
SMTP_PASSWORD=your16charapppassword
SMTP_FROM=your-sender-account@gmail.com
COMPANY_WEBHOOK_URL=
SEND_CUSTOMER_EMAILS=false

```

### Step 4: Start the Streamlit Application

```
uv run streamlit run app.py

```

### Step 5: Verify Locally

1. Open the local URL shown in the terminal (typically `http://localhost:8501`).

2. In **Request a Claim**, enter a `Policy Number`, customer info, damage cost (`₹`), current vehicle value (`₹`), dates, and optional proof files, then click **Request Claim & Notify Company**.

3. Check the **Company Approval** tab to approve or reject pending claims, the **Company Emails** tab to confirm email status and preview the message, and the **Claim History** tab to inspect step-by-step notes or export CSV/Excel files.

## 6. Troubleshooting Guide & Fixes Applied

Below are common issues encountered during setup and how they are resolved:

1. **Circular Import Error (`ImportError: cannot import name ... from partially initialized module`)**

   * **Cause:** A module (such as `core/config.py`) importing from `db/session.py` while `db/session.py` imports from `core/config.py`.

   * **Fix:** Keep `core/config.py` self-contained (reading environment variables via `pydantic-settings`) and import `settings` into `db/session.py`, not the other way around.

2. **Missing `notifications` Module (`ModuleNotFoundError` / `ImportError` on `notifications.company_notify`)**

   * **Cause:** The `notifications/` directory or `notifications/__init__.py` / `notifications/company_notify.py` was missing or incomplete at the project root.

   * **Fix:** Create `notifications/` at the root of `Autonomous_Insurance_Claim_Agent/`, add `notifications/__init__.py` exporting `notify_company_of_claim`, `send_claim_email`, and `list_company_alerts`, and implement `notifications/company_notify.py`. Verify with:

```
uv run python -c "from notifications.company_notify import notify_company_of_claim; print('OK')"

```

3. **Monetary Values Appearing in Foreign Currency Instead of Indian Rupees (`₹`)**

   * **Cause:** Default thresholds, sample figures, and UI strings formatted in foreign currency or non-INR scales.

   * **Fix:** Set `CURRENCY=INR` and `CURRENCY_SYMBOL=₹` in `.env` and `core/config.py`, scale dataset figures appropriately in `data_loader/portfolio.py`, and format amounts with `₹` across `agents/graph.py`, `notifications/company_notify.py`, and `app.py`.

4. **Claims Auto-Approving Without Requesting Company/Human Approval**

   * **Cause:** `adjudicate_node` marking low-risk claims under the threshold directly as `APPROVED` with `requires_human_approval=False`.

   * **Fix:** Route eligible claims to `PENDING_REVIEW` (`requires_human_approval=True`) with a clear company approval request so a human reviewer approves or rejects them in the **Company Approval** tab.

5. **SMTP Authentication Failures or Unloaded `.env` Variables**

   * **Cause:** Using a regular account password instead of a 16-character Google App Password, leaving spaces/typos in email addresses, or starting Streamlit without loading `.env`.

   * **Fix:** Call `load_dotenv()` early in `app.py`, verify `SMTP_USER` and `SMTP_FROM` match the sender Gmail account that owns the App Password, remove spaces from `SMTP_PASSWORD`, and restart Streamlit (`Ctrl+C` then `uv run streamlit run app.py`).

6. **Jargon-Heavy Messages in UI, Emails, and Logs**

   * **Cause:** Internal engineering terms appearing in user-facing status text and audit entries.

   * **Fix:** Use clear, plain professional English in decision summaries, email subjects/bodies, tab labels, and step-by-step history notes.

## 7. Deploying for Professional Real-World Use

To deploy **Motor Claim Request & Approval** for real-world use, you need three things in place: **persistent storage** (so claims, uploaded proof files, and alert logs survive restarts/redeploys), **runtime environment variables** (SMTP email credentials, currency/threshold settings, and database URL), and **a reliable host** (such as Docker on a cloud server or Render/VPS with persistent storage).

### 1. Choose the Right Real-World Hosting Setup

* **Cloud Docker / Render Web Service:** Best if you want a public HTTPS URL without managing a Linux server from scratch. On platforms like Render, a paid web service avoids idle spin-down, and attaching a persistent disk or using an external database prevents data loss across restarts.

* **Linux VPS / Internal Company Server with Docker:** Best if you want full control over local storage (`claimflow.db`, `qdrant_storage`, `data/claim_proofs/`, `company_claim_alerts.jsonl`), firewall/VPN restrictions, or local backups on your own machine.

### 2. Step-by-Step Deployment Guide

**1.Add a Production Dockerfile:**Project root.

Create a `Dockerfile` in your project root so the app runs consistently with Python 3.12 and `uv` (or `pip`), binding to `0.0.0.0` and respecting `$PORT`:

Dockerfile

```
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock* ./
RUN pip install --no-cache-dir uv && uv sync --frozen --no-dev || pip install --no-cache-dir -e .

COPY . .

EXPOSE 8501

CMD ["sh", "-c", "uv run streamlit run app.py --server.port=${PORT:-8501} --server.address=0.0.0.0"]

```

*Verification:* Run `docker build -t claimflow-app .` locally and confirm it completes without dependency or build errors.

**2.Push Code Safely Without Secrets:**Git & Hosting Dashboard.

Make sure `.env`, `claimflow.db`, `qdrant_storage/`, `data/claim_proofs/`, and `company_claim_alerts.jsonl` are listed in `.gitignore`, push your repository to GitHub, and add your environment variables in your hosting provider's dashboard (never commit real passwords or App Passwords to Git):

* `CURRENCY=INR`

* `CURRENCY_SYMBOL=₹`

* `AUTO_APPROVE_THRESHOLD=135000.0`

* `FRAUD_SCORE_THRESHOLD=0.65`

* `COMPANY_NOTIFY_EMAIL=santhoshbharathi82@gmail.com`

* `SMTP_HOST=smtp.gmail.com`

* `SMTP_PORT=587`

* `SMTP_USER=<your-sender-gmail>`

* `SMTP_PASSWORD=<your-16-char-app-password>`

* `SMTP_FROM=<your-sender-gmail>`

  *Verification:* Check your Git commit history and repository files to verify no `.env` file or secret password was pushed.

**3.Configure Persistent Data & Backups:**Storage & Database.

In real-world operation, ephemeral container filesystems reset on redeploy. Either mount a persistent volume/disk for `claimflow.db`, `qdrant_storage`, `data/claim_proofs`, and `company_claim_alerts.jsonl` (or point `DATABASE_URL` to a managed PostgreSQL database) and schedule regular backups of your database and proof folders.

*Verification:* Submit a test claim, restart or redeploy the service, and confirm the claim still appears in **Claim History** and **Company Emails**.

**4.Lock Down Access & Test End-to-End:**Access & Operations.

If exposing the app on the public internet rather than an internal company network, put it behind reverse-proxy/SSO or network access controls so unauthorized users cannot access the **Company Approval** queue or customer claim records.

*Verification:* Open the live URL, submit a claim with a sample proof file, confirm the company approval email arrives, approve the claim in **Company Approval**, and confirm the approval email is sent.

### 3. Production Safety & Operational Reminders

Protect Secrets and Internal Approval Access

Never commit your `.env` file or Google App Password to a Git repository, and restrict access to the **Company Approval** tab if the app is reachable outside your local machine or private company network.

## 8. Extending & Editing in the Future

This codebase is modular so you can customize rules and workflows safely as your business evolves:

* **Adjust Peril Deductibles, Caps & Approval Rules:** Edit `PERIL_SCHEDULE` and `VEHICLE_RISK_MULTIPLIER` in `agents/policy_rules.py` or risk checks in `actuarial_fraud_node` (`agents/graph.py`).

* **Update Policy Documents for Local RAG:** Edit `data/policies/comprehensive_motor_policy_schedule.md` and re-run ingestion (`rag/ingest.py`) or clear `qdrant_storage/` so the index rebuilds.

* **Connect an External Policy API or CRM:** Replace or extend `lookup_policy_record()` in `data_loader/portfolio.py` to query your live policy database or internal REST API.

* **Customize Email Templates or Channels:** Update `_build_email_body()` or add Slack/Teams/SMS handlers inside `notifications/company_notify.py`.

* **Add Automated Tests:** Add unit and integration tests under `tests/` and run them with `uv run pytest`.
