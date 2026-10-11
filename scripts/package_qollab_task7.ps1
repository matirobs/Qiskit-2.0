$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$stage = Join-Path $root (".qollab-task7-stage-" + [guid]::NewGuid().ToString("N"))
$zip = Join-Path $root "qollab-task7-app.zip"

try {
    New-Item -ItemType Directory -Force -Path (Join-Path $stage "scripts") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $stage "data\fixtures") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $stage "docs") | Out-Null
    $builder = Join-Path $root "scripts\build_qollab_html.py"
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 $builder --output-dir $stage
    } else {
        & python $builder --output-dir $stage
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Could not build the self-contained Qollab HTML/JS assets."
    }
    foreach ($relativePath in @("main.py", "styles.css", "run_repackq_web.py", "Launch RePack-Q.bat", "README.md", "requirements.txt", "LICENSE", "ATTRIBUTION.md")) {
        Copy-Item (Join-Path $root $relativePath) -Destination $stage
    }
    foreach ($relativePath in @("scripts\__init__.py", "scripts\qollab_runtime_probe.py", "scripts\build_qollab_html.py")) {
        Copy-Item (Join-Path $root $relativePath) -Destination (Join-Path $stage "scripts")
    }
    Copy-Item (Join-Path $root "src\repackq") -Destination $stage -Recurse
    Copy-Item (Join-Path $root "data\fixtures\synthetic_demo.json") -Destination (Join-Path $stage "data\fixtures")
    Copy-Item (Join-Path $root "web") -Destination $stage -Recurse
    foreach ($relativePath in @("docs\RESULTS.md", "docs\QOLLAB_SPIKE.md")) {
        Copy-Item (Join-Path $root $relativePath) -Destination (Join-Path $stage "docs")
    }

    foreach ($requiredPath in @(
        "index.html",
        "main.js",
        "styles.css"
    )) {
        if (-not (Test-Path -LiteralPath (Join-Path $stage $requiredPath) -PathType Leaf)) {
            throw "Qollab HTML/JS package is missing required file: $requiredPath"
        }
    }

    Get-ChildItem -Path (Join-Path $stage "repackq") -Directory -Recurse -Filter "__pycache__" |
        Remove-Item -Recurse -Force

    Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $zip -Force
    if (-not (Test-Path -LiteralPath $zip -PathType Leaf)) {
        throw "Qollab Task 7 application ZIP was not created."
    }
}
finally {
    if (Test-Path -LiteralPath $stage -PathType Container) {
        Remove-Item -LiteralPath $stage -Recurse -Force
    }
}

Write-Output "Created Qollab Task 7 application: $zip"
