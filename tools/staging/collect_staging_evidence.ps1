param(
    [string]$OutputDirectory = "artifacts\staging_evidence"
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$statusPath = Join-Path $OutputDirectory "git_status_$timestamp.txt"
$diffPath = Join-Path $OutputDirectory "git_diff_stat_$timestamp.txt"

git status --short | Set-Content -LiteralPath $statusPath -Encoding UTF8
git diff --stat | Set-Content -LiteralPath $diffPath -Encoding UTF8

Write-Output "Collected staging evidence:"
Write-Output $statusPath
Write-Output $diffPath
