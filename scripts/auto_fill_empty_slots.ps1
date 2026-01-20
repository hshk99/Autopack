# Auto-fill empty cursor slots with next available [READY] prompts
# Main orchestrator for Option B workflow
# Respects wave boundaries - does NOT cross to next wave
# Usage: .\auto_fill_empty_slots.ps1
# StreamDeck: Use auto_fill_empty_slots.ps1 (no .bat wrapper needed for PowerShell)

param(
    [int]$WaveNumber = 0,  # 0 = auto-detect from Prompts_All_Waves.md
    [string]$WaveFile = "",
    [switch]$DryRun,
    [switch]$Interactive,
    [switch]$Kill  # Kill all running Cursor processes and cleanup
)

# Define WindowHelper if not already loaded
if (-not ([System.Management.Automation.PSTypeName]'WindowHelper').Type) {
Add-Type @"
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;

public class WindowHelper {
    [DllImport("user32.dll")]
    public static extern bool MoveWindow(IntPtr hWnd, int X, int Y, int nWidth, int nHeight, bool bRepaint);

    [DllImport("user32.dll")]
    public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);

    [DllImport("user32.dll")]
    public static extern bool IsIconic(IntPtr hWnd);

    [DllImport("user32.dll")]
    public static extern bool IsWindowVisible(IntPtr hWnd);

    [DllImport("user32.dll")]
    public static extern int GetWindowTextLength(IntPtr hWnd);

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    public static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);

    [DllImport("user32.dll")]
    public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);

    [DllImport("user32.dll")]
    public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);

    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr hWnd);

    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

    [DllImport("user32.dll")]
    public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);

    [StructLayout(LayoutKind.Sequential)]
    public struct RECT {
        public int Left;
        public int Top;
        public int Right;
        public int Bottom;
    }

    public static List<IntPtr> GetWindowsByProcessName(string processName) {
        var windows = new List<IntPtr>();
        var processIds = new HashSet<uint>();

        foreach (var proc in System.Diagnostics.Process.GetProcessesByName(processName)) {
            processIds.Add((uint)proc.Id);
        }

        EnumWindows((hWnd, lParam) => {
            uint procId;
            GetWindowThreadProcessId(hWnd, out procId);

            if (processIds.Contains(procId) && IsWindowVisible(hWnd)) {
                int length = GetWindowTextLength(hWnd);
                if (length > 0) {
                    StringBuilder sb = new StringBuilder(length + 1);
                    GetWindowText(hWnd, sb, sb.Capacity);
                    string title = sb.ToString();
                    if (!string.IsNullOrWhiteSpace(title) && title.Length > 1) {
                        windows.Add(hWnd);
                    }
                }
            }
            return true;
        }, IntPtr.Zero);

        return windows;
    }

    public static string GetWindowTitle(IntPtr hWnd) {
        int length = GetWindowTextLength(hWnd);
        if (length == 0) return "";
        StringBuilder sb = new StringBuilder(length + 1);
        GetWindowText(hWnd, sb, sb.Capacity);
        return sb.ToString();
    }

    public static RECT GetWindowRect(IntPtr hWnd) {
        RECT rect;
        GetWindowRect(hWnd, out rect);
        return rect;
    }
}
"@
}

Write-Host ""
Write-Host "============ AUTO-FILL EMPTY SLOTS ============" -ForegroundColor Cyan
Write-Host ""

# Auto-detect wave file if not provided
if ([string]::IsNullOrWhiteSpace($WaveFile)) {
    $backupDir = "C:\Users\hshk9\OneDrive\Backup\Desktop"
    $promptsFile = Join-Path $backupDir "Prompts_All_Waves.md"

    if (Test-Path $promptsFile) {
        $WaveFile = $promptsFile
        Write-Host "[AUTO-DETECT] Using: Prompts_All_Waves.md"
    } else {
        # Fallback to old Wave*_All_Phases.md format for backwards compatibility
        $waveFiles = @(Get-ChildItem -Path $backupDir -Filter "Wave*_All_Phases.md" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending)

        if ($waveFiles.Count -eq 0) {
            Write-Host "[ERROR] No Prompts_All_Waves.md or Wave*_All_Phases.md file found" -ForegroundColor Red
            Write-Host "First run: .\\generate_wave_prompts.ps1"
            exit 1
        }

        $WaveFile = $waveFiles[0].FullName
        Write-Host "[AUTO-DETECT] Using: $($waveFiles[0].Name) (legacy format)"

        # Extract wave number from filename
        if ($waveFiles[0].Name -match "Wave(\d)_") {
            $WaveNumber = [int]$Matches[1]
        }
    }
}

if (-not (Test-Path $WaveFile)) {
    Write-Host "[ERROR] Wave file not found: $WaveFile" -ForegroundColor Red
    exit 1
}

Write-Host "[INFO] Wave: $WaveNumber"
Write-Host "[INFO] File: $WaveFile"
Write-Host ""

