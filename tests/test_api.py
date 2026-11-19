import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from api import make_handler
from crm_workflow import connect, initialize

class ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)/'api_test.sqlite3'
        with connect(self.path) as con: initialize(con)
        self.server = ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.path))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.root=f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=2)
        self.tmp.cleanup()

    def test_dashboard_and_metrics(self):
        with urlopen(self.root+'/') as r: self.assertIn(b'CRM Workflow Data Integrity',r.read())
        with urlopen(self.root+'/api/metrics') as r:
            self.assertEqual(json.load(r)['crm_records'],0)

    def test_post_event_via_web_api(self):
        data=dict(source='demo',external_id='e01',record_id='OPP-001',event_time='2026-11-10T10:00:00Z',owner='test@example.test',stage='Discovery',next_step='Review')
        req=Request(self.root+'/api/events',data=json.dumps(data).encode(),headers={'Content-Type':'application/json'},method='POST')
        with urlopen(req) as r: self.assertEqual(r.status,201)
        with urlopen(self.root+'/api/metrics') as r: self.assertEqual(json.load(r)['ingested_events'],1)
        with urlopen(req) as r: self.assertEqual(r.status,200)

if __name__=='__main__':unittest.main()
