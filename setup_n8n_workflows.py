#!/usr/bin/env python3
"""
Setup Thrift-Cycle n8n workflows via REST API.
Deletes old workflows, creates new webhook-triggered ones, activates them,
and tests Workflow 1 with sample data.
"""

import requests
import urllib3
import json
import sys

# Suppress SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "https://192.168.0.105:5678/api/v1"
API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJkNTQ0NGMyNy04ODc2LTQxZjktYTc5ZC04MzExMDU1NWRjY2UiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiYjg4OWM4ZGUtMWFkNS00YWRlLTk4YzktZTdhYTI5NjdlMGJjIiwiaWF0IjoxNzc3NzA2NzIwfQ.Mnfiite7mOj4uj2HlGLXBJvht8GGKUyeZJABevastIU"

HEADERS = {
    "X-N8N-API-KEY": API_KEY,
    "Content-Type": "application/json"
}

OLD_WORKFLOW_IDS = [
    "NtkRFqxidcRvET9P",
    "jADswajVssh30seE"
]

WORKFLOW_1 = {
    "name": "Thrift-Cycle Daily Brief",
    "nodes": [
        {
            "id": "webhook-trigger",
            "name": "Pipeline Results",
            "type": "n8n-nodes-base.webhook",
            "typeVersion": 2,
            "position": [100, 200],
            "parameters": {
                "path": "thrift-cycle-daily-brief",
                "httpMethod": "POST"
            }
        },
        {
            "id": "format-brief",
            "name": "Format Brief",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [400, 200],
            "parameters": {
                "jsCode": "// Process incoming pipeline results and format Telegram message\nconst data = $input.first().json;\nconst results = data.results || [];\nconst date = data.date || 'Unknown';\n\nif (!results || results.length === 0) {\n  return [{ json: { found: false, message: `No pipeline results for ${date}`, chatId: '7463920150' } }];\n}\n\n// Sort by sellability descending\nconst sorted = [...results].sort((a, b) => (b.sellability || 0) - (a.sellability || 0));\n\n// Top 5 buys\nconst topBuys = sorted.slice(0, 5);\nlet topBuysText = topBuys.map((r, i) => {\n  const str = Math.round((r.sellability || 0) * 100);\n  const flag = r.marketplace === 'de' ? '🇩🇪' : '🇺🇸';\n  return `${i + 1}. ${r.keyword} ${flag} — STR ${str}% | Avg €${(r.avg_price || 0).toFixed(0)} | ${r.confidence || 'LOW'}`;\n}).join('\\n');\n\n// Trending items (items with sellability > 0 or sold > 0)\nconst trending = results.filter(r => r.sold > 0 || (r.sellability || 0) > 0.3);\nlet trendingText = trending.slice(0, 5).map(r => {\n  const str = Math.round((r.sellability || 0) * 100);\n  const arrow = r.trend === '▲' ? '📈' : r.trend === '▼' ? '📉' : '➡️';\n  return `• ${r.keyword} (${r.marketplace}) — STR ${str}% ${arrow}`;\n}).join('\\n');\nif (!trendingText) trendingText = '• No trending items today';\n\nconst soldCount = results.filter(r => r.sold > 0).length;\nconst zeroCount = results.filter(r => r.sold === 0).length;\nconst totalActive = results.reduce((sum, r) => sum + (r.active || 0), 0);\n\nconst message = `☕ Thrift-Cycle Daily — ${date}\\n\\n🔥 TOP BUYS:\\n${topBuysText}\\n\\n📈 TRENDING:\\n${trendingText}\\n\\n📊 Scanned: ${results.length} keywords | ${soldCount} with sold data | ${totalActive} total active listings\\n${zeroCount > results.length * 0.5 ? '⚠️ ' + zeroCount + ' keywords returned 0 sold data — possible API quota exhaustion' : ''}\\n\\nDashboard: https://wahajahmed010.github.io/thrift-cycle`;\n\nreturn [{ json: { found: true, message, chatId: '7463920150' } }];"
            }
        },
        {
            "id": "send-brief",
            "name": "Send Morning Brief",
            "type": "n8n-nodes-base.telegram",
            "typeVersion": 1,
            "position": [700, 200],
            "parameters": {
                "resource": "message",
                "operation": "sendMessage",
                "chatId": "7463920150",
                "text": "={{ $json.message }}",
                "additionalFields": {}
            },
            "credentials": {
                "telegramApi": {
                    "id": "r0ksi4cNYBUR6Awr",
                    "name": "Telegram Bot"
                }
            }
        }
    ],
    "connections": {
        "Pipeline Results": {
            "main": [[{"node": "Format Brief", "type": "main", "index": 0}]]
        },
        "Format Brief": {
            "main": [[{"node": "Send Morning Brief", "type": "main", "index": 0}]]
        }
    },
    "settings": {}
}