# ============ KILL MODE: Safely close background Cursor windows ============
if ($Kill) {
    Write-Host "KILL MODE: Safely closing background Cursor windows..." -ForegroundColor Red
    Write-Host ""
    Write-Host "[IMPORTANT] This will:"
    Write-Host "  ✓ Close all BACKGROUND Cursor windows (those opened by auto_fill)"
    Write-Host "  ✓ KEEP your OLDEST/MAIN Cursor window intact"
    Write-Host "  ✓ NOT close VSCode or Claude Code"
    Write-Host ""

    try {
        & "C:\dev\Autopack\scripts\safe_cleanup_background_cursors.ps1"
    } catch {
        Write-Host "[WARN] Error during cleanup: $_" -ForegroundColor Yellow
    }

    Write-Host ""
    Write-Host "Cleanup complete. Exiting..." -ForegroundColor Green
    exit 0
}

# ============ STEP 1: Detect Empty Slots ============
Write-Host "STEP 1: Detecting empty slots..." -ForegroundColor Yellow
$emptySlots = & "C:\dev\Autopack\scripts\detect_empty_slots.ps1"
$emptySlots = @($emptySlots | Where-Object { $_ -is [int] })

if ($emptySlots.Count -eq 0) {
    Write-Host "[INFO] No empty slots available"
    exit 0
}

Write-Host "[OK] Found $($emptySlots.Count) empty slot(s): $($emptySlots -join ', ')"
Write-Host ""

# ============ STEP 2: Load Wave Prompts and Check State ============
Write-Host "STEP 2: Loading wave prompts..." -ForegroundColor Yellow

$prompts = & "C:\dev\Autopack\scripts\manage_prompt_state.ps1" -Action Load -WaveFile $WaveFile
# Include both [READY] and [UNRESOLVED] phases - UNRESOLVED are CI failures that need fixing
$readyPrompts = @($prompts | Where-Object { $_.Status -eq "READY" -or $_.Status -eq "UNRESOLVED" })

Write-Host "[OK] Loaded $($prompts.Count) total prompts"
$readyCount = @($prompts | Where-Object {$_.Status -eq 'READY'}).Count
$unresolvedCount = @($prompts | Where-Object {$_.Status -eq 'UNRESOLVED'}).Count
$pendingCount = @($prompts | Where-Object {$_.Status -eq 'PENDING'}).Count
$completedCount = @($prompts | Where-Object {$_.Status -eq 'COMPLETED'}).Count
Write-Host "Status: $readyCount READY | $unresolvedCount UNRESOLVED | $pendingCount PENDING | $completedCount COMPLETED"
Write-Host ""

# ============ STEP 3: Wave Boundary Protection ============
Write-Host "STEP 3: Checking wave boundaries..." -ForegroundColor Yellow

if ($readyPrompts.Count -eq 0) {
    Write-Host "[INFO] Wave $WaveNumber is complete!"
    Write-Host "[INFO] All phases are either PENDING or COMPLETED"
    Write-Host "[INFO] Ready for Wave $($WaveNumber + 1)"
    exit 0
}

$emptySlotCount = $emptySlots.Count

if ($readyPrompts.Count -lt $emptySlotCount) {
    Write-Host ""
    Write-Host "[WAVE BOUNDARY] Only $($readyPrompts.Count) [READY] phases remaining in Wave $WaveNumber"
    Write-Host "[INFO] Will fill only $($readyPrompts.Count) slot(s) - NOT crossing to Wave $($WaveNumber + 1)"
    Write-Host "[INFO] Different waves have different dependencies!"
    Write-Host ""

    $promptsToFill = $readyPrompts
    $fillMode = "BOUNDARY"
    $slotsToFill = $emptySlots[0..($readyPrompts.Count - 1)]
} else {
    # Determine fill mode: BULK or SEQUENTIAL
    if ($readyPrompts.Count -le 9) {
        $fillMode = "BULK"
        $promptsToFill = $readyPrompts
        $slotsToFill = $emptySlots
        Write-Host "[BULK FILL] $($readyPrompts.Count) phases <= 9, filling all at once"
    } else {
        $fillMode = "SEQUENTIAL"
        $promptsToFill = $readyPrompts | Select-Object -First $emptySlotCount
        $slotsToFill = $emptySlots | Select-Object -First $emptySlotCount
        Write-Host "[SEQUENTIAL FILL] $($readyPrompts.Count) phases > 9, filling batch of $($promptsToFill.Count)"
    }
}

Write-Host ""

# ============ STEP 4: Fill Slots ============
Write-Host "STEP 4: Filling slots..." -ForegroundColor Yellow
Write-Host ""

if ($DryRun) {
    Write-Host "[DRY-RUN] Would fill:"
    for ($i = 0; $i -lt $promptsToFill.Count; $i++) {
        $prompt = $promptsToFill[$i]
        $slot = $slotsToFill[$i]
        Write-Host "  Slot $slot ← Phase $($prompt.ID)"
    }
    exit 0
}

