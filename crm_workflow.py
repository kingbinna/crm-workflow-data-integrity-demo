"""CRM Workflow Data Integrity Demo (local prototype; synthetic sample data).

Python standard library only. No Salesforce credentials or external services.
"""
import argparse
import csv
import hashlib
import json
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

FIELDS = ("owner", "stage", "next_step")


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_utc(value):
    try:
        d = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError as e:
        raise ValueError("event_time must be an ISO-8601 timestamp with timezone") from e
    if d.tzinfo is None or d.utcoffset() is None:
        raise ValueError("event_time must include a timezone")
    return d.astimezone(timezone.utc).isoformat(timespec="seconds")


def connect(db_path):
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA busy_timeout=5000")
    return con


def initialize(con):
    con.executescript("""
    CREATE TABLE IF NOT EXISTS participants (
        email TEXT PRIMARY KEY,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS crm_records (
        record_id TEXT PRIMARY KEY,
        owner TEXT NOT NULL REFERENCES participants(email),
        stage TEXT NOT NULL,
        next_step TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS workflow_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source TEXT NOT NULL,
        external_id TEXT NOT NULL,
        record_id TEXT NOT NULL,
        event_time TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        payload_hash TEXT NOT NULL,
        received_at TEXT NOT NULL,
        UNIQUE(source, external_id)
    );
    CREATE TABLE IF NOT EXISTS proposed_changes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id INTEGER NOT NULL REFERENCES workflow_events(id),
        record_id TEXT NOT NULL REFERENCES crm_records(record_id),
        field_name TEXT NOT NULL CHECK(field_name IN ('owner','stage','next_step')),
        old_value TEXT NOT NULL,
        new_value TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
        created_at TEXT NOT NULL,
        decided_at TEXT
    );
    CREATE TABLE IF NOT EXISTS audit_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        action TEXT NOT NULL,
        entity TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        details_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """)
    con.commit()


def validated_event(raw):
    required = ("source", "external_id", "record_id", "event_time", *FIELDS)
    missing = [k for k in required if k not in raw or raw[k] is None]
    if missing:
        raise ValueError("missing fields: " + ", ".join(missing))
    obj = {k: str(raw[k]).strip() for k in required}
    for k in ("source", "external_id", "record_id", "owner", "stage"):
        if not obj[k]:
            raise ValueError(f"{k} cannot be empty")
    obj["event_time"] = normalize_utc(obj["event_time"])
    return obj


