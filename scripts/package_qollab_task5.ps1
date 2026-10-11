$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$stage = Join-Path $root (".qollab-task5-stage-" + [guid]::NewGuid().ToString("N"))
$zip = Join-Path $root "qollab-task5-python.zip"

try {
    New-Item -ItemType Directory -Force -Path (Join-Path $stage "scripts") | Out-Null
    foreach ($relativePath in @("main.py", "requirements.txt", "LICENSE", "ATTRIBUTION.md")) {
        Copy-Item (Join-Path $root $relativePath) -Destination $stage
    }
    foreach ($relativePath in @("scripts\__init__.py", "scripts\qollab_runtime_probe.py")) {
        Copy-Item (Join-Path $root $relativePath) -Destination (Join-Path $stage "scripts")
    }
    Copy-Item (Join-Path $root "src\repackq") -Destination $stage -Recurse

    Get-ChildItem -Path (Join-Path $stage "repackq") -Directory -Recurse -Filter "__pycache__" |
        Remove-Item -Recurse -Force

    Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $zip -Force
    if (-not (Test-Path -LiteralPath $zip -PathType Leaf)) {
        throw "Qollab Python ZIP was not created."
    }
}
finally {
    if (Test-Path -LiteralPath $stage -PathType Container) {
        Remove-Item -LiteralPath $stage -Recurse -Force
    }
}

Write-Output "Created Qollab Python package: $zip"
