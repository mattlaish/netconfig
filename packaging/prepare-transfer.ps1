param(
    [string]$OutputPath,
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$version = "2.0.0"
$projectRoot = Split-Path -Parent $PSScriptRoot
$specPath = Join-Path $PSScriptRoot "netconfig.spec"
$releaseMatch = Select-String -LiteralPath $specPath -Pattern '^Release:\s+([0-9]+)' | Select-Object -First 1
if (-not $releaseMatch) {
    throw "Unable to determine RPM Release from $specPath"
}
$release = $releaseMatch.Matches[0].Groups[1].Value

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

    foreach ($directory in @("opt", "usr", "etc", "packaging", "tests", ".github")) {
        $source = Join-Path $projectRoot $directory
        if (-not (Test-Path -LiteralPath $source -PathType Container)) {
            throw "Required directory is missing: $source"
        }
        Copy-Item -LiteralPath $source -Destination $bundleRoot -Recurse
    }

    foreach ($file in @(
        ".gitattributes",
        ".gitignore",
        "README.md",
        "API.md",
        "TESTING.md",
        "TESTING_RESULT_2026-09-12.md",
        "AGENTS.md",
        "AI_HANDOFF.md",
        "CLAUDE.md",
        "DEV_BASELINE.md",
        "DEVELOPMENT.md",
        "ROADMAP.md",
        "SECURITY.md",
        "HANDOVER_2026-09-07.md",
        "TESTING_RESULT_2026-09-07.md",
        "HANDOVER_PROMPT.md",
        "patch.md",
        "pyproject.toml"
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
