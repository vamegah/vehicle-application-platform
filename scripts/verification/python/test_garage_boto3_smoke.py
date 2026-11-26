"""boto3 put, get, head, delete against the digest-pinned Garage image (ADR-013).

Starts Garage through the Python Testcontainers DockerContainer (no object-store-specific module).
Skipped, and reported as skipped, when no Docker daemon is reachable. The RPC secret and S3 key are
generated at run time for a throwaway container.
"""

from __future__ import annotations

import os
import re
import secrets
import tempfile
import time
import unittest

GARAGE_IMAGE = os.environ.get(
    "GARAGE_IMAGE",
    "dxflrs/garage:v2.6.0@sha256:4b5a318fc9fe2fbec5d3af590eeafe05d83492e6411266fa0b9e215c20264013",
)
BUCKET = "autoreliance-text-dev"
SECRET_RE = re.compile(r"(?i)(secret key:\s*)\S+")

try:
    import docker  # type: ignore

    docker.from_env().ping()
    DOCKER = True
except Exception:  # noqa: BLE001
    DOCKER = False


@unittest.skipUnless(DOCKER, "Docker daemon not reachable")
class GarageBoto3Smoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from testcontainers.core.container import DockerContainer
        from testcontainers.core.waiting_utils import wait_for_logs

        config = (
            'metadata_dir = "/tmp/meta"\n'
            'data_dir = "/tmp/data"\n'
            'db_engine = "sqlite"\n'
            "replication_factor = 1\n"
            'rpc_bind_addr = "[::]:3901"\n'
            'rpc_public_addr = "127.0.0.1:3901"\n'
            f'rpc_secret = "{secrets.token_hex(32)}"\n\n'
            "[s3_api]\n"
            's3_region = "garage"\n'
            'api_bind_addr = "[::]:3900"\n'
            'root_domain = ".s3.garage.localhost"\n'
        )
        cls.tmp = tempfile.TemporaryDirectory()
        path = os.path.join(cls.tmp.name, "garage.toml")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(config)
        cls.container = (
            DockerContainer(GARAGE_IMAGE).with_exposed_ports(3900).with_volume_mapping(path, "/etc/garage.toml", "ro")
        )
        cls.container.start()
        wait_for_logs(cls.container, "S3 API server listening", timeout=60)

        status = cls._exec("/garage", "status")
        node = re.search(r"([0-9a-f]{16})\s", status).group(1)
        cls._exec("/garage", "layout", "assign", "-z", "dc1", "-c", "1G", node)
        cls._exec("/garage", "layout", "apply", "--version", "1")
        cls._exec("/garage", "bucket", "create", BUCKET)
        key = cls._exec("/garage", "key", "create", "smoke")
        cls.access_key = re.search(r"Key ID:\s*(\S+)", key).group(1)
        cls.secret_key = re.search(r"Secret key:\s*(\S+)", key).group(1)
        cls._exec("/garage", "bucket", "allow", "--read", "--write", "--owner", BUCKET, "--key", "smoke")
        time.sleep(2)
        cls.url = f"http://{cls.container.get_container_host_ip()}:{cls.container.get_exposed_port(3900)}"

    @classmethod
    def _exec(cls, *cmd: str) -> str:
        code, out = cls.container.exec(list(cmd))
        text = out.decode() if isinstance(out, bytes) else str(out)
        if code != 0:
            raise AssertionError(" ".join(cmd) + " failed: " + SECRET_RE.sub(r"\1***", text))
        return text

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "container", None):
            cls.container.stop()
        if getattr(cls, "tmp", None):
            cls.tmp.cleanup()

    def test_put_get_head_delete_with_when_required_checksums(self):
        from botocore.exceptions import ClientError
        from s3_client import build_client

        s3 = build_client(self.url, self.access_key, self.secret_key)
        key = "tenant-smoke/text/smoke.txt"
        s3.put_object(Bucket=BUCKET, Key=key, Body=b"hello")
        self.assertEqual(s3.get_object(Bucket=BUCKET, Key=key)["Body"].read(), b"hello")
        self.assertEqual(s3.head_object(Bucket=BUCKET, Key=key)["ContentLength"], 5)
        s3.delete_object(Bucket=BUCKET, Key=key)
        with self.assertRaises(ClientError):
            s3.get_object(Bucket=BUCKET, Key=key)

    def test_record_whether_garage_accepts_default_checksums(self):
        from s3_client import build_client

        s3 = build_client(self.url, self.access_key, self.secret_key, when_required=False)
        try:
            s3.put_object(Bucket=BUCKET, Key="tenant-smoke/text/default.txt", Body=b"hello")
            s3.delete_object(Bucket=BUCKET, Key="tenant-smoke/text/default.txt")
            accepted = True
        except Exception as exc:  # noqa: BLE001
            accepted = False
            print("GARAGE_DEFAULT_CHECKSUM_ERROR=", type(exc).__name__)
        print(f"GARAGE_ACCEPTS_SDK_DEFAULT_CHECKSUMS={accepted} (python)")


if __name__ == "__main__":
    unittest.main()
