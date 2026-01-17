param(
    [string]$PromptFile,
    [string]$Model = "opus",
    [string]$WorkDir = "C:\dev\Autopack"
)

$prompt = Get-Content -Raw $PromptFile
$prompt | claude -p --dangerously-skip-permissions --model $Model --add-dir $WorkDir
