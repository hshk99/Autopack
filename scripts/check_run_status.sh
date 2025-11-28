#!/bin/bash
# Quick status check for Autopack run
# Usage: bash scripts/check_run_status.sh [run-id]

RUN_ID="${1:-fileorg-phase2-beta}"
API_URL="${AUTOPACK_API_URL:-http://localhost:8000}"

curl -s "$API_URL/runs/$RUN_ID" | python -c "
import sys, json
data = json.load(sys.stdin)

print('=' * 80)
print('AUTOPACK RUN STATUS: {}'.format(data['id']))
print('=' * 80)
print('')
print('State: {}'.format(data['state']))
print('Tokens Used: {:,} / 150,000 ({:.1f}%)'.format(
    data.get('tokens_used', 0),
    data.get('tokens_used', 0) / 1500
))
print('')
print('PHASE PROGRESS:')
print('-' * 80)

total_phases = 0
completed = 0
queued = 0
failed = 0

for tier in data.get('tiers', []):
    print('\\n  Tier {}: {} [{}]'.format(tier['tier_index'], tier['name'], tier['state']))

    for phase in tier.get('phases', []):
        total_phases += 1
        state = phase['state']
        if state == 'COMPLETE':
            completed += 1
            icon = '✅'
        elif state == 'QUEUED':
            queued += 1
            icon = '⏳'
        elif state == 'EXECUTING':
            icon = '🔄'
        elif state == 'FAILED':
            failed += 1
            icon = '❌'
        elif state == 'BLOCKED':
            icon = '⚠️'
        else:
            icon = '❓'

        tokens_info = ''
        if phase.get('tokens_used'):
            tokens_info = ' ({:,} tokens)'.format(phase['tokens_used'])

        print('    {} Phase {}: {}{}'.format(
            icon,
            phase.get('phase_index', '?'),
            phase['name'],
            tokens_info
        ))

print('')
print('=' * 80)
print('SUMMARY:')
print('  Total Phases: {}'.format(total_phases))
print('  Completed: {} ({:.0f}%)'.format(completed, (completed/total_phases*100) if total_phases > 0 else 0))
print('  Queued: {}'.format(queued))
print('  Failed: {}'.format(failed))
print('=' * 80)
"