def ingest(con, raw):
    """Return 'created' or 'duplicate'. Reject conflicting duplicate event IDs.

    Process each event atomically, preserving a complete audit trail.
    """
    evt = validated_event(raw)
    payload = json.dumps(evt, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(payload.encode()).hexdigest()
    with con:
        prior = con.execute("SELECT payload_hash FROM workflow_events WHERE source=? AND external_id=?", (evt["source"], evt["external_id"])).fetchone()
        if prior:
            if prior["payload_hash"] == digest:
                return "duplicate"
            raise ValueError(f"CONFLICT: event {evt['source']}/{evt['external_id']} already exists with different content")
        con.execute("INSERT OR IGNORE INTO participants(email, created_at) VALUES (?, ?)", (evt["owner"], utc_now()))
        cur = con.execute("INSERT INTO workflow_events (source,external_id,record_id,event_time,payload_json,payload_hash,received_at) VALUES (?,?,?,?,?,?,?)",
                          (evt["source"], evt["external_id"], evt["record_id"], evt["event_time"], payload, digest, utc_now()))
        event_id = cur.lastrowid
        record = con.execute("SELECT * FROM crm_records WHERE record_id=?", (evt["record_id"],)).fetchone()
        if record is None:
            con.execute("INSERT INTO crm_records(record_id,owner,stage,next_step,updated_at) VALUES(?,?,?,?,?)",
                        (evt["record_id"], evt["owner"], evt["stage"], evt["next_step"], utc_now()))
        else:
            for field in FIELDS:
                if record[field] != evt[field]:
                    con.execute("INSERT INTO proposed_changes(event_id,record_id,field_name,old_value,new_value,created_at) VALUES(?,?,?,?,?,?)",
                                (event_id, evt["record_id"], field, record[field], evt[field], utc_now()))
        con.execute("INSERT INTO audit_events(action,entity,entity_id,details_json,created_at) VALUES(?,?,?,?,?)",
                    ("ingested", "event", str(event_id), json.dumps({"record_id": evt["record_id"], "source": evt["source"]}), utc_now()))
    return "created"


def decide(con, change_id, decision):
    if decision not in ("approved", "rejected"):
        raise ValueError("decision must be approved or rejected")
    with con:
        change = con.execute("SELECT * FROM proposed_changes WHERE id=?", (change_id,)).fetchone()
        if change is None:
            raise ValueError("change not found")
        if change["status"] != "pending":
            raise ValueError("change already decided")
        record = con.execute("SELECT * FROM crm_records WHERE record_id=?", (change["record_id"],)).fetchone()
        if decision == "approved":
            if record[change["field_name"]] != change["old_value"]:
                raise ValueError("stale proposal: source value changed; review again")
            con.execute(f"UPDATE crm_records SET {change['field_name']}=?, updated_at=? WHERE record_id=?",
                        (change["new_value"], utc_now(), change["record_id"]))
        con.execute("UPDATE proposed_changes SET status=?, decided_at=? WHERE id=?", (decision, utc_now(), change_id))
        con.execute("INSERT INTO audit_events(action,entity,entity_id,details_json,created_at) VALUES(?,?,?,?,?)",
                    (decision, "change", str(change_id), json.dumps({"record_id": change["record_id"], "field": change["field_name"]}), utc_now()))
    return decision


def metrics(con):
    records = con.execute("SELECT * FROM crm_records ORDER BY record_id").fetchall()
    stages = Counter(row["stage"] for row in records)
    return {
        "crm_records": len(records),
        "ingested_events": con.execute("SELECT count(*) FROM workflow_events").fetchone()[0],
        "pending_changes": con.execute("SELECT count(*) FROM proposed_changes WHERE status='pending'").fetchone()[0],
        "approved_changes": con.execute("SELECT count(*) FROM proposed_changes WHERE status='approved'").fetchone()[0],
        "missing_next_steps": sum(not row["next_step"] for row in records),
        "by_stage": dict(sorted(stages.items()))
    }


def run_cli():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", default="crm_demo.sqlite3", help="SQLite database path")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="Initialize schema")
    i = sub.add_parser("import-csv", help="Ingest synthetic CSV events")
    i.add_argument("csv_path")
    sub.add_parser("report", help="Print data quality / workflow metrics")
    sub.add_parser("changes", help="List pending change proposals")
    sub.add_parser("audit", help="Show recent audit log")
    ap = sub.add_parser("approve", help="Approve a proposed change")
    ap.add_argument("change_id", type=int)
    rj = sub.add_parser("reject", help="Reject a proposed change")
    rj.add_argument("change_id", type=int)
    args = p.parse_args()
    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    con = connect(args.db)
    initialize(con)
    try:
        if args.command == "init":
            print("Database initialized:", args.db)
        elif args.command == "import-csv":
            counts = Counter()
            with open(args.csv_path, newline="", encoding="utf-8") as f:
                for line_num, event in enumerate(csv.DictReader(f), start=2):
                    try:
                        counts[ingest(con, event)] += 1
                    except ValueError as e:
                        counts["rejected"] += 1
                        print(f"row {line_num}: {e}")
            print(json.dumps(dict(counts), indent=2))
        elif args.command == "report":
            print(json.dumps(metrics(con), indent=2))
        elif args.command == "changes":
            for row in con.execute("SELECT id,record_id,field_name,old_value,new_value,status FROM proposed_changes WHERE status='pending' ORDER BY id"):
                print(dict(row))
        elif args.command == "audit":
            for row in con.execute("SELECT * FROM audit_events ORDER BY id DESC LIMIT 30"):
                print(dict(row))
        elif args.command in ("approve", "reject"):
            print(decide(con, args.change_id, "approved" if args.command == "approve" else "rejected"))
    except ValueError as e:
        p.exit(1, f"Error: {e}\n")
    finally:
        con.close()

if __name__ == "__main__":
    run_cli()
