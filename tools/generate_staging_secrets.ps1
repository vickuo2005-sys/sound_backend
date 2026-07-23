param(
    [string]$OutputPath = "config\staging_secrets.local.env",
    [string]$InventoryPath = "config\staging_secrets_inventory.local.json"
)

$ErrorActionPreference = "Stop"

function New-Token {
    param([int]$Bytes = 32)
    $data = New-Object byte[] $Bytes
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $rng.GetBytes($data)
    } finally {
        $rng.Dispose()
    }
    return [Convert]::ToBase64String($data).TrimEnd("=").Replace("+", "-").Replace("/", "_")
}

$outputDirectory = Split-Path -Parent $OutputPath
if ($outputDirectory -and -not (Test-Path $outputDirectory)) {
    New-Item -ItemType Directory -Path $outputDirectory | Out-Null
}
$inventoryDirectory = Split-Path -Parent $InventoryPath
if ($inventoryDirectory -and -not (Test-Path $inventoryDirectory)) {
    New-Item -ItemType Directory -Path $inventoryDirectory | Out-Null
}

$values = @{
    APP_ENV = "staging"
    DEVICE_TOKEN = New-Token
    UPLOAD_TOKEN = New-Token
    STREAM_TOKEN_SECRET = New-Token
    DASHBOARD_AUTH_SECRET = New-Token
    DATABASE_URL = ""
    SUPABASE_URL = ""
    SUPABASE_KEY = ""
    GCS_BUCKET_NAME = ""
    GCP_PROJECT_ID = ""
    GOOGLE_APPLICATION_CREDENTIALS_JSON = ""
}

$lines = @(
    "# Local staging secrets generated on $(Get-Date -Format o)",
    "# Do not commit this file. Copy values into Render staging manually."
)
foreach ($key in $values.Keys | Sort-Object) {
    $lines += "$key=$($values[$key])"
}

$lines | Set-Content -LiteralPath $OutputPath -Encoding UTF8
$inventory = foreach ($key in $values.Keys | Sort-Object) {
    $value = [string]$values[$key]
    [PSCustomObject]@{
        variable = $key
        configured = -not [string]::IsNullOrWhiteSpace($value)
        length = $value.Length
        created_at = (Get-Date -Format o)
        suffix = if ($value.Length -ge 4) { $value.Substring($value.Length - 4) } else { "" }
    }
}
$inventory | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $InventoryPath -Encoding UTF8
Write-Output "Generated staging secrets file: $OutputPath"
Write-Output "Generated masked inventory file: $InventoryPath"
Write-Output "Values were not printed to console."
