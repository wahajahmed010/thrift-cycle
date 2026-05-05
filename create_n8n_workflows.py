#!/usr/bin/env python3
"""
Create Thrift-Cycle n8n workflows via REST API.
Workflows are created INACTIVE — Wahaj must activate them after adding Telegram credentials.
"""

import json
import sys
import uuid
import urllib3
import requests

# ── config ──────────────────────────────────────────────────────────
N8N_BASE_URL = "https://192.168.0.105:5678"
API_KEY      = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJkNTQ0NGMyNy04ODc2LTQxZjktYTc5ZC04MzExMDU1NWRjY2UiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiYjg4OWM4ZGUtMWFkNS00YWRlLTk4YzktZTdhYTI5NjdlMGJjIiwiaWF0IjoxNzc3NzA2NzIwfQ.Mnfiite7mOj4uj2HlGLXBJvht8GGKUyeZJABevastIU"
DATA_DIR     = "/home/wahaj/.openclaw/workspace/thrift-cycle/data"
PIPELINE_DIR = "/home/wahaj/.openclaw/workspace/thrift-cycle"

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

HEADERS = {
    "X-N8N-API-KEY": API_KEY,
    "Content-Type": "application/json",
}

# ── helper ──────────────────────────────────────────────────────────
def api(method, path, **kwargs):
    url = f"{N8N_BASE_URL}/api/v1{path}"
    r = requests.request(method, url, headers=HEADERS, verify=False, **kwargs)
    return r


def new_id():
    return str(uuid.uuid4())


