# Capture All 9 Grid Slots - Phase 2 Analysis Tool

## Overview

The "Capture All Slots" tool takes simultaneous screenshots of all 9 Cursor grid windows to analyze error patterns. This is essential for improving Phase 2 automated detection.

## Why This is Useful

### For Phase 2 Improvement
- **See all errors at once** - Understand error patterns across all windows
- **Compare error dialogs** - See if errors look the same in all slots or vary
- **Analyze visual changes** - Determine pixel change percentages for Phase 2 tuning
- **Build accurate detection** - Real data → better detection algorithms

### For Troubleshooting
- **Diagnose issues** - See state of all windows when problem occurs
- **Analyze patterns** - Understand when and how errors appear
- **Verify fixes** - Confirm if all windows show consistent behavior

## How to Use

### From Stream Deck Button

**Setup**:
1. In Stream Deck, add "Open" action
2. Set file path to: `C:\dev\Autopack\scripts\capture_all_slots.bat`
3. Label button: "📸 Capture All Error" or similar

**Usage**:
1. When errors appear, click Stream Deck button
2. All 9 windows captured simultaneously
3. Screenshots saved to `C:\dev\Autopack\error_analysis\`
4. Window shows completion status

### From Command Line

**Batch launcher**:
```batch
C:\dev\Autopack\scripts\capture_all_slots.bat
```

**PowerShell**:
```powershell
& "C:\dev\Autopack\scripts\capture_all_slots.ps1"
```

## Expected Output

### Console Output
```
========== CAPTURE ALL 9 GRID SLOTS ===========

Capturing all 9 Cursor windows simultaneously...
This creates a complete snapshot for Phase 2 analysis

Capturing all slots at 14:23:45...

  Slot 1... [OK]
  Slot 2... [OK]
  Slot 3... [OK]
  Slot 4... [OK]
  Slot 5... [OK]
  Slot 6... [OK]
  Slot 7... [OK]
  Slot 8... [OK]
  Slot 9... [OK]

========== CAPTURE COMPLETE ==========

Captured: 9 / 9 slots

All 9 screenshots saved successfully!

Output location:
  C:\dev\Autopack\error_analysis

Timestamp: 20260119_142345

Files created:
  ✓ error_snapshot_slot_1_20260119_142345.png
  ✓ error_snapshot_slot_2_20260119_142345.png
  ✓ error_snapshot_slot_3_20260119_142345.png
  ✓ error_snapshot_slot_4_20260119_142345.png
  ✓ error_snapshot_slot_5_20260119_142345.png
  ✓ error_snapshot_slot_6_20260119_142345.png
  ✓ error_snapshot_slot_7_20260119_142345.png
  ✓ error_snapshot_slot_8_20260119_142345.png
  ✓ error_snapshot_slot_9_20260119_142345.png

NEXT STEP FOR PHASE 2 IMPROVEMENT:
  1. Close this window
  2. Open the error_analysis folder
  3. Review the 9 screenshots
  4. Share them with me for Phase 2 visual analysis

These screenshots will help us:
  ✓ See what error dialogs actually look like
  ✓ Analyze error patterns across all windows
  ✓ Determine accurate detection thresholds
  ✓ Build Phase 2 detection based on REAL data

========================================
```

### Files Created
```
C:\dev\Autopack\error_analysis\
├─ error_snapshot_slot_1_20260119_142345.png
├─ error_snapshot_slot_2_20260119_142345.png
├─ error_snapshot_slot_3_20260119_142345.png
├─ error_snapshot_slot_4_20260119_142345.png
├─ error_snapshot_slot_5_20260119_142345.png
├─ error_snapshot_slot_6_20260119_142345.png
├─ error_snapshot_slot_7_20260119_142345.png
├─ error_snapshot_slot_8_20260119_142345.png
└─ error_snapshot_slot_9_20260119_142345.png
```

All 9 files timestamped together (same timestamp = captured simultaneously).

## Workflow

### When Connection Error Occurs

1. **Notice error** in one or more Cursor windows
2. **Click Stream Deck button** (or run batch file)
3. **All 9 windows captured** simultaneously
4. **Wait for completion message**
5. **Review screenshots** in error_analysis folder

### What to Look For

In the captured screenshots:

- **Which slots have errors?** (1-9, or multiple?)
- **What does error dialog look like?** (size, position, colors)
- **Is error the same across slots?** (or different patterns?)
- **How much of window is covered?** (percentage)
- **What colors are in error dialog?** (for detection tuning)

### Share for Analysis

Once you have the 9 screenshots:

1. Open `C:\dev\Autopack\error_analysis\`
2. Select all 9 PNG files with that timestamp
3. Share with me
4. I'll analyze and improve Phase 2 detection

## Stream Deck Setup Examples

### Example 1: Simple Button
```
Button Label: "📸 All Errors"
Action Type: Open
File: C:\dev\Autopack\scripts\capture_all_slots.bat
```

### Example 2: Multi-Action Button
```
Action 1: Open → capture_all_slots.bat
Action 2: Show Alert → "Capturing 9 slots..."
Action 3: Delay → 2 seconds
Action 4: Open File → C:\dev\Autopack\error_analysis
```
(Opens folder after capture completes)

### Example 3: With Phase 1 Recovery
```
Row 1:
  - Button: "📸 Capture" → capture_all_slots.bat
  - Button: "🔧 Phase 1" → handle_connection_errors.bat

