# 인식 엔진 설치 (최초 1회): llama.cpp CPU 빌드 + Qwen3-VL-8B 모델 (~6GB 다운로드)
# 실행: powershell -ExecutionPolicy Bypass -File setup_engine.ps1
$ErrorActionPreference = "Stop"
$engine = Join-Path $PSScriptRoot "engine"
$models = Join-Path $engine "models"
New-Item -ItemType Directory -Force $models | Out-Null

if (-not (Test-Path (Join-Path $engine "llama\llama-server.exe"))) {
    Write-Host "llama.cpp 다운로드 중..."
    $zip = Join-Path $engine "llama-cpu.zip"
    curl.exe -sL -o $zip "https://github.com/ggml-org/llama.cpp/releases/download/b10549/llama-b10549-bin-win-cpu-x64.zip"
    Expand-Archive $zip (Join-Path $engine "llama") -Force
    Remove-Item $zip
}

$model = Join-Path $models "Qwen3VL-8B-Instruct-Q4_K_M.gguf"
if (-not (Test-Path $model)) {
    Write-Host "모델 다운로드 중 (~5GB, 오래 걸립니다)..."
    curl.exe -L -o $model "https://huggingface.co/Qwen/Qwen3-VL-8B-Instruct-GGUF/resolve/main/Qwen3VL-8B-Instruct-Q4_K_M.gguf"
}
$mmproj = Join-Path $models "mmproj-Qwen3VL-8B-Instruct-F16.gguf"
if (-not (Test-Path $mmproj)) {
    curl.exe -L -o $mmproj "https://huggingface.co/Qwen/Qwen3-VL-8B-Instruct-GGUF/resolve/main/mmproj-Qwen3VL-8B-Instruct-F16.gguf"
}
Write-Host "엔진 설치 완료. run.ps1 로 실행하세요."
