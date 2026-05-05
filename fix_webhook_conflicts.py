#!/usr/bin/env python3
import requests
import urllib3
import json

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "https://192.168.0.105:5678/api/v1"
API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJkNTQ0NGMyNy04ODc2LTQxZjktYTc5ZC04MzExMDU1NWRjY2UiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiYjg4OWM4ZGUtMWFkNS00YWRlLTk4YzktZTdhYTI5NjdlMGJjIiwiaWF0IjoxNzc3NzA2NzIwfQ.Mnfiite7mOj4uj2HlGLXBJvht8GGKUyeZJABevastIU"
HEADERS = {"X-N8N-API-KEY": API_KEY, "Content-Type": "application/json"}

# Old active workflows with conflicting webhooks
CONFLICTING = [
    "mpzkKZm9iUfjENaE",   # Old Thrift-Cycle Daily Brief
    "4XuduWg1ZeiAkk4O",   # Old Thrift-Cycle STR Alert
]

# New workflows to activate
NEW_WORKFLOWS = {
    "J46DLPbZUgoSTHUq": "Thrift-Cycle Daily Brief",
    "OBlxqlMeyMe313fx": "Thrift-Cycle STR Alert"
}

print("Step 1: Deleting conflicting old workflows...")
for wf_id in CONFLICTING:
    url = f"{BASE_URL}/workflows/{wf_id}"
    try:
        resp = requests.delete(url, headers=HEADERS, verify=False, timeout=30)
        if resp.status_code in (200, 204):
            print(f"  ✓ Deleted old workflow {wf_id}")
        elif resp.status_code == 404:
            print(f"  ⚠ Workflow {wf_id} not found")
        else:
            print(f"  ✗ Failed to delete {wf_id}: {resp.status_code}")
    except Exception as e:
        print(f"  ✗ Error deleting {wf_id}: {e}")

print("\nStep 2: Activating new workflows...")
for wf_id, name in NEW_WORKFLOWS.items():
    url = f"{BASE_URL}/workflows/{wf_id}/activate"
    try:
        resp = requests.post(url, headers=HEADERS, verify=False, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        active = data.get("active", False)
        print(f"  {'✓' if active else '✗'} {name} active={active}")
    except Exception as e:
        print(f"  ✗ Failed to activate {name}: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"    Response: {e.response.status_code} - {e.response.text[:300]}")

print("\nStep 3: Verifying...")
for wf_id, name in NEW_WORKFLOWS.items():
    url = f"{BASE_URL}/workflows/{wf_id}"
    try:
        resp = requests.get(url, headers=HEADERS, verify=False, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        active = data.get("active", False)
        print(f"  {'✓' if active else '✗'} {name} is {'ACTIVE' if active else 'INACTIVE'}")
    except Exception as e:
        print(f"  ✗ Error verifying {name}: {e}")

print("\nStep 4: Re-testing webhook...")
test_url = "https://192.168.0.105:5678/webhook/thrift-cycle-daily-brief"
payload = {
    "date": "2026-05-02",
    "results": [
        {"keyword": "Birkenstock Arizona", "marketplace": "de", "active": 344, "sold": 50, "avg_price": 65.20, "sellability": 0.72, "confidence": "HIGH", "trend": "▲"},
        {"keyword": "Patagonia Nano Puff", "marketplace": "de", "active": 105, "sold": 30, "avg_price": 89.50, "sellability": 0.55, "confidence": "MEDIUM", "trend": "→"},
        {"keyword": "Vintage Levi's 501", "marketplace": "us", "active": 200, "sold": 80, "avg_price": 45.00, "sellability": 0.80, "confidence": "HIGH", "trend": "▲"},
        {"keyword": "Cold Item Example", "marketplace": "de", "active": 500, "sold": 0, "avg_price": 0, "sellability": 0.0, "confidence": "LOW", "trend": "→"}
    ]
}
try:
    resp = requests.post(test_url, json=payload, verify=False, timeout=60)
    print(f"  Webhook response: {resp.status_code}")
    print(f"  Response body: {resp.text[:300]}")
    if resp.status_code in (200, 201):
        print("  ✓ Test webhook sent successfully")
    else:
        print(f"  ⚠ Webhook returned status {resp.status_code}")
except Exception as e:
    print(f"  ✗ Error: {e}")
