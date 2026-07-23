param(
    [Parameter(Mandatory = $true)]
    [string]$BaseUrl,

    [string]$DeviceId = "staging_node_A01",

    [switch]$AllowWebSocket,

    [switch]$AllowAudioTest
)

$ErrorActionPreference = "Stop"

$args = @("tools\post_deploy_smoke.py", "--base-url", $BaseUrl, "--device-id", $DeviceId)
if ($AllowWebSocket) {
    $args += "--allow-websocket"
}
if ($AllowAudioTest) {
    $args += "--allow-audio-test"
}

python @args
