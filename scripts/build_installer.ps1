param(
    [string]$Version = "3.4.0",
    [switch]$SkipUiBuild,
    [switch]$SkipExeBuild,
    [switch]$DownloadPrereqs,
    [string]$WebView2StandaloneUrl = "",
    [switch]$NoClean
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

function Remove-PathIfExists {
    param([string]$PathToRemove)
    if (Test-Path $PathToRemove) {
        Remove-Item -Path $PathToRemove -Recurse -Force
    }
}

if ($DownloadPrereqs) {
    $downloadArgs = @{}
    if ($WebView2StandaloneUrl) {
        $downloadArgs.WebView2StandaloneUrl = $WebView2StandaloneUrl
    }
    & (Join-Path $repoRoot "scripts\download_installer_prereqs.ps1") @downloadArgs
}

if (-not $SkipUiBuild) {
    Write-Host "[1/4] Build UI" -ForegroundColor Cyan
    Push-Location (Join-Path $repoRoot "ui")
    npm ci
    if ($LASTEXITCODE -ne 0) { throw "Falha em npm ci" }
    npm run build
    if ($LASTEXITCODE -ne 0) { throw "Falha em npm run build" }
    Pop-Location
}

$appVersionFile = Join-Path $repoRoot "app_version.py"
$appVersionFileExisted = Test-Path $appVersionFile
$originalAppVersionContent = $null
if ($appVersionFileExisted) {
    $originalAppVersionContent = Get-Content -Path $appVersionFile -Raw
}

Set-Content -Path $appVersionFile -Value ("APP_VERSION = `"{0}`"" -f $Version)

try {
    if (-not $SkipExeBuild) {
        Write-Host "[2/4] Build EXE" -ForegroundColor Cyan
        if (-not $NoClean) {
            Write-Host "      Limpar artefactos antigos" -ForegroundColor DarkCyan
            Remove-PathIfExists (Join-Path $repoRoot "build")
            Remove-PathIfExists (Join-Path $repoRoot "dist\WootFlow")
            Remove-PathIfExists (Join-Path $repoRoot ".artifacts\pyinstaller\work")
        }

        $pyiWorkDir = Join-Path $repoRoot ".artifacts\pyinstaller\work"
        New-Item -ItemType Directory -Path $pyiWorkDir -Force | Out-Null

        & ".\.venv\Scripts\python.exe" -m pip install pyinstaller
        if ($LASTEXITCODE -ne 0) { throw "Falha ao instalar PyInstaller" }
        & ".\.venv\Scripts\python.exe" -m PyInstaller WootFlow.spec --clean -y --workpath $pyiWorkDir --distpath "dist"
        if ($LASTEXITCODE -ne 0) { throw "Falha ao gerar EXE" }
    }

    Write-Host "[3/4] Localizar Inno Setup Compiler" -ForegroundColor Cyan
    $iscc = (Get-Command iscc.exe -ErrorAction SilentlyContinue).Source
    if (-not $iscc) {
        $candidate = Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"
        if (Test-Path $candidate) {
            $iscc = $candidate
        }
    }
    if (-not $iscc) {
        throw "ISCC.exe nao encontrado. Instala Inno Setup 6 ou adiciona iscc.exe ao PATH."
    }

    $distDir = Join-Path $repoRoot "dist\WootFlow"
    if (-not (Test-Path (Join-Path $distDir "WootFlow.exe"))) {
        throw "dist\WootFlow\WootFlow.exe nao encontrado."
    }

    Write-Host "[4/4] Compilar instalador" -ForegroundColor Cyan
    & $iscc "/DAppVersion=$Version" "/DRepoDir=$repoRoot" "/DSourceDir=$distDir" (Join-Path $repoRoot "installer\WootFlowInstaller.iss")
    if ($LASTEXITCODE -ne 0) { throw "Falha ao compilar instalador Inno Setup" }

    Write-Host "Instalador gerado em installer\output" -ForegroundColor Green
    Write-Host "Portable gerado em dist\WootFlow" -ForegroundColor Green
}
finally {
    if ($appVersionFileExisted) {
        Set-Content -Path $appVersionFile -Value $originalAppVersionContent -NoNewline
    }
}