WORKFLOW_2 = {
    "name": "Thrift-Cycle STR Alert",
    "nodes": [
        {
            "id": "webhook-trigger",
            "name": "STR Data",
            "type": "n8n-nodes-base.webhook",
            "typeVersion": 2,
            "position": [100, 200],
            "parameters": {
                "path": "thrift-cycle-str-alert",
                "httpMethod": "POST"
            }
        },
        {
            "id": "compare-str",
            "name": "Compare STR",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [400, 200],
            "parameters": {
                "jsCode": "// Compare today vs yesterday sellability to find NEW HOT items\nconst payload = $input.first().json;\nconst today = payload.today || {};\nconst yesterday = payload.yesterday || {};\n\nconst todayResults = today.results || [];\nconst yesterdayResults = yesterday.results || [];\n\n// Build yesterday lookup\nconst yesterdayMap = {};\nfor (const r of yesterdayResults) {\n  const key = `${r.keyword}|${r.marketplace}`;\n  yesterdayMap[key] = r.sellability || 0;\n}\n\n// Find items that crossed into HOT (sellability >= 0.60) from below\nconst newHot = todayResults.filter(r => {\n  const key = `${r.keyword}|${r.marketplace}`;\n  const yesterdayStr = yesterdayMap[key] !== undefined ? yesterdayMap[key] : 0;\n  const todayStr = r.sellability || 0;\n  return todayStr >= 0.6 && yesterdayStr < 0.6;\n});\n\nif (newHot.length === 0) {\n  return [{ json: { hasAlert: false, message: '' } }];\n}\n\nconst lines = newHot.map(item => {\n  const key = `${item.keyword}|${item.marketplace}`;\n  const yesterdayStr = yesterdayMap[key] !== undefined ? yesterdayMap[key] : 0;\n  const todayStr = Math.round((item.sellability || 0) * 100);\n  const yesterdayPct = Math.round(yesterdayStr * 100);\n  return `• ${item.keyword} (${item.marketplace}) — STR ${todayStr}% (was ${yesterdayPct}%)`;\n}).join('\\n');\n\nconst message = `🚨 NEW HOT ITEMS DETECTED\\n\\n${lines}\\n\\nCheck Fleek for sourcing!`;\n\nreturn [{ json: { hasAlert: true, message, chatId: '7463920150' } }];"
            }
        },
        {
            "id": "has-new-hot",
            "name": "Has New HOT?",
            "type": "n8n-nodes-base.if",
            "typeVersion": 2,
            "position": [700, 200],
            "parameters": {
                "conditions": {
                    "options": {
                        "caseSensitive": True,
                        "leftExpression": "",
                        "typeValidation": "strict"
                    },
                    "conditions": [
                        {
                            "id": "condition1",
                            "leftValue": "={{ $json.hasAlert }}",
                            "rightValue": True,
                            "operator": {
                                "type": "boolean",
                                "operation": "equals"
                            }
                        }
                    ]
                }
            }
        },
        {
            "id": "telegram-alert",
            "name": "Telegram Alert",
            "type": "n8n-nodes-base.telegram",
            "typeVersion": 1,
            "position": [1000, 200],
            "parameters": {
                "resource": "message",
                "operation": "sendMessage",
                "chatId": "7463920150",
                "text": "={{ $json.message }}",
                "additionalFields": {}
            },
            "credentials": {
                "telegramApi": {
                    "id": "r0ksi4cNYBUR6Awr",
                    "name": "Telegram Bot"
                }
            }
        }
    ],
    "connections": {
        "STR Data": {
            "main": [[{"node": "Compare STR", "type": "main", "index": 0}]]
        },
        "Compare STR": {
            "main": [[{"node": "Has New HOT?", "type": "main", "index": 0}]]
        },
        "Has New HOT?": {
            "main": [
                [{"node": "Telegram Alert", "type": "main", "index": 0}],
                []
            ]
        }
    },
    "settings": {}
}


