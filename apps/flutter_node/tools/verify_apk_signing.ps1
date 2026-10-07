param(
    [Parameter(Mandatory = $true)]
    [string]$ApkPath,

    [switch]$Production
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $ApkPath)) {
    throw "APK not found: $ApkPath"
}

function Find-ApkSigner {
    $candidates = @()
    $sdkRoots = @()
    if ($env:ANDROID_HOME) { $sdkRoots += $env:ANDROID_HOME }
    if ($env:ANDROID_SDK_ROOT) { $sdkRoots += $env:ANDROID_SDK_ROOT }
    $localProperties = "android\local.properties"
    if (Test-Path -LiteralPath $localProperties) {
        Get-Content -LiteralPath $localProperties | ForEach-Object {
            if ($_ -match "^sdk\.dir=(.*)$") {
                $sdkRoots += ($matches[1] -replace "\\\\", "\")
            }
        }
    }
    $sdkRoots += Join-Path $env:LOCALAPPDATA "Android\sdk"

    foreach ($sdkRoot in $sdkRoots | Where-Object { $_ } | Select-Object -Unique) {
        $buildTools = Join-Path $sdkRoot "build-tools"
        if (Test-Path -LiteralPath $buildTools) {
            $candidates += Get-ChildItem -Path $buildTools -Filter apksigner.bat -Recurse -ErrorAction SilentlyContinue
            $candidates += Get-ChildItem -Path $buildTools -Filter apksigner -Recurse -ErrorAction SilentlyContinue
        }
    }
    $cmd = Get-Command apksigner.bat -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }
    return $candidates | Sort-Object FullName -Descending | Select-Object -First 1 -ExpandProperty FullName
}

$apksigner = Find-ApkSigner
if (-not $apksigner) {
    throw "apksigner not found. Install Android SDK build-tools or set ANDROID_HOME."
}

$output = & $apksigner verify --verbose --print-certs $ApkPath 2>&1
$text = $output -join "`n"
$debugSigned = $text -match "Android Debug" -or $text -match "debug"
$shaMatch = [regex]::Match($text, "Signer #1 certificate SHA-256 digest:\s*(?<sha>[0-9a-fA-F:]+)")
$sha = if ($shaMatch.Success) { $shaMatch.Groups["sha"].Value } else { "unknown" }

Write-Output "APK=$ApkPath"
Write-Output "SIGNED=$($text -match 'Verified')"
Write-Output "DEBUG_SIGNED=$debugSigned"
Write-Output "CERTIFICATE_SHA256=$sha"

if ($Production -and $debugSigned) {
    throw "PRODUCTION BLOCKER: APK is debug-signed."
}

if ($debugSigned) {
    Write-Output "SIGNING_CLASSIFICATION=INTERNAL TEST ONLY"
} else {
    Write-Output "SIGNING_CLASSIFICATION=RELEASE SIGNED"
}
