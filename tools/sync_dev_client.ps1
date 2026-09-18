$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$clientDir = Join-Path $repoRoot "client_avalonia"

$sourceInterface = Join-Path $repoRoot "assets\interface.json"
$targetInterface = Join-Path $clientDir "interface.json"

$sourceIcon = Join-Path $repoRoot "happyfish.ico"
$targetAssets = Join-Path $clientDir "Assets"
$targetIcon = Join-Path $targetAssets "logo.ico"

if (-not (Test-Path $clientDir)) {
    throw "client_avalonia not found: $clientDir"
}

Copy-Item $sourceInterface $targetInterface -Force

New-Item -ItemType Directory -Force $targetAssets | Out-Null
Copy-Item $sourceIcon $targetIcon -Force

# Check resource junction
$resourceDir = Join-Path $clientDir "resource"
if (Test-Path $resourceDir) {
    $item = Get-Item $resourceDir -Force
    if ($item.LinkType -eq 'Junction') {
        Write-Host "[OK] resource is a junction. Target: $($item.Target)"
    } else {
        Write-Warning "resource is not a junction"
    }
} else {
    Write-Warning "resource directory not found"
}

# Check agent junction
$agentDir = Join-Path $clientDir "agent"
if (Test-Path $agentDir) {
    $item = Get-Item $agentDir -Force
    if ($item.LinkType -eq 'Junction') {
        Write-Host "[OK] agent is a junction. Target: $($item.Target)"
    } else {
        Write-Warning "agent is not a junction"
    }
} else {
    Write-Warning "agent directory not found"
}

$hash1 = (Get-FileHash $sourceInterface).Hash
$hash2 = (Get-FileHash $targetInterface).Hash
if ($hash1 -eq $hash2) {
    Write-Host "[OK] interface.json synced"
} else {
    Write-Error "[FAIL] interface.json hash mismatch"
}

$hash3 = (Get-FileHash $sourceIcon).Hash
$hash4 = (Get-FileHash $targetIcon).Hash
if ($hash3 -eq $hash4) {
    Write-Host "[OK] logo.ico synced"
} else {
    Write-Error "[FAIL] logo.ico hash mismatch"
}
