"""Open a fresh practice demo with sample records already loaded."""
import csv
import tempfile
import webbrowser
from http.server import ThreadingHTTPServer
from pathlib import Path

from api import make_handler
from crm_workflow import connect, initialize, ingest

BASE = Path(__file__).resolve().parent


def prepare_demo(path):
    with connect(path) as con:
        initialize(con)
        with (BASE / "sample_events.csv").open(newline="", encoding="utf-8") as sample:
            for event in csv.DictReader(sample):
                ingest(con, event)


def main():
    with tempfile.TemporaryDirectory(prefix="crm-practice-") as folder:
        path = Path(folder) / "practice.sqlite3"
        prepare_demo(path)
        with ThreadingHTTPServer(("127.0.0.1", 0), make_handler(path)) as server:
            url = f"http://127.0.0.1:{server.server_port}/"
            print("Your practice demo is ready!", flush=True)
            print(f"If a page does not open, open this link: {url}", flush=True)
            print("Keep this window open while you play.", flush=True)
            print("Press Control+C here to stop. Each start gives you a fresh practice copy.", flush=True)
            webbrowser.open(url)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                print("Practice finished. You can start again any time.")


if __name__ == "__main__":
    main()
