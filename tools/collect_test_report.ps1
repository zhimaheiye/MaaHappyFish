[CmdletBinding()]
param(
    [string]$PackageRoot = "",
    [ValidateRange(1, 30)]
    [int]$MaxLogFiles = 3,
    [string]$OutputDirectory = ""
)

$ErrorActionPreference = "Stop"

if (-not $PackageRoot) {
    $repositoryRoot = Split-Path -Parent $PSScriptRoot
    $candidates = @(
        $PSScriptRoot,
        $repositoryRoot,
        (Join-Path $repositoryRoot "client_avalonia")
    )
    $PackageRoot = $candidates |
        Where-Object { Test-Path -LiteralPath (Join-Path $_ "logs") -PathType Container } |
        Select-Object -First 1
}

if (-not $PackageRoot) {
    throw "No MaaHappyFish logs directory was found. Run MaaHappyFish at least once, then try again."
}

$PackageRoot = [System.IO.Path]::GetFullPath($PackageRoot)
$logDirectory = Join-Path $PackageRoot "logs"
if (-not (Test-Path -LiteralPath $logDirectory -PathType Container)) {
    throw "Logs directory not found: $logDirectory"
}

$logFiles = @(Get-ChildItem -LiteralPath $logDirectory -Filter "*.log" -File |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First $MaxLogFiles)
if ($logFiles.Count -eq 0) {
    throw "No .log files were found in: $logDirectory"
}

$debugDirectory = Join-Path $PackageRoot "debug"
$frameworkLogFiles = @()
$errorImageFiles = @()
if (Test-Path -LiteralPath $debugDirectory -PathType Container) {
    $frameworkLogFiles = @(Get-ChildItem -LiteralPath $debugDirectory -Filter "maafw*.log" -File |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First $MaxLogFiles)

    $errorImageDirectory = Join-Path $debugDirectory "on_error"
    if (Test-Path -LiteralPath $errorImageDirectory -PathType Container) {
        $errorImageFiles = @(Get-ChildItem -LiteralPath $errorImageDirectory -Filter "*.png" -File |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 10)
    }
}

$collectedFiles = @($logFiles) + @($frameworkLogFiles) + @($errorImageFiles)

if (-not $OutputDirectory) {
    $desktop = [Environment]::GetFolderPath("Desktop")
    $OutputDirectory = Join-Path $desktop "MaaHappyFish-TestReports"
}
$OutputDirectory = [System.IO.Path]::GetFullPath($OutputDirectory)
[System.IO.Directory]::CreateDirectory($OutputDirectory) | Out-Null

$version = "unknown"
$interfacePath = Join-Path $PackageRoot "interface.json"
if (Test-Path -LiteralPath $interfacePath -PathType Leaf) {
    try {
        $interface = Get-Content -LiteralPath $interfacePath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($interface.version) {
            $version = [string]$interface.version
        }
    }
    catch {
        $version = "unreadable interface.json"
    }
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$zipPath = Join-Path $OutputDirectory "MaaHappyFish-TestReport-$timestamp.zip"
$reportPath = Join-Path ([System.IO.Path]::GetTempPath()) "MaaHappyFish-report-$([guid]::NewGuid().ToString('N')).txt"
$utf8WithBom = New-Object System.Text.UTF8Encoding($true)

$logSummary = $collectedFiles | ForEach-Object {
    "- {0} | {1:N2} MB | modified {2:yyyy-MM-dd HH:mm:ss}" -f $_.FullName.Substring($PackageRoot.Length).TrimStart('\'), ($_.Length / 1MB), $_.LastWriteTime
}

$reportLines = @(
    "MaaHappyFish test report",
    "",
    "[Please fill in before sending]",
    "Approximate failure time:",
    "Run duration:",
    "Selected tasks:",
    "Observed behavior:",
    "Expected behavior:",
    "MuMu version / resolution / DPI:",
    "Other notes:",
    "",
    "[Collected automatically]",
    "Collected at: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')",
    "MaaHappyFish version: $version",
    "OS: $([System.Runtime.InteropServices.RuntimeInformation]::OSDescription)",
    "OS architecture: $([System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture)",
    "PowerShell: $($PSVersionTable.PSVersion.ToString())",
    "Included logs:"
) + $logSummary

try {
    [System.IO.File]::WriteAllLines($reportPath, $reportLines, $utf8WithBom)
    $archiveInputs = @($reportPath) + @($collectedFiles.FullName)
    Compress-Archive -LiteralPath $archiveInputs -DestinationPath $zipPath -CompressionLevel Optimal -Force
}
finally {
    if (Test-Path -LiteralPath $reportPath -PathType Leaf) {
        Remove-Item -LiteralPath $reportPath -Force
    }
}

$sourceBytes = ($collectedFiles | Measure-Object Length -Sum).Sum
$zipBytes = (Get-Item -LiteralPath $zipPath).Length
Write-Host "Test report created successfully."
Write-Host "Included $($collectedFiles.Count) log/screenshot file(s): $([math]::Round($sourceBytes / 1MB, 2)) MB before compression."
Write-Host "ZIP size: $([math]::Round($zipBytes / 1MB, 2)) MB"
Write-Host "Saved to: $zipPath"