When error occurs:
  1. Click "📸 Capture" to get screenshots
  2. Click "🔧 Phase 1" to manually recover
  3. Use screenshots for Phase 2 analysis
```

## Technical Details

### What It Does
1. Takes screenshot of each grid window (1707x480 pixels)
2. Saves as PNG with timestamp
3. Creates all 9 files in rapid succession (same timestamp)
4. Reports success/failure for each slot

### Grid Positions Captured
```
Slot 1 (0, 0)           Slot 2 (1707, 0)        Slot 3 (3414, 0)
Slot 4 (0, 480)         Slot 5 (1707, 480)      Slot 6 (3414, 480)
Slot 7 (0, 960)         Slot 8 (1707, 960)      Slot 9 (3414, 960)
```

### File Naming
```
error_snapshot_slot_[1-9]_[TIMESTAMP].png
Example: error_snapshot_slot_3_20260119_142345.png
```

Timestamp format: `yyyyMMdd_HHmmss` (all 9 files get same timestamp)

### Output Directory
```
C:\dev\Autopack\error_analysis\
```

Created automatically if it doesn't exist.

## Usage Patterns

### Pattern 1: Immediate Capture
```
1. Connection error appears
2. Click Stream Deck button immediately
3. All 9 slots captured with error visible
4. Provides snapshot of exact moment error occurred
```

### Pattern 2: Before & After
```
1. Capture all slots (error present)
2. Use Phase 1 to recover
3. Capture all slots again (recovered)
4. Compare before/after to see what changed
```

### Pattern 3: Analysis Session
```
1. Run multiple captures at different times
2. Each capture gets unique timestamp
3. Collect multiple error snapshots
4. Share all timestamps for pattern analysis
```

## Troubleshooting

### Issue: One or more slots failed to capture
- **Cause**: Window might be minimized or off-screen
- **Solution**: Verify all 9 Cursor windows are visible and positioned correctly
- **Retry**: Run capture again

### Issue: No error dialog visible in screenshots
- **Cause**: Error already recovered before capture completed
- **Solution**: Prepare to click immediately when error appears
- **Tip**: Have Stream Deck button ready before triggering error

### Issue: Screenshot appears blank
- **Cause**: Window might not be rendering properly
- **Solution**: Check if Cursor window is active/focused
- **Retry**: Try again after ensuring windows are visible

## Next Steps

### When You Have Screenshots

1. **Review 9 screenshots** - What do errors look like?
2. **Identify patterns** - Same error in all slots or different?
3. **Note characteristics** - Size, colors, position
4. **Share with me** - All 9 files with same timestamp
5. **I analyze** - Build detection based on real data
6. **Phase 2 improved** - Automatic detection gets better

### Phase 2 Improvement Process

```
Current → You capture errors → I analyze → Phase 2 improved → Accurate automation
```

## Files

**Main tool**:
- `scripts/capture_all_slots.bat` - Launcher (use from Stream Deck)
- `scripts/capture_all_slots.ps1` - Implementation

**Supporting tools**:
- `scripts/capture_error_screenshot.bat` - Single slot capture (fallback)
- `scripts/capture_error_screenshot.ps1` - Single slot implementation

**Output**:
- `C:\dev\Autopack\error_analysis\` - Where screenshots are saved

## Summary

**Capture All 9 Grid Slots Tool**:
- ✅ One-click capture from Stream Deck
- ✅ All 9 windows captured simultaneously
- ✅ Creates timestamped PNG files
- ✅ Essential for Phase 2 visual analysis
- ✅ Helps build accurate error detection

**Stream Deck Integration**:
- Easy button setup
- Quick capture of error state
- Perfect for immediate response

**Phase 2 Improvement**:
- Real screenshots → accurate detection
- Visual data → better thresholds
- Multiple captures → pattern analysis

**Ready to use! Click Stream Deck button when error appears.**
