# Autopack Ralph Evolution Loop

This directory contains the Ralph continuous evolution setup for autonomously improving Autopack toward its README ideal state.

## What This Does

Runs a continuous **discovery → implementation → verification** loop:

1. **DISCOVER**: Scans for gaps using comprehensive_scan_prompt_v2.md methodology
2. **IMPLEMENT**: Closes found gaps by implementing IMPs
3. **VERIFY**: Checks if ideal state is reached
4. **LOOP**: If not at ideal state, goes back to discovery

This continues until Autopack reaches its ideal state or max cycles are exceeded.

## Files

| File | Purpose |
|------|---------|
| `PROMPT_evolution.md` | Main prompt given to Claude each iteration |
| `IDEAL_STATE_DEFINITION.md` | Machine-verifiable definition of "done" |
| `guardrails.md` | Accumulated learnings (grows over time) |
| `evolution_loop.sh` | Bash orchestration script |
| `evolution_loop.bat` | Windows orchestration script |
| `verify_ideal_state.sh` | Quick verification (Bash) |
| `verify_ideal_state.bat` | Quick verification (Windows) |

## Quick Start

### Check Current Status

```bash
# Git Bash / WSL
./ralph/verify_ideal_state.sh

# Windows CMD
ralph\verify_ideal_state.bat
```

### Run Evolution Loop

```bash
# Git Bash / WSL (default: 50 cycles, opus model)
cd C:/dev/Autopack
./ralph/evolution_loop.sh

# With custom settings
./ralph/evolution_loop.sh 100 sonnet  # 100 cycles, sonnet model

# Windows CMD
cd C:\dev\Autopack
ralph\evolution_loop.bat

# With custom settings
ralph\evolution_loop.bat 100 sonnet
```

### Monitor Progress

```bash
# Watch logs
tail -f .ralph/logs/cycle_*.log

# Check IMP status
python -c "import json; d=json.load(open('C:/Users/hshk9/OneDrive/Backup/Desktop/AUTOPACK_IMPS_MASTER.json')); print(f'Unimplemented: {d[\"statistics\"][\"unimplemented\"]}')"
```

## How It Works

### Outer Loop (Bash/Batch Script)

```
for cycle in 1..MAX_CYCLES:
    Phase A: Discovery (find new gaps)
    Phase B: Implementation (close gaps)
    Phase C: Ideal State Check

    if ideal_state_reached:
        exit SUCCESS
```

### Inner Loop (Claude)

Each Claude invocation:
1. Reads `PROMPT_evolution.md` + `guardrails.md`
2. Executes current phase (discovery/implementation/verification)
3. Updates `AUTOPACK_IMPS_MASTER.json`
4. Outputs phase completion markers
5. Context resets on next iteration (fresh start)

### State Persistence

Progress persists through:
- **Git commits**: Code changes survive context resets
- **AUTOPACK_IMPS_MASTER.json**: Tracks discovered/completed IMPs
- **guardrails.md**: Learnings accumulate across cycles
- **BUILD_HISTORY.md**: Documents what was done

## Configuration

### Cycle Limits

| Parameter | Default | Purpose |
|-----------|---------|---------|
| `MAX_CYCLES` | 50 | Maximum evolution cycles |
| `DISCOVERY_MAX_ITER` | 10 | Max iterations per discovery phase |
| `IMPLEMENTATION_MAX_ITER` | 20 | Max iterations per implementation phase |

### Circuit Breaker

The loop stops early if:
- **3 consecutive no-progress iterations**: Stuck on same problem
- **Ideal state reached**: Success!
- **Manual interrupt**: Ctrl+C

### Model Selection

```bash
# Use Opus (default - best for complex reasoning)
./ralph/evolution_loop.sh 50 opus

# Use Sonnet (faster, cheaper, good for simpler tasks)
./ralph/evolution_loop.sh 50 sonnet
```

## Cost Estimation

- **Per iteration**: ~$1-3 (depends on context size)
- **Per cycle**: ~$10-30 (discovery + implementation + verification)
- **Full evolution**: ~$100-500 (varies by starting state)

Set `MAX_CYCLES` conservatively until you understand consumption patterns.

## Safety

### Safeguards Built In

1. **Max iterations**: Prevents infinite loops
2. **Circuit breaker**: Stops on repeated failures
3. **Pre-commit hooks**: Formatting/linting validation
4. **Test requirements**: Changes validated before commit
5. **Guardrails**: Prevent repeated mistakes

### Recommended Practices

1. **Run in isolated environment** if using `--dangerously-skip-permissions`
2. **Review first few cycles** before leaving unattended
3. **Set reasonable MAX_CYCLES** (start with 10-20)
4. **Monitor costs** via Claude API dashboard
5. **Keep git clean**: Easy rollback if needed

## Troubleshooting

### "Claude CLI not found"

Install Claude Code:
```bash
npm install -g @anthropic-ai/claude-code
```

### "IMP tracking file not found"

The file should be at:
```
C:\Users\hshk9\OneDrive\Backup\Desktop\AUTOPACK_IMPS_MASTER.json
```

### "No progress for 3 iterations"

Circuit breaker triggered. Check:
1. Logs in `.ralph/logs/`
2. `guardrails.md` for blocking issues
3. `docs/DEBUG_LOG.md` for error patterns

### Manual Rollback

If something goes wrong:
```bash
git log --oneline -20  # Find last good commit
git reset --hard <commit-sha>
```

## Sources

Based on Ralph methodology from:
- [Geoffrey Huntley's Ralph Essay](https://ghuntley.com/ralph/)
- [Ralph Playbook](https://github.com/ClaytonFarr/ralph-playbook)
- [ralph-claude-code](https://github.com/frankbria/ralph-claude-code)