# ═════════════════════════════════════════════════════════════════════
#  Workflow 1 — Thrift-Cycle Daily Pipeline
# ═════════════════════════════════════════════════════════════════════
def build_workflow_1():
    n = {
        "schedule":      {"id": new_id(), "name": "Schedule Trigger",      "pos": [100,  200]},
        "exec":          {"id": new_id(), "name": "Execute Command",       "pos": [400,  200]},
        "format":        {"id": new_id(), "name": "Format Brief",          "pos": [700,  200]},
        "telegram_ok":   {"id": new_id(), "name": "Telegram Success",      "pos": [1000, 200]},
        "telegram_err":  {"id": new_id(), "name": "Telegram Failure",      "pos": [400,  500]},
        "trigger_wf2":   {"id": new_id(), "name": "Trigger STR Alert",     "pos": [1300, 200]},
    }

    # JavaScript for the Format Brief Code node
    format_js = f"""
const fs = require('fs');
const path = '{DATA_DIR}/';

const files = fs.readdirSync(path)
  .filter(f => f.match(/^\\d{{4}}-\\d{{2}}-\\d{{2}}\\.json$/))
  .sort();

if (files.length === 0) {{
  return [{{ json: {{ message: 'No data files found.', chatId: 'PLACEHOLDER_CHAT_ID' }} }}];
}}

const latest = files[files.length - 1];
const data = JSON.parse(fs.readFileSync(path + latest, 'utf8'));
const date = data.date;
const results = data.results || [];

const sorted = [...results].sort((a, b) => b.sellability - a.sellability);
const topBuys = sorted.slice(0, 5);

let topBuysText = topBuys.map((r, i) => {{
  const str = Math.round(r.sellability * 100);
  return `${{i + 1}}. ${{r.keyword}} (${{r.marketplace}}) — STR ${{str}}% | Avg €${{r.avg_price.toFixed(2)}} | ${{r.confidence}}`;
}}).join('\\n');
if (!topBuysText) topBuysText = '• No items today';

const trending = results.filter(r => r.trend === '▲');
let trendingText = trending.map(r => {{
  const str = Math.round(r.sellability * 100);
  return `• ${{r.keyword}} (${{r.marketplace}}) — STR ${{str}}% ▲`;
}}).join('\\n');
if (!trendingText) trendingText = '• No trending items today';

const soldCount = results.filter(r => r.sold > 0).length;
const zeroCount = results.filter(r => r.sold === 0).length;

const message = `☕ Thrift-Cycle Daily — ${{date}}

🔥 TOP BUYS:
${{topBuysText}}

📈 TRENDING UP:
${{trendingText}}

⚠️ QUOTA: ${{soldCount}} keywords got sold data, ${{zeroCount}} returned 0

Full dashboard: https://wahajahmed010.github.io/thrift-cycle`;

return [{{ json: {{ message, chatId: 'PLACEHOLDER_CHAT_ID', date }} }}];
""".strip()

    nodes = [
        {
            "id": n["schedule"]["id"],
            "name": n["schedule"]["name"],
            "type": "n8n-nodes-base.scheduleTrigger",
            "typeVersion": 1,
            "position": n["schedule"]["pos"],
            "parameters": {
                "rule": {"interval": []},
                "mode": "cronExpression",
                "cronExpression": "0 8 * * *",
            },
        },
        {
            "id": n["exec"]["id"],
            "name": n["exec"]["name"],
            "type": "n8n-nodes-base.executeCommand",
            "typeVersion": 1,
            "position": n["exec"]["pos"],
            "parameters": {
                "command": f"cd {PIPELINE_DIR} && python3 pipeline.py --full 2>&1",
            },
        },
        {
            "id": n["format"]["id"],
            "name": n["format"]["name"],
            "type": "n8n-nodes-base.code",
            "typeVersion": 1,
            "position": n["format"]["pos"],
            "parameters": {
                "jsCode": format_js,
            },
        },
        {
            "id": n["telegram_ok"]["id"],
            "name": n["telegram_ok"]["name"],
            "type": "n8n-nodes-base.telegram",
            "typeVersion": 1,
            "position": n["telegram_ok"]["pos"],
            "parameters": {
                "resource": "message",
                "operation": "sendMessage",
                "chatId": "PLACEHOLDER_CHAT_ID",
                "text": "={{ $json.message }}",
                "additionalFields": {},
            },
            "credentials": {
                "telegramBotApi": {
                    "id": "PLACEHOLDER",
                    "name": "Placeholder Bot"
                }
            },
        },
        {
            "id": n["telegram_err"]["id"],
            "name": n["telegram_err"]["name"],
            "type": "n8n-nodes-base.telegram",
            "typeVersion": 1,
            "position": n["telegram_err"]["pos"],
            "parameters": {
                "resource": "message",
                "operation": "sendMessage",
                "chatId": "PLACEHOLDER_CHAT_ID",
                "text": "🚨 Thrift-Cycle Pipeline FAILED\n\nThe daily pipeline encountered an error. Please check the logs.\n\nWorkspace: /home/wahaj/.openclaw/workspace/thrift-cycle/",
                "additionalFields": {},
            },
            "credentials": {
                "telegramBotApi": {
                    "id": "PLACEHOLDER",
                    "name": "Placeholder Bot"
                }
            },
        },
        {
            "id": n["trigger_wf2"]["id"],
            "name": n["trigger_wf2"]["name"],
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 1,
            "position": n["trigger_wf2"]["pos"],
            "parameters": {
                "method": "POST",
                "url": f"{N8N_BASE_URL}/webhook/thrift-cycle-str-alert",
                "sendBody": True,
                "contentType": "json",
                "body": "={{ JSON.stringify({ date: $json.date }) }}",
                "options": {
                    "rejectUnauthorized": False,
                },
            },
        },
    ]

    connections = {
        n["schedule"]["name"]: {
            "main": [[{"node": n["exec"]["name"], "type": "main", "index": 0}]]
        },
        n["exec"]["name"]: {
            "main": [[{"node": n["format"]["name"], "type": "main", "index": 0}]],
            "error": [[{"node": n["telegram_err"]["name"], "type": "main", "index": 0}]]
        },
        n["format"]["name"]: {
            "main": [[{"node": n["telegram_ok"]["name"], "type": "main", "index": 0}]]
        },
        n["telegram_ok"]["name"]: {
            "main": [[{"node": n["trigger_wf2"]["name"], "type": "main", "index": 0}]]
        },
    }

    return {
        "name": "Thrift-Cycle Daily Pipeline",
        "nodes": nodes,
        "connections": connections,
        "settings": {
            "executionOrder": "v1",
            "timezone": "Europe/Berlin",
        },
    }


