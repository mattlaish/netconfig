param(
    [string]$OutputPath,
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$version = "2.0.0"
$release = "16"
$projectRoot = Split-Path -Parent $PSScriptRoot

if (-not $OutputPath) {
    $OutputPath = Join-Path $projectRoot "netconfig-$version-$release-rpm-build-source.zip"
} elseif (-not [System.IO.Path]::IsPathRooted($OutputPath)) {
    $OutputPath = Join-Path $projectRoot $OutputPath
}
$OutputPath = [System.IO.Path]::GetFullPath($OutputPath)

if (Test-Path -LiteralPath $OutputPath) {
    if (-not $Force) {
        throw "Output already exists: $OutputPath (use -Force to replace it)"
    }
    Remove-Item -LiteralPath $OutputPath -Force
}

$stage = Join-Path ([System.IO.Path]::GetTempPath()) (
    "netconfig-rpm-transfer-" + [System.Guid]::NewGuid().ToString("N"))
$bundleName = "netconfig-$version-$release-build"
$bundleRoot = Join-Path $stage $bundleName

try {
    New-Item -ItemType Directory -Path $bundleRoot | Out-Null

    foreach ($directory in @("opt", "usr", "etc", "packaging")) {
        $source = Join-Path $projectRoot $directory
        if (-not (Test-Path -LiteralPath $source -PathType Container)) {
            throw "Required directory is missing: $source"
        }
        Copy-Item -LiteralPath $source -Destination $bundleRoot -Recurse
    }

    foreach ($file in @(
        ".gitignore",
        "AGENTS.md",
        "AI_HANDOFF.md",
        "CLAUDE.md",
        "DEV_BASELINE.md",
        "patch.md"
    )) {
        $source = Join-Path $projectRoot $file
        if (Test-Path -LiteralPath $source -PathType Leaf) {
            Copy-Item -LiteralPath $source -Destination $bundleRoot
        }
    }

    Get-ChildItem -LiteralPath $bundleRoot -Directory -Recurse -Force |
        Where-Object Name -eq "__pycache__" |
        Remove-Item -Recurse -Force
    Get-ChildItem -LiteralPath $bundleRoot -File -Recurse -Force |
        Where-Object { $_.Extension -in @(".pyc", ".pyo", ".rpm", ".srpm") } |
        Remove-Item -Force

    Compress-Archive -LiteralPath $bundleRoot -DestinationPath $OutputPath -CompressionLevel Optimal
    Write-Output $OutputPath
} finally {
    if (Test-Path -LiteralPath $stage) {
        Remove-Item -LiteralPath $stage -Recurse -Force
    }
}
