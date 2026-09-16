# 배포 패키지 빌드: dist\handwrite-scanner\ 폴더 + zip
# 실행: powershell -ExecutionPolicy Bypass -File build.ps1
param([string]$InnoCompiler = $env:INNO_COMPILER)
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
if (-not $InnoCompiler) {
    $InnoCompiler = (Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source
}
if (-not $InnoCompiler) { throw "Inno Setup 6을 설치하고 -InnoCompiler 옵션으로 ISCC.exe 경로를 지정하세요." }
& "$PSScriptRoot\.venv\Scripts\pip" install -q pyinstaller
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 설치 실패" }
& "$PSScriptRoot\.venv\Scripts\pyinstaller" --noconfirm --clean --onefile `
    --name handwrite-updater update_helper.py
if ($LASTEXITCODE -ne 0) { throw "업데이트 도우미 빌드 실패" }
& "$PSScriptRoot\.venv\Scripts\pyinstaller" --noconfirm --clean --onedir `
    --name handwrite-scanner `
    --add-data "app/static;static" `
    --collect-submodules app `
    launcher.py
if ($LASTEXITCODE -ne 0) { throw "프로그램 빌드 실패" }
Copy-Item -LiteralPath "$PSScriptRoot\dist\handwrite-updater.exe" -Destination "$PSScriptRoot\dist\handwrite-scanner\handwrite-updater.exe"
# 서버 모드 실행용 바로가기 배치
Set-Content -Encoding utf8 "$PSScriptRoot\dist\handwrite-scanner\server-mode.bat" `
    "@echo off`r`n`"%~dp0handwrite-scanner.exe`" --server`r`npause"
Compress-Archive -Force "$PSScriptRoot\dist\handwrite-scanner" "$PSScriptRoot\dist\handwrite-scanner.zip"
$releaseVersion = & "$PSScriptRoot\.venv\Scripts\python" -c 'from app.config import VERSION; print(VERSION)'
& $InnoCompiler "/DAppVersion=$releaseVersion" "$PSScriptRoot\installer.iss"
if ($LASTEXITCODE -ne 0) { throw "설치 프로그램 빌드 실패" }
Write-Host "빌드 완료: dist\handwrite-scanner-setup-$releaseVersion.exe 및 자동 업데이트 ZIP"
