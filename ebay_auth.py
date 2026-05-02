#!/usr/bin/env python3
"""eBay OAuth2 token manager for Thrift-Cycle Predictor.
Handles client credentials flow (Application token) for Browse/Finding API.
Auto-refreshes tokens before expiry.
"""

import json
import urllib.request
import urllib.parse
import base64
import time
import os
from pathlib import Path
import sys

# DNS patch for api.ebay.com resolution
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dns_patch

CREDENTIALS_PATH = Path.home() / ".openclaw" / ".ebay_credentials"
TOKEN_PATH = Path.home() / ".openclaw" / ".ebay_tokens.json"

TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
SCOPE = "https://api.ebay.com/oauth/api_scope"

def load_credentials():
    """Load App ID and Cert ID from credentials file."""
    with open(CREDENTIALS_PATH) as f:
        creds = json.load(f)
    return creds["app_id"], creds["cert_id"], creds["dev_id"]

def get_token():
    """Get a valid eBay Application token. Refreshes if expired or missing."""
    # Check existing token
    if TOKEN_PATH.exists():
        with open(TOKEN_PATH) as f:
            tokens = json.load(f)
        if tokens.get("expires_at", 0) > time.time() + 300:  # 5 min buffer
            return tokens["access_token"]

    # Fetch new token using client credentials flow
    app_id, cert_id, dev_id = load_credentials()

    auth = base64.b64encode(f"{app_id}:{cert_id}".encode()).decode()
    data = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "scope": SCOPE,
    }).encode()

    req = urllib.request.Request(TOKEN_URL, data=data, headers={
        "Authorization": f"Basic {auth}",
        "Content-Type": "application/x-www-form-urlencoded",
    })

    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        raise RuntimeError(f"eBay OAuth failed ({e.code}): {body}")

    tokens = {
        "access_token": result["access_token"],
        "expires_at": time.time() + result.get("expires_in", 7200),
        "token_type": result.get("token_type", "Application Access Token"),
    }

    # Save token
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(TOKEN_PATH, "w") as f:
        json.dump(tokens, f, indent=2)
    os.chmod(TOKEN_PATH, 0o600)

    return tokens["access_token"]

def api_request(url, method="GET", data=None):
    """Make an authenticated eBay API request."""
    token = get_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    if data:
        data = json.dumps(data).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())

if __name__ == "__main__":
    token = get_token()
    print(f"Token acquired (expires in {int((json.load(open(TOKEN_PATH))['expires_at'] - time.time()) / 60)} min)")
    print(f"Type: Application Access Token")