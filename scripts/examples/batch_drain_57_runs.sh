#!/bin/bash
# Example: Efficiently process the 57 runs with failed phases
#
# This script demonstrates how to use the batch drain controller
# to process failed phases across all runs in manageable batches.

set -e  # Exit on error

echo "==================================================================="
echo "Batch Drain Controller - Process 57 Runs with Failed Phases"
echo "==================================================================="
echo ""

# Configuration
BATCH_SIZE=20
TOTAL_PHASES_TARGET=100  # Process 100 failed phases total

echo "Configuration:"
echo "  Batch Size: $BATCH_SIZE phases per batch"
echo "  Target: Process $TOTAL_PHASES_TARGET failed phases total"
echo ""

# Step 1: Check current state
echo "Step 1: Checking current state..."
python scripts/list_run_counts.py | head -20
echo ""

# Step 2: Run first batch (dry run to preview)
echo "Step 2: Preview first batch (dry run)..."
python scripts/batch_drain_controller.py \
    --batch-size $BATCH_SIZE \
    --dry-run
echo ""

read -p "Proceed with actual drain? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted by user"
    exit 0
fi

# Step 3: Process batches until target reached
PROCESSED=0
BATCH_NUM=1

while [ $PROCESSED -lt $TOTAL_PHASES_TARGET ]; do
    REMAINING=$((TOTAL_PHASES_TARGET - PROCESSED))
    CURRENT_BATCH_SIZE=$BATCH_SIZE

    if [ $REMAINING -lt $BATCH_SIZE ]; then
        CURRENT_BATCH_SIZE=$REMAINING
    fi

    echo "==================================================================="
    echo "Batch $BATCH_NUM: Processing $CURRENT_BATCH_SIZE phases"
    echo "Progress: $PROCESSED/$TOTAL_PHASES_TARGET processed so far"
    echo "==================================================================="
    echo ""

    # Run batch drain
    python scripts/batch_drain_controller.py \
        --batch-size $CURRENT_BATCH_SIZE

    EXIT_CODE=$?

    # Update progress
    PROCESSED=$((PROCESSED + CURRENT_BATCH_SIZE))
    BATCH_NUM=$((BATCH_NUM + 1))

    # Check if we should continue
    if [ $EXIT_CODE -ne 0 ]; then
        echo ""
        echo "Warning: Batch completed with errors (exit code: $EXIT_CODE)"
        read -p "Continue to next batch? (y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo "Stopping after $PROCESSED phases processed"
            break
        fi
    fi

    echo ""
    echo "Batch $((BATCH_NUM - 1)) complete. Pausing 5 seconds before next batch..."
    sleep 5
done

echo ""
echo "==================================================================="
echo "Batch Drain Complete"
echo "==================================================================="
echo ""
echo "Final state:"
python scripts/list_run_counts.py | head -20
echo ""
echo "Review session files in: .autonomous_runs/batch_drain_sessions/"
