#!/bin/bash
# File verification script for GPT-5.2 review materials

echo "Verifying all 27 files for GPT-5.2 review..."
echo ""

FOUND=0
MISSING=0

FILES=(
    ".autonomous_runs/lovable-integration-v1/GPT5_REVIEW_PROMPT.md"
    ".autonomous_runs/lovable-integration-v1/GPT5_REFERENCE_FILES.md"
    ".autonomous_runs/lovable-integration-v1/GPT5_VALIDATION_REPORT.md"
    ".autonomous_runs/lovable-integration-v1/run_config.json"
    ".autonomous_runs/lovable-integration-v1/README.md"
    ".autonomous_runs/lovable-integration-v1/phases/phase_01_lovable-p1-agentic-file-search.md"
    ".autonomous_runs/lovable-integration-v1/phases/phase_02_lovable-p1-intelligent-file-selection.md"
    ".autonomous_runs/lovable-integration-v1/phases/phase_03_lovable-p1-build-validation.md"
    ".autonomous_runs/lovable-integration-v1/phases/phase_04_lovable-p1-dynamic-retry-delays.md"
    ".autonomous_runs/lovable-integration-v1/phases/phase_05_lovable-p2-package-detection.md"
    ".autonomous_runs/lovable-integration-v1/phases/phase_06_lovable-p2-hmr-error-detection.md"
    ".autonomous_runs/lovable-integration-v1/phases/phase_07_lovable-p2-missing-import-autofix.md"
    ".autonomous_runs/lovable-integration-v1/phases/phase_08_lovable-p2-conversation-state.md"
    ".autonomous_runs/lovable-integration-v1/phases/phase_09_lovable-p2-fallback-chain.md"
    ".autonomous_runs/lovable-integration-v1/phases/phase_10_lovable-p3-morph-fast-apply.md"
    ".autonomous_runs/lovable-integration-v1/phases/phase_11_lovable-p3-system-prompts.md"
    ".autonomous_runs/lovable-integration-v1/phases/phase_12_lovable-p3-context-truncation.md"
    ".autonomous_runs/file-organizer-app-v1/archive/research/LOVABLE_DEEP_DIVE_INCORPORATION_PLAN.md"
    ".autonomous_runs/file-organizer-app-v1/archive/research/IMPLEMENTATION_PLAN_LOVABLE_INTEGRATION.md"
    ".autonomous_runs/file-organizer-app-v1/archive/research/EXECUTIVE_SUMMARY.md"
    ".autonomous_runs/file-organizer-app-v1/archive/research/COMPARATIVE_ANALYSIS_DEVIKA_OPCODE_LOVABLE.md"
    ".autonomous_runs/file-organizer-app-v1/archive/research/CLAUDE_CODE_CHROME_LOVABLE_PHASE5_ANALYSIS.md"
    "README.md"
    "docs/FUTURE_PLAN.md"
    "docs/BUILD_HISTORY.md"
    ".autonomous_runs/lovable-integration-v1/FILE_LOCATIONS.md"
    ".autonomous_runs/lovable-integration-v1/generate_all_phases.py"
)

for file in "${FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "✅ Found: $file"
        ((FOUND++))
    else
        echo "❌ Missing: $file"
        ((MISSING++))
    fi
done

echo ""
echo "📊 Summary:"
echo "Found: $FOUND files"
echo "Missing: $MISSING files"
echo ""

if [ $MISSING -eq 0 ]; then
    echo "✅ All files verified! Ready for GPT-5.2 review."
else
    echo "⚠️ Some files are missing. Please check the paths above."
fi
