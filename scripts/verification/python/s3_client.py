"""boto3 client settings required for S3-compatible backends (ADR-012, ADR-013).

Path-style addressing, an explicit endpoint and region, and when-required checksums. botocore 1.36 and
later send flexible checksums by default, which some S3-compatible stores reject (Garage v2.6.0 does).
"""

from __future__ import annotations

import boto3
from botocore.config import Config


def build_config(*, when_required: bool = True) -> Config:
    kwargs: dict = {"s3": {"addressing_style": "path"}}
    if when_required:
        kwargs["request_checksum_calculation"] = "when_required"
        kwargs["response_checksum_validation"] = "when_required"
    return Config(**kwargs)


def build_client(endpoint_url: str, access_key: str, secret_key: str, *, region: str = "garage", when_required: bool = True):
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        region_name=region,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=build_config(when_required=when_required),
    )
