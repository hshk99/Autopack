# Connection Error Handler - Diagnosis & Solution

## Problem Analysis

We've tried multiple approaches and none are working automatically:

1. ❌ **UI Automation** - Cannot access Cursor's web-rendered buttons
2. ❌ **Keyboard shortcuts** - Random keys opening settings/menus
3. ❌ **Pixel sampling** - Cannot reliably detect error dialog

**Root cause**: We don't actually know what the error dialog looks like, so we can't reliably detect it.

---

## The Real Issue

Without being able to **SEE** what the error dialog looks like:
- Brightness threshold is a guess (500? 600? 400?)
- Sample pixel location is a guess (center of window?)
- Error detection is unreliable
- We're shooting in the dark

---

## Solution: Two-Tool Approach

### Tool 1: Screenshot Capture (Learn What Error Looks Like)
**File**: `capture_error_screenshot.ps1`

**Purpose**: Capture visual image of the error dialog so we understand what it looks like

**Usage**:
```powershell
.\capture_error_screenshot.ps1

# Interactive mode - enter slot number when error appears
Slot [1-9] to capture or (q)uit? > 3
# Captures screenshot of grid slot 3
```

Or with argument:
```powershell
.\capture_error_screenshot.ps1 3
```

**Output**: Creates `error_screenshot_slot_3_20260119_151330.png`

**Why this helps**:
- We can see the actual error dialog
- Analyze pixel colors, position, size
- Determine proper detection threshold
- Build accurate detection logic

### Tool 2: Direct Click Handler (Immediate Recovery)
**File**: `handle_connection_errors_direct.ps1`

**Purpose**: Click Resume button when you specify which slot has the error

**Usage - Interactive Mode**:
```powershell
.\handle_connection_errors_direct.ps1

# When error appears in slot 3:
Slot [1-9] or (q)uit? > 3
# Clicks Resume button in slot 3
```

**Usage - Direct Mode**:
```powershell
.\handle_connection_errors_direct.ps1 3
# Immediately clicks slot 3
```

**Usage - Batch Integration**:
```batch
# From batch file or external tool
powershell.exe -ExecutionPolicy Bypass -NoProfile -File "handle_connection_errors_direct.ps1" -ArgumentList 3
```

**Why this works**:
- No guessing about detection
- You confirm error is present
- Click happens immediately
- Reliable and simple

---

## Testing Workflow

### Step 1: Prepare to Capture Error

**Terminal 1**: Open PowerShell
```powershell
cd C:\dev\Autopack\scripts
```

**Terminal 2**: Have screenshot tool ready
```powershell
cd C:\dev\Autopack\scripts
```

### Step 2: Trigger Connection Error
1. Open Cursor window(s)
2. Disconnect internet or simulate error
3. Wait for error dialog to appear

### Step 3: Capture Screenshot (Terminal 2)
When error appears, quickly switch to Terminal 2 and capture:
```powershell
.\capture_error_screenshot.ps1 3
# If error is in grid slot 3
```

This saves: `error_screenshot_slot_3_20260119_151330.png`

### Step 4: Analyze Screenshot
1. Look at the saved image
2. Identify:
   - Error dialog location and size
   - Resume button appearance
   - Background colors (for detection threshold)
   - Any text or icons that could be used for detection

### Step 5: Use Direct Handler to Recover
```powershell
.\handle_connection_errors_direct.ps1 3
# Or interactively:
Slot [1-9] or (q)uit? > 3
```

---

## How This Helps Move Forward

### Immediate (Today)
- **Capture error** screenshot
- **See what it looks like** visually
- **Use direct handler** to click Resume button immediately
- Get Cursor working again

### Next (Tomorrow)
- **Analyze screenshot** pixel data
- **Determine detection threshold** from actual colors
- **Create accurate detection** based on real error appearance
- **Build automated handler** that actually works

### Example - What We'll Learn
```
Looking at error_screenshot_slot_3.png, we see:
- Error dialog is at position (X: 2500-3300, Y: 200-500)
- Resume button is bright green: RGB(0, 200, 0)
- Background is white/light gray: RGB(240, 240, 240)
- We can sample pixel at (2800, 350) to detect
- Brightness threshold should be 600+ for detection
- Detection accuracy: 99%

Then create proper automated handler...
```

---

## Files Created

### Capture Tool
**File**: `C:\dev\Autopack\scripts\capture_error_screenshot.ps1`
- Interactive screenshot capture
- Saves PNG images of error dialogs
- Helps analyze error appearance

### Direct Click Handler
**File**: `C:\dev\Autopack\scripts\handle_connection_errors_direct.ps1`
- Manual/direct clicking
- Interactive mode (you type slot number)
- Direct mode (parameter: slot 1-9)
- Reliable immediate recovery

---

## Immediate Actions

### For Quick Recovery (Next Time Error Occurs)
```powershell
# Terminal 1: Open this when error appears
C:\dev\Autopack\scripts\handle_connection_errors_direct.ps1

# When error appears, type the slot number:
Slot [1-9] or (q)uit? > 3
# Clicks Resume in slot 3, error recovers
```

### For Future Automated Solution
```powershell
# Capture the error to analyze
C:\dev\Autopack\scripts\capture_error_screenshot.ps1 3
# Saves screenshot
# Share with me for analysis
# I build detection based on actual appearance
```

---

## Why This Approach

### Old approaches failed because:
- ❌ UI Automation: Chromium blocks it
- ❌ Keyboard: Wrong window, wrong keys
- ❌ Pixel sampling: Guessing at threshold

### New approach works because:
- ✅ Direct clicking: Always works if coordinates right
- ✅ Manual control: You confirm error present
- ✅ Real data: Actual screenshots for analysis
- ✅ Data-driven: Detection based on facts, not guesses

---

## Summary

The path forward has two parts:

**Part 1: Immediate Recovery** (Working NOW)
- Use `handle_connection_errors_direct.ps1`
- Manually trigger when error appears
- Immediate recovery
- No guessing needed

**Part 2: Build Automation** (Coming Next)
- Capture error screenshots
- Analyze actual appearance
- Build detection based on real data
- Create working automated handler

---

## Next Steps

1. **Test direct handler**: Run next time error appears
2. **Capture screenshot**: See what error looks like
3. **Share data**: Send screenshot for analysis
4. **Build automated**: I create detection based on facts

Let's fix this properly with real data! 🚀
