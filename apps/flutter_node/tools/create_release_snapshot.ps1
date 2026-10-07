param(
    [string]$SourceRoot = "C:\Users\vicku\sound_detector_clean",
    [string]$OutputRoot = "C:\release_snapshots\sound_detector_clean"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $SourceRoot)) {
    throw "SourceRoot not found: $SourceRoot"
}

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$snapshotDir = Join-Path $OutputRoot $timestamp
New-Item -ItemType Directory -Force -Path $snapshotDir | Out-Null

$excludedDirectories = @(
    ".git",
    ".dart_tool",
    ".gradle",
    ".idea",
    ".vscode",
    "build",
    "outputs"
)

$excludedFiles = @(
    ".env",
    "key.properties",
    "google-services.json",
    "local_events.json"
)

$excludedExtensions = @(
    ".apk",
    ".jks",
    ".keystore",
    ".pem",
    ".key",
    ".wav",
    ".mp3",
    ".m4a"
)

function Should-ExcludePath {
    param([string]$Path)
    $relative = Resolve-Path -LiteralPath $Path -Relative
    foreach ($dir in $excludedDirectories) {
        if ($relative -match "(^|[\\/])$([regex]::Escape($dir))([\\/]|$)") {
            return $true
        }
    }
    $name = Split-Path -Leaf $Path
    if ($excludedFiles -contains $name) {
        return $true
    }
    $extension = [System.IO.Path]::GetExtension($Path)
    if ($excludedExtensions -contains $extension) {
        return $true
    }
    return $false
}

$files = Get-ChildItem -LiteralPath $SourceRoot -Recurse -File -Force |
    Where-Object { -not (Should-ExcludePath $_.FullName) }

$manifest = @()
foreach ($file in $files) {
    $sourcePrefix = (Resolve-Path -LiteralPath $SourceRoot).Path.TrimEnd("\") + "\"
    $relative = $file.FullName.Substring($sourcePrefix.Length)
    $destination = Join-Path $snapshotDir $relative
    $destinationParent = Split-Path -Parent $destination
    New-Item -ItemType Directory -Force -Path $destinationParent | Out-Null
    Copy-Item -LiteralPath $file.FullName -Destination $destination -Force
    $hash = Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256
    $manifest += [pscustomobject]@{
        path = $relative
        bytes = $file.Length
        sha256 = $hash.Hash.ToLowerInvariant()
    }
}

$manifest |
    Sort-Object path |
    ConvertTo-Json -Depth 4 |
    Set-Content -LiteralPath (Join-Path $snapshotDir "snapshot_manifest.json") -Encoding UTF8

$manifest |
    Sort-Object path |
    ForEach-Object { "$($_.sha256)  $($_.bytes)  $($_.path)" } |
    Set-Content -LiteralPath (Join-Path $snapshotDir "snapshot_manifest.txt") -Encoding UTF8

Write-Output "Snapshot created: $snapshotDir"
Write-Output "Files copied: $($manifest.Count)"
