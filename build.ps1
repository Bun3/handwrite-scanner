# 배포 패키지 빌드: dist\handwrite-scanner\ 폴더 + zip
# 실행: powershell -ExecutionPolicy Bypass -File build.ps1
$ErrorActionPreference = "Stop"
& "$PSScriptRoot\.venv\Scripts\pip" install -q pyinstaller
& "$PSScriptRoot\.venv\Scripts\pyinstaller" --noconfirm --clean --onedir `
    --name handwrite-scanner `
    --add-data "app/static;static" `
    --collect-submodules app `
    launcher.py
# 서버 모드 실행용 바로가기 배치
Set-Content -Encoding utf8 "$PSScriptRoot\dist\handwrite-scanner\server-mode.bat" `
    "@echo off`r`n`"%~dp0handwrite-scanner.exe`" --server`r`npause"
Compress-Archive -Force "$PSScriptRoot\dist\handwrite-scanner" "$PSScriptRoot\dist\handwrite-scanner.zip"
Write-Host "빌드 완료: dist\handwrite-scanner.zip"
