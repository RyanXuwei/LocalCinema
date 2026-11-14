param(
    [string]$Python = "python",
    [string]$InnoCompiler = ""
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $repoRoot
try {
    $appVersion = (& $Python -c 'from version import APP_VERSION; print(APP_VERSION)').Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Cannot read version.py' }
    $buildRoot = Join-Path $repoRoot 'build/windows'
    New-Item -ItemType Directory -Force $buildRoot | Out-Null
    $buildArgs = @('-m','PyInstaller','--noconfirm','--windowed','--onedir','--name','LocalCinema',
        '--distpath',(Join-Path $buildRoot 'dist'),'--workpath',(Join-Path $buildRoot 'work'),
        '--specpath',$buildRoot,'--icon',(Join-Path $repoRoot 'assets/localcinema.ico'),
        '--add-data',((Join-Path $repoRoot 'assets')+';assets'),
        '--add-data',((Join-Path $repoRoot 'index.html')+';.'),'--collect-all','imageio_ffmpeg',
        '--hidden-import','pystray._win32','--exclude-module','PyQt5','--exclude-module','PyQt6',
        '--exclude-module','matplotlib','--exclude-module','numpy',(Join-Path $repoRoot 'LocalCinema.pyw'))
    & $Python @buildArgs
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed' }
    $reportPath = Join-Path $buildRoot 'self-test.json'
    $testProcess = Start-Process -FilePath (Join-Path $buildRoot 'dist/LocalCinema/LocalCinema.exe') -ArgumentList @('--self-test',('"'+$reportPath+'"')) -WindowStyle Hidden -Wait -PassThru
    if ($testProcess.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $reportPath)) { throw 'Frozen app self-test failed' }
    $report = Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json
    if (-not $report.ok) { throw 'Frozen app self-test reported failure' }
    if (-not $InnoCompiler) {
        $foundCompiler = Get-Command ISCC.exe -ErrorAction SilentlyContinue
        if ($foundCompiler) { $InnoCompiler = $foundCompiler.Source }
    }
    if (-not $InnoCompiler) { throw 'Pass -InnoCompiler with the path to the official Inno Setup ISCC.exe.' }
    & $InnoCompiler (('/DAppVersion=')+$appVersion) (Join-Path $PSScriptRoot 'setup.iss')
    if ($LASTEXITCODE -ne 0) { throw 'Inno Setup failed' }
    $installer = Join-Path $repoRoot ('dist/LocalCinema_Setup_v'+$appVersion+'_x64.exe')
    $digest = (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash.ToLowerInvariant()
    ($digest+'  '+[IO.Path]::GetFileName($installer)) | Set-Content -LiteralPath ($installer+'.sha256') -Encoding utf8
    Write-Host ('Built: '+$installer)
} finally { Pop-Location }
