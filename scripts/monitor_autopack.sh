#!/bin/bash
# Monitor Autopack Run Progress
# Usage: bash scripts/monitor_autopack.sh [run-id]

RUN_ID="${1:-fileorg-phase2-beta}"
API_URL="${AUTOPACK_API_URL:-http://localhost:8000}"

echo "========================================"
echo "AUTOPACK RUN MONITOR: $RUN_ID"
echo "========================================"
echo ""

# Watch mode - refresh every 5 seconds
watch -n 5 "curl -s $API_URL/runs/$RUN_ID | python -c \"
import sys, json
data = json.load(sys.stdin)

print('Run:', data['id'])
print('State:', data['state'])
print('Tokens Used:', data.get('tokens_used', 0), '/ 150,000')
print('')
print('TIERS:')
print('-' * 60)

for tier in data.get('tiers', []):
    print(f\"  Tier {tier['tier_index']}: {tier['name']} [{tier['state']}]\")

    for phase in tier.get('phases', []):
        status_icon = {'QUEUED': '⏳', 'EXECUTING': '🔄', 'COMPLETE': '✅', 'FAILED': '❌', 'BLOCKED': '⚠️'}.get(phase['state'], '❓')
        print(f\"    {status_icon} {phase['name']} ({phase['state']})\")
        if phase.get('tokens_used'):
            print(f\"       Tokens: {phase['tokens_used']}\")
    print('')
\""
