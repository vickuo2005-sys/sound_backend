param(
    [string]$ExamplePath = ".env.staging.example",
    [string]$OutputPath = ".env.staging.local"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $ExamplePath)) {
    throw "Example env file not found: $ExamplePath"
}
if (Test-Path -LiteralPath $OutputPath) {
    throw "Refusing to overwrite existing local env file: $OutputPath"
}

Copy-Item -LiteralPath $ExamplePath -Destination $OutputPath
Write-Output "Created local staging env template: $OutputPath"
Write-Output "Fill it manually with staging-only values. Do not commit it."
