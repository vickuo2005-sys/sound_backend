param(
    [string]$OutputPath = "config\phase4_staging_secrets.local.env",
    [string]$InventoryPath = "config\phase4_staging_secrets_inventory.local.json"
)

$ErrorActionPreference = "Stop"

if (Test-Path -LiteralPath $OutputPath) {
    throw "Refusing to overwrite existing secret file: $OutputPath"
}
if (Test-Path -LiteralPath $InventoryPath) {
    throw "Refusing to overwrite existing inventory file: $InventoryPath"
}

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
    DASHBOARD_WRITE_TOKEN_REQUIRED = "true"
    DASHBOARD_ADMIN_TOKEN = New-Token
    DATABASE_URL = ""
    GCS_BUCKET_NAME = ""
    GOOGLE_APPLICATION_CREDENTIALS_JSON = ""
    GOOGLE_MAPS_API_KEY = ""
}

$lines = @(
    "# Local Phase 4 staging secrets generated on $(Get-Date -Format o)",
    "# Do not commit this file. Configure only confirmed staging resources."
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
    }
}
$inventory | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $InventoryPath -Encoding UTF8
Write-Output "Generated staging secrets file: $OutputPath"
Write-Output "Generated masked inventory file: $InventoryPath"
Write-Output "Values were not printed to console."
