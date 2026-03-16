#!/bin/bash

# Check Stripe revenue daily
# Logs to memory/stripe-revenue.md

set -e

WORKSPACE="/home/kyant/.openclaw/workspace"
REVENUE_LOG="$WORKSPACE/memory/stripe-revenue.md"
ENV_FILE="$WORKSPACE/.env.local"

# Load Stripe key
if [ ! -f "$ENV_FILE" ]; then
  echo "✗ .env.local not found"
  exit 1
fi

STRIPE_KEY=$(grep STRIPE_SECRET_KEY "$ENV_FILE" | cut -d= -f2)

# Get charges from Stripe
REVENUE=$(python3 << PYTHON
import json, urllib.request, os

stripe_key = "$STRIPE_KEY"
url = "https://api.stripe.com/v1/charges?limit=100"
req = urllib.request.Request(url, headers={"Authorization": f"Bearer {stripe_key}"})

try:
    with urllib.request.urlopen(req) as r:
        data = json.loads(r.read().decode())
        total = sum(c['amount'] for c in data.get('data', []) if c['status'] == 'succeeded') / 100
        print(f"{total:.2f}")
except:
    print("0.00")
PYTHON
)

# Log
echo "## $(date '+%Y-%m-%d %H:%M:%S')" >> "$REVENUE_LOG"
echo "Revenue: \$$REVENUE" >> "$REVENUE_LOG"
echo "" >> "$REVENUE_LOG"

echo "✓ Revenue logged: \$$REVENUE"
