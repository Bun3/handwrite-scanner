import sys
from pathlib import Path

VERSION = "0.3.0"
GITHUB_REPO = "Bun3/handwrite-scanner"

if getattr(sys, "frozen", False):  # PyInstaller 배포판: exe 옆에 engine/data
    BASE_DIR = Path(sys.executable).resolve().parent
    STATIC_DIR = Path(sys._MEIPASS) / "static"
else:
    BASE_DIR = Path(__file__).resolve().parent.parent
    STATIC_DIR = BASE_DIR / "app" / "static"
ENGINE_DIR = BASE_DIR / "engine"
LLAMA_SERVER = ENGINE_DIR / "llama" / "llama-server.exe"
MODEL = ENGINE_DIR / "models" / "Qwen3VL-8B-Instruct-Q4_K_M.gguf"
MMPROJ = ENGINE_DIR / "models" / "mmproj-Qwen3VL-8B-Instruct-F16.gguf"
LLAMA_PORT = 18080
APP_PORT = 8000

DATA_DIR = BASE_DIR / "data"
TEMPLATES_DIR = DATA_DIR / "templates"
JOBS_DIR = DATA_DIR / "jobs"
for d in (TEMPLATES_DIR, JOBS_DIR):
    d.mkdir(parents=True, exist_ok=True)