# ═════════════════════════════════════════════════════════════════════
#  Workflow 2 — Thrift-Cycle STR Alert
# ═════════════════════════════════════════════════════════════════════
def build_workflow_2():
    n = {
        "webhook":     {"id": new_id(), "name": "Webhook Trigger",  "pos": [100,  200]},
        "compare":     {"id": new_id(), "name": "Compare STR",      "pos": [400,  200]},
        "if_hot":      {"id": new_id(), "name": "Has New HOT?",     "pos": [700,  200]},
        "telegram":    {"id": new_id(), "name": "Telegram Alert",   "pos": [1000, 200]},
    }

    compare_js = f"""
const fs = require('fs');
const path = '{DATA_DIR}/';

const files = fs.readdirSync(path)
  .filter(f => f.match(/^\\d{{4}}-\\d{{2}}-\\d{{2}}\\.json$/))
  .sort();

if (files.length < 2) {{
  return [{{ json: {{ hasAlert: false, message: '', chatId: 'PLACEHOLDER_CHAT_ID' }} }}];
}}

const todayFile = files[files.length - 1];
const yesterdayFile = files[files.length - 2];

const today = JSON.parse(fs.readFileSync(path + todayFile, 'utf8'));
const yesterday = JSON.parse(fs.readFileSync(path + yesterdayFile, 'utf8'));

const todayMap = {{}};
(today.results || []).forEach(r => {{
  todayMap[r.keyword + '|' + r.marketplace] = r;
}});

const yesterdayMap = {{}};
(yesterday.results || []).forEach(r => {{
  yesterdayMap[r.keyword + '|' + r.marketplace] = r;
}});

const newHot = [];
Object.keys(todayMap).forEach(key => {{
  const t = todayMap[key];
  const y = yesterdayMap[key];
  if (t && t.sellability >= 0.60 && y && y.sellability < 0.60) {{
    newHot.push({{
      keyword: t.keyword,
      marketplace: t.marketplace,
      todayStr: Math.round(t.sellability * 100),
      yesterdayStr: Math.round(y.sellability * 100)
    }});
  }}
}});

if (newHot.length === 0) {{
  return [{{ json: {{ hasAlert: false, message: '', chatId: 'PLACEHOLDER_CHAT_ID' }} }}];
}}

const lines = newHot.map(item => {{
  return `• ${{item.keyword}} (${{item.marketplace}}) — STR ${{item.todayStr}}% (was ${{item.yesterdayStr}}%)`;
}}).join('\\n');

const message = `🚨 NEW HOT ITEMS DETECTED\n\n${{lines}}\n\nCheck Fleek for sourcing!`;

return [{{ json: {{ hasAlert: true, message, chatId: 'PLACEHOLDER_CHAT_ID' }} }}];
""".strip()

    nodes = [
        {
            "id": n["webhook"]["id"],
            "name": n["webhook"]["name"],
            "type": "n8n-nodes-base.webhook",
            "typeVersion": 1,
            "position": n["webhook"]["pos"],
            "parameters": {
                "httpMethod": "POST",
                "path": "thrift-cycle-str-alert",
                "responseMode": "onReceived",
                "options": {},
            },
        },
        {
            "id": n["compare"]["id"],
            "name": n["compare"]["name"],
            "type": "n8n-nodes-base.code",
            "typeVersion": 1,
            "position": n["compare"]["pos"],
            "parameters": {
                "jsCode": compare_js,
            },
        },
        {
            "id": n["if_hot"]["id"],
            "name": n["if_hot"]["name"],
            "type": "n8n-nodes-base.if",
            "typeVersion": 1,
            "position": n["if_hot"]["pos"],
            "parameters": {
                "conditions": {
                    "boolean": [
                        {
                            "value1": "={{ $json.hasAlert }}",
                            "operation": "equal",
                            "value2": True,
                        }
                    ]
                }
            },
        },
        {
            "id": n["telegram"]["id"],
            "name": n["telegram"]["name"],
            "type": "n8n-nodes-base.telegram",
            "typeVersion": 1,
            "position": n["telegram"]["pos"],
            "parameters": {
                "resource": "message",
                "operation": "sendMessage",
                "chatId": "PLACEHOLDER_CHAT_ID",
                "text": "={{ $json.message }}",
                "additionalFields": {},
            },
            "credentials": {
                "telegramBotApi": {
                    "id": "PLACEHOLDER",
                    "name": "Placeholder Bot"
                }
            },
        },
    ]

    connections = {
        n["webhook"]["name"]: {
            "main": [[{"node": n["compare"]["name"], "type": "main", "index": 0}]]
        },
        n["compare"]["name"]: {
            "main": [[{"node": n["if_hot"]["name"], "type": "main", "index": 0}]]
        },
        n["if_hot"]["name"]: {
            "main": [
                [{"node": n["telegram"]["name"], "type": "main", "index": 0}],
                []
            ]
        },
    }

    return {
        "name": "Thrift-Cycle STR Alert",
        "nodes": nodes,
        "connections": connections,
        "settings": {
            "executionOrder": "v1",
            "timezone": "Europe/Berlin",
        },
    }