def delete_old_workflows():
    print("Step 1: Deleting old workflows...")
    for wf_id in OLD_WORKFLOW_IDS:
        url = f"{BASE_URL}/workflows/{wf_id}"
        try:
            resp = requests.delete(url, headers=HEADERS, verify=False, timeout=30)
            if resp.status_code in (200, 204):
                print(f"  ✓ Deleted workflow {wf_id}")
            elif resp.status_code == 404:
                print(f"  ⚠ Workflow {wf_id} not found (already deleted?)")
            else:
                print(f"  ✗ Failed to delete workflow {wf_id}: {resp.status_code} - {resp.text[:200]}")
        except Exception as e:
            print(f"  ✗ Error deleting workflow {wf_id}: {e}")


def create_workflow(workflow_json):
    url = f"{BASE_URL}/workflows"
    try:
        resp = requests.post(url, headers=HEADERS, json=workflow_json, verify=False, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        wf_id = data.get("id")
        print(f"  ✓ Created workflow '{workflow_json['name']}' (ID: {wf_id})")
        return wf_id
    except Exception as e:
        print(f"  ✗ Failed to create workflow '{workflow_json['name']}': {e}")
        if hasattr(e, "response") and e.response is not None:
            print(f"    Response: {e.response.status_code} - {e.response.text[:500]}")
        return None


def activate_workflow(wf_id, name):
    url = f"{BASE_URL}/workflows/{wf_id}/activate"
    try:
        resp = requests.post(url, headers=HEADERS, verify=False, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        active = data.get("active", False)
        print(f"  ✓ Activated workflow '{name}' (active={active})")
        return active
    except Exception as e:
        print(f"  ✗ Failed to activate workflow '{name}': {e}")
        if hasattr(e, "response") and e.response is not None:
            print(f"    Response: {e.response.status_code} - {e.response.text[:500]}")
        return False


def verify_workflow(wf_id, name):
    url = f"{BASE_URL}/workflows/{wf_id}"
    try:
        resp = requests.get(url, headers=HEADERS, verify=False, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        active = data.get("active", False)
        status = "ACTIVE" if active else "INACTIVE"
        print(f"  {'✓' if active else '✗'} Workflow '{name}' is {status}")
        return active
    except Exception as e:
        print(f"  ✗ Failed to verify workflow '{name}': {e}")
        return False


def test_workflow_1():
    print("\nStep 5: Testing Workflow 1 via webhook...")
    url = "https://192.168.0.105:5678/webhook/thrift-cycle-daily-brief"
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
        resp = requests.post(url, json=payload, verify=False, timeout=60)
        print(f"  Webhook response: {resp.status_code}")
        print(f"  Response body: {resp.text[:500]}")
        if resp.status_code in (200, 201):
            print("  ✓ Test webhook sent successfully")
        else:
            print(f"  ⚠ Webhook returned status {resp.status_code}")
    except Exception as e:
        print(f"  ✗ Error sending test webhook: {e}")


def main():
    print("=" * 60)
    print("Thrift-Cycle n8n Workflow Setup")
    print("=" * 60)

    # Step 1: Delete old workflows
    delete_old_workflows()

    # Step 2: Create new workflows
    print("\nStep 2: Creating new workflows...")
    wf1_id = create_workflow(WORKFLOW_1)
    wf2_id = create_workflow(WORKFLOW_2)

    if not wf1_id or not wf2_id:
        print("\n✗ Failed to create one or more workflows. Aborting.")
        sys.exit(1)

    # Step 3: Activate workflows
    print("\nStep 3: Activating workflows...")
    active1 = activate_workflow(wf1_id, WORKFLOW_1["name"])
    active2 = activate_workflow(wf2_id, WORKFLOW_2["name"])

    # Step 4: Verify
    print("\nStep 4: Verifying workflow status...")
    verify_workflow(wf1_id, WORKFLOW_1["name"])
    verify_workflow(wf2_id, WORKFLOW_2["name"])

    # Step 5: Test
    test_workflow_1()

    print("\n" + "=" * 60)
    print("Setup complete!")
    print(f"  Workflow 1 ID: {wf1_id}")
    print(f"  Workflow 2 ID: {wf2_id}")
    print("=" * 60)


if __name__ == "__main__":
    main()
