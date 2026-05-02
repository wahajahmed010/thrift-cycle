#!/bin/bash
# Thrift-Cycle Daily Pipeline Runner
# Usage: bash run_pipeline.sh

cd "$(dirname "$0")"

echo "=== Thrift-Cycle Pipeline ==="
echo "Date: $(date -u +%Y-%m-%d_%H:%M)"
echo ""

# 1. Ensure auth token is valid
python3 -c "
import sys
sys.path.insert(0, '.')
from ebay_auth import get_token
token = get_token()
print('Auth OK')
"

if [ $? -ne 0 ]; then
    echo "ERROR: Auth failed"
    exit 1
fi

# 2. Run pipeline
python3 pipeline.py

echo ""
echo "=== Pipeline Done ==="
