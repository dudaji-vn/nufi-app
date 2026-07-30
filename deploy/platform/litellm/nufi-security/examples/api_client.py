"""Simple Python client example for the NuFi HTTP API.

Usage:
    1. Start the server: nufi-egress serve
    2. Run this script: python examples/api_client.py

Requires: httpx (pip install httpx)
"""
from __future__ import annotations

import httpx

BASE_URL = "http://localhost:8000"


def main():
    # Detect PII in Korean text
    resp = httpx.post(f"{BASE_URL}/detect", json={"text": "김민수님 전화번호는 010-1234-5678입니다"})
    resp.raise_for_status()
    print("=== /detect ===")
    print(resp.json())

    # Mask PII
    resp = httpx.post(f"{BASE_URL}/mask", json={"text": "김민수님 전화번호는 010-1234-5678입니다"})
    resp.raise_for_status()
    print("\n=== /mask ===")
    print(resp.json())

    # Route decision
    resp = httpx.post(f"{BASE_URL}/route", json={"text": "김민수님 전화번호는 010-1234-5678입니다"})
    resp.raise_for_status()
    print("\n=== /route ===")
    print(resp.json())

    # Health check
    resp = httpx.get(f"{BASE_URL}/health")
    resp.raise_for_status()
    print("\n=== /health ===")
    print(resp.json())


if __name__ == "__main__":
    main()
