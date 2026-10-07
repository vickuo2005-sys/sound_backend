param(
    [Parameter(Mandatory = $true)]
    [string]$ConfigPath,

    [Parameter(Mandatory = $true)]
    [ValidateSet("development", "staging", "production")]
    [string]$Environment,

    [string]$ApprovedStagingHost = ""
)

$ErrorActionPreference = "Stop"

function Fail($Message) {
    Write-Error $Message
    exit 1
}

if (-not (Test-Path -LiteralPath $ConfigPath)) {
    Fail "Config file not found: $ConfigPath"
}

$raw = Get-Content -LiteralPath $ConfigPath -Raw
$config = $raw | ConvertFrom-Json

$appEnv = [string]$config.APP_ENV
$backendBaseUrl = [string]$config.BACKEND_BASE_URL
$uploadToken = [string]$config.UPLOAD_TOKEN
$deviceToken = [string]$config.DEVICE_TOKEN

if ($appEnv -ne $Environment) {
    Fail "APP_ENV must be '$Environment'."
}
if ([string]::IsNullOrWhiteSpace($backendBaseUrl)) {
    Fail "BACKEND_BASE_URL is required."
}
if ([string]::IsNullOrWhiteSpace($uploadToken)) {
    Fail "UPLOAD_TOKEN is required."
}
if ([string]::IsNullOrWhiteSpace($deviceToken)) {
    Fail "DEVICE_TOKEN is required."
}
if (($Environment -ne "development") -and $uploadToken -eq ("test" + "-token-123")) {
    Fail "UPLOAD_TOKEN cannot use the demo token."
}
if (($Environment -ne "development") -and $deviceToken -eq ("test" + "-token-123")) {
    Fail "DEVICE_TOKEN cannot use the demo token."
}

$uri = $null
if (-not [System.Uri]::TryCreate($backendBaseUrl, [System.UriKind]::Absolute, [ref]$uri)) {
    Fail "BACKEND_BASE_URL must be an absolute URL."
}

if ($Environment -eq "production") {
    if ($uri.Scheme -ne "https") {
        Fail "Production BACKEND_BASE_URL must use https."
    }
    if ($uri.Host -in @("localhost", "127.0.0.1", "0.0.0.0", "10.0.2.2")) {
        Fail "Production BACKEND_BASE_URL cannot be localhost."
    }
    if ($uri.Host -like "*staging*") {
        Fail "Production BACKEND_BASE_URL cannot point to staging."
    }
}

if ($Environment -eq "staging") {
    if ($uri.Scheme -ne "https") {
        Fail "Staging BACKEND_BASE_URL must use https."
    }
    if ([string]::IsNullOrWhiteSpace($ApprovedStagingHost)) {
        Fail "ApprovedStagingHost is required for staging validation."
    }
    if ($ApprovedStagingHost.Contains("://") -or $ApprovedStagingHost.Contains("/")) {
        Fail "ApprovedStagingHost must be a hostname only."
    }
    if ($uri.Host -ne $ApprovedStagingHost) {
        Fail "Staging BACKEND_BASE_URL hostname is not approved."
    }
    if ($uri.Host -eq "sound-backend.onrender.com") {
        Fail "Staging BACKEND_BASE_URL cannot point to the production host."
    }
}

if ($Environment -eq "development") {
    if (($uri.Host -notin @("localhost", "127.0.0.1", "0.0.0.0", "10.0.2.2")) -and $uri.Scheme -ne "https") {
        Fail "Development BACKEND_BASE_URL must use https for remote hosts."
    }
}

Write-Output "Config validation passed: environment=$Environment backend_host=$($uri.Host) upload_token_configured=true device_token_configured=true"
