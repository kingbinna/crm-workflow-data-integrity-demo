# CRM Workflow Data Integrity Demo

A local, runnable **portfolio prototype** showing how an operations team can ingest CRM updates, flag discrepancies, require review before making changes, and measure data quality. Uses **Python 3 and SQLite**, with no third-party packages or external account access.

This is a demonstration using **synthetic records**, not a deployed Salesforce integration, production customer system, or real employer project. Any interview or resume description should preserve that distinction.

## Why it fits digital supply chain / enterprise systems work

- Data import and quality checks: validate timestamp formats, normalize timezones, and reject conflicting duplicate event IDs.
- Workflow and approvals: propose changes without automatically overwriting existing business records.
- Administration and traceability: keep an append-only audit log of ingested events and approval decisions.
- Operational reporting: count CRM records, ingested events, pending/approved changes, missing next steps, and records by stage.
- Relational data: SQLite tables for participants, CRM records, events, proposed changes, and audit events.

## Quick start

From the directory containing `crm_workflow.py`:

```bash
python3 crm_workflow.py --db demo.sqlite3 init
python3 crm_workflow.py --db demo.sqlite3 import-csv sample_events.csv
python3 crm_workflow.py --db demo.sqlite3 report
python3 crm_workflow.py --db demo.sqlite3 changes
python3 crm_workflow.py --db demo.sqlite3 approve 1
python3 crm_workflow.py --db demo.sqlite3 report
python3 crm_workflow.py --db demo.sqlite3 audit
```

Repeat `import-csv` to see idempotency (rows will be `duplicate`). Try changing a row while preserving its `external_id` to see a conflict. Do **not** put real customers' personal information in sample files.

## Run tests

```bash
python3 -m unittest discover -s tests -v
```

## Demo workflow

1. Import four fictional events from `sample_events.csv`. The third event proposes changes to an existing opportunity instead of changing its data immediately.
2. List pending proposals. The first proposal will concern the stage; an additional proposal will concern the next step.
3. Approve or reject an individual proposal. Each decision is recorded in the audit log.
4. Review the metrics before and after to see approved changes and data-quality issues.

## System overview

| Table | Purpose |
|---|---|
| `participants` | Unique fictional record owners |
| `crm_records` | Current status of each opportunity |
| `workflow_events` | Incoming updates, unique source/event ID, UTC timestamp, payload hash |
| `proposed_changes` | Field-level differences requiring manual approval |
| `audit_events` | History of imports and decisions |

## Resume-friendly, accurate description

**CRM Workflow Data Integrity Demo | Python, SQLite, SQL**
- Developed a runnable local prototype that imports synthetic CRM events, checks data consistency and duplicate submissions, and normalizes timestamps to UTC.
- Implemented field-level change proposals, human approval, audit logs, and operational metrics using a relational SQLite database.

## Possible next versions

- Add a web API and real authentication.
- Add CSV report export and configurable validation rules.
- Integrate with a CRM sandbox after verifying permissions and access controls.
- Add a simple web dashboard for approvals and metrics.

## Optional local web dashboard and REST API

After importing the sample CSV, start the web app:

```bash
python3 api.py --db demo.sqlite3 --port 8765
```

Visit **http://127.0.0.1:8765/** on the same computer. This provides a simple dashboard showing operational metrics, sample CRM records, pending change approvals, and audit events. The page lets you approve or reject a proposed change.

API endpoints:

- `GET /api/health`, `GET /api/metrics`, `GET /api/records`
- `GET /api/changes`, `GET /api/audit`
- `POST /api/events` with a JSON event body
- `POST /api/changes/{id}/approve` or `POST /api/changes/{id}/reject`

**Important security limitation:** this demo binds to `127.0.0.1` only and does not include login, authorization, rate-limiting, or HTTPS. It is **not suitable for production deployment**. It intentionally has no Salesforce integration or real customer data.
