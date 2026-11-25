param(
    [string]$EnvPath = ".env.staging.local"
)

$ErrorActionPreference = "Stop"

function Fail($Message) {
    Write-Error $Message
    exit 1
}

if (-not (Test-Path -LiteralPath $EnvPath)) {
    Fail "Env file not found: $EnvPath"
}

$vars = @{}
Get-Content -LiteralPath $EnvPath | ForEach-Object {
    if ($_ -match "^\s*([^#][^=]+?)\s*=\s*(.*)$") {
        $vars[$matches[1].Trim()] = $matches[2].Trim()
    }
}

$required = @(
    "APP_ENV",
    "DATABASE_URL",
    "GCS_BUCKET_NAME",
    "GOOGLE_APPLICATION_CREDENTIALS_JSON",
    "GOOGLE_MAPS_API_KEY",
    "UPLOAD_TOKEN"
)

foreach ($key in $required) {
    if (-not $vars.ContainsKey($key) -or [string]::IsNullOrWhiteSpace($vars[$key])) {
        Fail "Missing required staging variable: $key"
    }
}

if ($vars["APP_ENV"] -notin @("development", "integration", "staging")) {
    Fail "APP_ENV must be development, integration, or staging."
}
if ($vars["UPLOAD_TOKEN"] -eq ("test" + "-token-123")) {
    Fail "UPLOAD_TOKEN cannot use the demo token."
}
if ($vars["LIVE_AUDIO_ENABLED"] -eq "true") {
    Write-Warning "LIVE_AUDIO_ENABLED is true. Initial integration deployment should keep this false."
}

Write-Output "Integration env validation passed. Secrets were not printed."
