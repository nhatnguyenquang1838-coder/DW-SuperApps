"""Loopback read-only HTTP adapter tests for qualification state."""
from __future__ import annotations

from http.client import HTTPResponse
from threading import Thread
import json
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from dw_observation.qualification_models import DwoRunId, QualificationSubject, TaskRef
from dw_observation.qualification_store import SQLiteQualificationReceiptStore
from dw_observation.qualification_projection import QualificationProjectionService
from dw_observation.qualification_http import create_read_only_qualification_server


class CurrentSubjectReader:
    def __init__(self, subject):
        self.subject = subject

    def read_current_subject(self, run_id: DwoRunId):
        return self.subject


class QualificationHttpTests(unittest.TestCase):
    def setUp(self):
        self.subject = QualificationSubject(
            dwo_run_id=DwoRunId("DWO-HTTP-1"),
            task_ref=TaskRef("SCRUM-820"),
            source_repository="owner/gwc",
            source_sha="a" * 40,
            lifecycle_profile="gwc.universal-run/1",
            projection_contract_version="dwo.projection-contract/2",
            reducer_version="dwo.reducer/1",
            durable_position="projection_ordinal=1",
        )

    def test_loopback_get_returns_read_projection_and_no_store_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "receipts.sqlite"
            with SQLiteQualificationReceiptStore(path):
                pass
            with SQLiteQualificationReceiptStore(path, read_only=True) as store:
                service = QualificationProjectionService(
                    store,
                    CurrentSubjectReader(self.subject),
                    graph_version="graph/1",
                )
                server = create_read_only_qualification_server(service, host="127.0.0.1", port=0)
                thread = Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    address, port = server.server_address[:2]
                    with urlopen(f"http://{address}:{port}/v1/runs/DWO-HTTP-1/qualification", timeout=3) as response:
                        body = json.loads(response.read().decode("utf-8"))
                        self.assertEqual(response.status, 200)
                        self.assertEqual(response.headers["Cache-Control"], "no-store")
                        self.assertEqual(body["status"], "UNKNOWN")
                        self.assertEqual(body["run_id"], "DWO-HTTP-1")
                    with self.assertRaises(HTTPError) as raised:
                        urlopen(Request(f"http://{address}:{port}/v1/runs/DWO-HTTP-1/qualification", data=b"{}", method="POST"), timeout=3)
                    self.assertEqual(raised.exception.code, 405)
                    self.assertEqual(store.count(), 0)
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=3)

    def test_non_loopback_bind_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "receipts.sqlite"
            with SQLiteQualificationReceiptStore(path):
                pass
            with SQLiteQualificationReceiptStore(path, read_only=True) as store:
                service = QualificationProjectionService(
                    store,
                    CurrentSubjectReader(self.subject),
                    graph_version="graph/1",
                )
                with self.assertRaises(ValueError):
                    create_read_only_qualification_server(service, host="0.0.0.0", port=0)


if __name__ == "__main__":
    unittest.main()
