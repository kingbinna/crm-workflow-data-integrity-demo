"""Loopback-only HTTP API and dashboard for CRM Workflow Data Integrity Demo.

Educational local prototype. No authentication: NEVER expose to an external network.
"""
import argparse
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from crm_workflow import connect, initialize, ingest, decide, metrics

BASE = Path(__file__).resolve().parent


def make_handler(db_path):
    class Handler(BaseHTTPRequestHandler):
        server_version = "CRMWorkflowDemo/1.0"

        def respond(self, code, obj):
            data = json.dumps(obj, indent=2).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            route = urlparse(self.path).path
            if route in ("/", "/index.html"):
                data = (BASE / "dashboard.html").read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            con = connect(db_path)
            try:
                if route == "/api/health":
                    self.respond(200, {"status": "ok", "scope": "local demo"})
                elif route == "/api/metrics":
                    self.respond(200, metrics(con))
                elif route == "/api/records":
                    rows = con.execute("SELECT * FROM crm_records ORDER BY record_id").fetchall()
                    self.respond(200, [dict(r) for r in rows])
                elif route == "/api/changes":
                    rows = con.execute("SELECT id,record_id,field_name,old_value,new_value,status,created_at FROM proposed_changes ORDER BY id DESC").fetchall()
                    self.respond(200, [dict(r) for r in rows])
                elif route == "/api/audit":
                    rows = con.execute("SELECT * FROM audit_events ORDER BY id DESC LIMIT 50").fetchall()
                    self.respond(200, [dict(r) for r in rows])
                else:
                    self.respond(404, {"error": "route not found"})
            finally:
                con.close()

        def do_POST(self):
            route = urlparse(self.path).path
            con = connect(db_path)
            try:
                if route == "/api/events":
                    if "application/json" not in self.headers.get("Content-Type", ""):
                        return self.respond(415, {"error": "Content-Type must be application/json"})
                    try:
                        size = int(self.headers.get("Content-Length", "0"))
                    except ValueError:
                        return self.respond(400, {"error": "invalid Content-Length"})
                    if size < 1 or size > 1048576:
                        return self.respond(413, {"error": "request must be 1 to 1048576 bytes"})
                    try:
                        record = json.loads(self.rfile.read(size))
                        if not isinstance(record, dict):
                            raise ValueError("request must be a JSON object")
                        result = ingest(con, record)
                        self.respond(201 if result == "created" else 200, {"status": result})
                    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as e:
                        code = 409 if str(e).startswith("CONFLICT") else 400
                        self.respond(code, {"error": str(e)})
                else:
                    match = re.fullmatch(r"/api/changes/(\d+)/(approve|reject)", route)
                    if match is None:
                        return self.respond(404, {"error": "route not found"})
                    try:
                        self.respond(200, {"status": decide(con, int(match.group(1)), "approved" if match.group(2) == "approve" else "rejected")})
                    except ValueError as e:
                        self.respond(409 if "stale" in str(e) or "already" in str(e) else 400, {"error": str(e)})
            finally:
                con.close()

    return Handler


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", default="crm_demo.sqlite3")
    p.add_argument("--port", type=int, default=8765)
    args = p.parse_args()
    with connect(args.db) as con:
        initialize(con)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(args.db))
    print(f"Demo dashboard: http://127.0.0.1:{server.server_port}")
    print("LOCAL DEMO ONLY. No authentication; do not bind to a public interface.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

if __name__ == "__main__":
    main()
