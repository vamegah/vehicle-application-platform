"""Client-configuration test: the boto3 client is built with the when-required checksum settings.

Verified on the wire against a local HTTP server. Credentials are fake.
"""

from __future__ import annotations

import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from s3_client import build_client

SEEN: list[dict[str, str]] = []


class Handler(BaseHTTPRequestHandler):
    def do_PUT(self):  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        if self.headers.get("Transfer-Encoding", "").lower() == "chunked" or "aws-chunked" in self.headers.get("Content-Encoding", ""):
            self.rfile.read1(65536)
        else:
            self.rfile.read(length)
        SEEN.append({k.lower(): v for k, v in self.headers.items()})
        self.send_response(200)
        self.send_header("ETag", '"d41d8cd98f00b204e9800998ecf8427e"')
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *args):  # silence
        pass


def has_checksum_header(headers: dict[str, str]) -> bool:
    return any(k.startswith("x-amz-checksum-") or k == "x-amz-sdk-checksum-algorithm" or k == "x-amz-trailer" for k in headers)


class S3ClientConfigTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        SEEN.clear()

    def test_when_required_client_sends_no_checksum_headers(self):
        build_client(self.url, "TESTKEYID", "testsecret").put_object(Bucket="b", Key="k", Body=b"hello")
        self.assertEqual(len(SEEN), 1)
        self.assertFalse(has_checksum_header(SEEN[0]), SEEN[0])

    def test_default_client_sends_checksum_headers(self):
        build_client(self.url, "TESTKEYID", "testsecret", when_required=False).put_object(Bucket="b", Key="k", Body=b"hello")
        self.assertEqual(len(SEEN), 1)
        self.assertTrue(has_checksum_header(SEEN[0]), SEEN[0])

    def test_config_object_has_required_settings(self):
        from s3_client import build_config

        cfg = build_config()
        self.assertEqual(cfg.request_checksum_calculation, "when_required")
        self.assertEqual(cfg.response_checksum_validation, "when_required")
        self.assertEqual(cfg.s3, {"addressing_style": "path"})


if __name__ == "__main__":
    unittest.main()