$successCount = 0
$failCount = 0

for ($i = 0; $i -lt $promptsToFill.Count; $i++) {
    $prompt = $promptsToFill[$i]
    $slot = $slotsToFill[$i]

    Write-Host "[$($i + 1)/$($promptsToFill.Count)] Filling Slot $slot with Phase $($prompt.ID)..."

    try {
        # Step A: Launch new Cursor window for this slot
        # CRITICAL: Always launch a NEW window for each empty slot - never reposition the original window
        Write-Host "  [1/5] Launching Cursor window..."
        $projectPath = $prompt.Path
        Write-Host "    Project: $projectPath"

        $launchOutput = & "C:\dev\Autopack\scripts\launch_cursor_for_slot.ps1" -SlotNumber $slot -ProjectPath $projectPath 2>&1
        # Check if launch was successful by looking for success indicators in output
        $launchSuccess = $launchOutput | Select-String -Pattern "Window positioned successfully|DONE.*launched" -Quiet
        if (-not $launchSuccess) {
            Write-Host "    ⚠️  Launch may have failed" -ForegroundColor Yellow
            Write-Host "    Output: $($launchOutput -join "`n")"
            Write-Host "    Continuing..." -ForegroundColor Yellow
        }
        Write-Host "  [INFO] New window launched and positioned to slot $slot"

        # Step B: Window is already positioned by launch script
        Write-Host "  [2/5] Window positioning..."
        Write-Host "  [OK] Window already positioned by launch script"

        # Step C: Skip model switching - use Cursor's default configured model
        Write-Host "  [3/5] Model configuration..."
        Write-Host "  [INFO] Using Cursor's configured Claude API (or default model)"
        Write-Host "  [INFO] Ensure your Claude API key is set in Cursor Settings"

        # Step D: Paste prompt (with Ctrl+M+O for project folder)
        Write-Host "  [4/5] Pasting prompt..."
        & "C:\dev\Autopack\scripts\paste_prompts_to_cursor_single_window.ps1" -SlotNumber $slot -PhaseId $prompt.ID -WaveFile $WaveFile 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "    ⚠️  Paste script exited with code $LASTEXITCODE" -ForegroundColor Yellow
        }

        Write-Host "  [5/5] Status updated to [PENDING]"
        Write-Host "  ✅ Slot $slot ready"

        $successCount++
    } catch {
        Write-Host "  ❌ Error: $_" -ForegroundColor Red
        $failCount++
    }

    Write-Host ""

    # Add minimal delay between slots (pasting script already waits 3 seconds)
    if ($i -lt ($promptsToFill.Count - 1)) {
        Write-Host "[INFO] Proceeding to next slot..."
        Start-Sleep -Milliseconds 500
    }
}

# ============ STEP 5: Summary ============
Write-Host "============ AUTO-FILL COMPLETE ============" -ForegroundColor Green
Write-Host ""
Write-Host "Fill Mode: $fillMode"
Write-Host "Slots Filled: $successCount / $($promptsToFill.Count)"
Write-Host "Failures: $failCount"
Write-Host ""
Write-Host "Wave Summary:"
# Reload prompts to get updated statuses from file
$promptsUpdated = & "C:\dev\Autopack\scripts\manage_prompt_state.ps1" -Action Load -WaveFile $WaveFile
$readyCount = @($promptsUpdated | Where-Object { $_.Status -eq "READY" }).Count
$unresolvedCount = @($promptsUpdated | Where-Object { $_.Status -eq "UNRESOLVED" }).Count
$pendingCount = @($promptsUpdated | Where-Object { $_.Status -eq "PENDING" }).Count
$completedCount = @($promptsUpdated | Where-Object { $_.Status -eq "COMPLETED" }).Count
Write-Host "  Status: $readyCount READY | $unresolvedCount UNRESOLVED | $pendingCount PENDING | $completedCount COMPLETED"
Write-Host ""

if ($readyCount -eq 0 -and $unresolvedCount -eq 0 -and $pendingCount -gt 0) {
    Write-Host "[INFO] No more [READY] or [UNRESOLVED] phases in Wave $WaveNumber"
    Write-Host "[INFO] Wait for PRs to merge, then use Button 2 again to refill"
} elseif ($readyCount -eq 0 -and $unresolvedCount -eq 0 -and $pendingCount -eq 0) {
    Write-Host "[INFO] Wave $WaveNumber complete! All phases finished."
    Write-Host "[INFO] Use Button 4 to cleanup, then Button 1 for Wave $($WaveNumber + 1)"
} elseif ($unresolvedCount -gt 0) {
    Write-Host "[INFO] $unresolvedCount [UNRESOLVED] phase(s) need CI failure fixes"
    Write-Host "[INFO] Use Button 2 again to fill slots with unresolved phases"
}

Write-Host ""