# ═════════════════════════════════════════════════════════════════════
#  Main
# ═════════════════════════════════════════════════════════════════════
def main():
    print("=" * 60)
    print("Thrift-Cycle n8n Phase 1 — Workflow Creator")
    print("=" * 60)

    # Test connectivity
    print("\n[1/4] Testing n8n API connectivity...")
    r = api("GET", "/workflows")
    if r.status_code != 200:
        print(f"ERROR: API connectivity failed — HTTP {r.status_code}")
        print(r.text)
        sys.exit(1)
    print("   ✓ API reachable")

    # Build workflows
    print("\n[2/4] Building workflow JSON...")
    wf1 = build_workflow_1()
    wf2 = build_workflow_2()
    print("   ✓ Workflow 1: Thrift-Cycle Daily Pipeline")
    print("   ✓ Workflow 2: Thrift-Cycle STR Alert")

    # Create Workflow 1
    print("\n[3/4] Creating workflows via n8n API...")
    results = {}

    print("   → POST Workflow 1...")
    r1 = api("POST", "/workflows", json=wf1)
    if r1.status_code in (200, 201):
        data1 = r1.json()
        results["wf1"] = {
            "name": data1.get("name", wf1["name"]),
            "id": data1.get("id"),
            "active": data1.get("active", False),
            "ok": True,
        }
        print(f"      ✓ Created — ID: {data1.get('id')}")
    else:
        results["wf1"] = {"ok": False, "status": r1.status_code, "error": r1.text}
        print(f"      ✗ Failed — HTTP {r1.status_code}")
        try:
            err = r1.json()
            print(f"        {json.dumps(err, indent=2)[:500]}")
        except Exception:
            print(f"        {r1.text[:500]}")

    # Create Workflow 2
    print("   → POST Workflow 2...")
    r2 = api("POST", "/workflows", json=wf2)
    if r2.status_code in (200, 201):
        data2 = r2.json()
        results["wf2"] = {
            "name": data2.get("name", wf2["name"]),
            "id": data2.get("id"),
            "active": data2.get("active", False),
            "ok": True,
        }
        print(f"      ✓ Created — ID: {data2.get('id')}")
    else:
        results["wf2"] = {"ok": False, "status": r2.status_code, "error": r2.text}
        print(f"      ✗ Failed — HTTP {r2.status_code}")
        try:
            err = r2.json()
            print(f"        {json.dumps(err, indent=2)[:500]}")
        except Exception:
            print(f"        {r2.text[:500]}")

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    for key, label in [("wf1", "Thrift-Cycle Daily Pipeline"), ("wf2", "Thrift-Cycle STR Alert")]:
        res = results[key]
        if res["ok"]:
            print(f"\n✓ {label}")
            print(f"  ID:        {res['id']}")
            print(f"  Status:    INACTIVE")
            print(f"  Activate:  {N8N_BASE_URL}/workflow/{res['id']}")
        else:
            print(f"\n✗ {label}")
            print(f"  Error: HTTP {res['status']}")

    print("\n" + "-" * 60)
    print("NEXT STEPS for Wahaj:")
    print("-" * 60)
    print("1. Add Telegram Bot credential in n8n:")
    print(f"   {N8N_BASE_URL}/credentials")
    print("   → New → Telegram → Bot Token")
    print("2. Update both workflows to use the real credential")
    print("3. Replace PLACEHOLDER_CHAT_ID with your actual Telegram chat ID")
    print("4. Activate both workflows in the n8n UI")
    print("5. Disable the old OpenClaw cron for the pipeline")
    print("=" * 60)

    # Save results to a file for reference
    with open(f"{PIPELINE_DIR}/n8n_workflow_ids.json", "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nWorkflow IDs saved to: {PIPELINE_DIR}/n8n_workflow_ids.json")


if __name__ == "__main__":
    main()
