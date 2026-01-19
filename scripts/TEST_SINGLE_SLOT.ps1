# Test the updated prompt pasting to Claude Chat
# This will launch ONE Cursor instance and paste a test prompt to verify Claude Chat is working

Write-Host ""
Write-Host "============ SINGLE SLOT TEST ============" -ForegroundColor Cyan
Write-Host ""

# Find the wave file
$backupDir = "C:\Users\hshk9\OneDrive\Backup\Desktop"
$waveFiles = @(Get-ChildItem -Path $backupDir -Filter "Wave*_All_Phases.md" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending)

if ($waveFiles.Count -eq 0) {
    Write-Host "[ERROR] No Wave file found" -ForegroundColor Red
    exit 1
}

$WaveFile = $waveFiles[0].FullName
Write-Host "[INFO] Using wave file: $($waveFiles[0].Name)"
Write-Host ""

# Test parameters
$SlotNumber = 1
$PhaseId = "safety006"  # This is the first READY phase in Wave1

Write-Host "[TEST] Will test pasting prompt to slot $SlotNumber (Phase $PhaseId)"
Write-Host ""

# Step 1: Launch Cursor for slot 1
Write-Host "[STEP 1/2] Launching Cursor window..."
& "C:\dev\Autopack\scripts\launch_cursor_for_slot.ps1" -SlotNumber $SlotNumber -ProjectPath "C:\dev\Autopack" 2>&1 | Out-Null

Write-Host "[OK] Cursor launched for slot $SlotNumber"
Write-Host ""
Write-Host "[WAITING] Giving Cursor 5 seconds to fully load..."
Start-Sleep -Seconds 5

# Step 2: Paste the prompt
Write-Host "[STEP 2/2] Pasting prompt to Claude Chat..."
& "C:\dev\Autopack\scripts\paste_prompts_to_cursor_single_window.ps1" -SlotNumber $SlotNumber -PhaseId $PhaseId -WaveFile $WaveFile 2>&1

Write-Host ""
Write-Host "============ TEST COMPLETE ============" -ForegroundColor Cyan
Write-Host ""
Write-Host "WHAT TO LOOK FOR:"
Write-Host "1. Claude Chat should open in the Cursor window (Ctrl+K)"
Write-Host "2. The prompt should paste into the chat input"
Write-Host "3. Claude should start responding"
Write-Host ""
Write-Host "If it works, you can run the full wave with Button 2"
Write-Host ""
