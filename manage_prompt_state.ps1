<#
.SYNOPSIS
    Manages prompt state phases with status transitions and timestamp tracking.

.DESCRIPTION
    Provides functions for managing phase status in prompt state files.
    Tracks started_at and completed_at timestamps for completion time metrics.

.NOTES
    IMP-TEL-003: Task Completion Time Metrics
#>

$ErrorActionPreference = "Stop"

function Set-PhaseStatus {
    <#
    .SYNOPSIS
        Updates the status of a phase with timestamp tracking.

    .DESCRIPTION
        Sets the status of a phase and automatically records:
        - started_at: When status changes from READY to PENDING
        - completed_at: When status changes to COMPLETED

    .PARAMETER Phase
        The phase object to update.

    .PARAMETER NewStatus
        The new status value (READY, PENDING, IN_PROGRESS, COMPLETED, etc.)

    .EXAMPLE
        $phase = @{ status = "READY"; name = "research" }
        Set-PhaseStatus -Phase $phase -NewStatus "PENDING"
        # Phase now has started_at timestamp

    .EXAMPLE
        $phase = @{ status = "IN_PROGRESS"; name = "implementation" }
        Set-PhaseStatus -Phase $phase -NewStatus "COMPLETED"
        # Phase now has completed_at timestamp
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [PSObject]$Phase,

        [Parameter(Mandatory = $true)]
        [ValidateSet("READY", "PENDING", "IN_PROGRESS", "COMPLETED", "FAILED", "BLOCKED")]
        [string]$NewStatus
    )

    # Add timestamp tracking when status changes
    $now = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

    if ($NewStatus -eq "PENDING" -and $Phase.status -eq "READY") {
        $Phase | Add-Member -NotePropertyName "started_at" -NotePropertyValue $now -Force
    }

    if ($NewStatus -eq "COMPLETED") {
        $Phase | Add-Member -NotePropertyName "completed_at" -NotePropertyValue $now -Force
    }

    $Phase.status = $NewStatus

    return $Phase
}

function Get-PhaseCompletionTime {
    <#
    .SYNOPSIS
        Calculates the completion time in minutes for a phase.

    .DESCRIPTION
        Computes the duration between started_at and completed_at timestamps.

    .PARAMETER Phase
        The phase object with timestamp data.

    .OUTPUTS
        [double] Completion time in minutes, or $null if timestamps unavailable.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [PSObject]$Phase
    )

    if (-not $Phase.started_at -or -not $Phase.completed_at) {
        return $null
    }

    try {
        $startTime = [datetime]::ParseExact($Phase.started_at, "yyyy-MM-dd HH:mm:ss", $null)
        $endTime = [datetime]::ParseExact($Phase.completed_at, "yyyy-MM-dd HH:mm:ss", $null)
        $duration = $endTime - $startTime
        return [math]::Round($duration.TotalMinutes, 2)
    }
    catch {
        Write-Warning "Failed to parse timestamps: $_"
        return $null
    }
}

# Export functions for module use
Export-ModuleMember -Function Set-PhaseStatus, Get-PhaseCompletionTime
