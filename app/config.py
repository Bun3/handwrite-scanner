import sys
from pathlib import Path

VERSION = "0.4.1"
GITHUB_REPO = "Bun3/handwrite-scanner"

if getattr(sys, "frozen", False):  # PyInstaller 배포판: exe 옆에 engine/data
    BASE_DIR = Path(sys.executable).resolve().parent
    STATIC_DIR = Path(sys._MEIPASS) / "static"
else:
    BASE_DIR = Path(__file__).resolve().parent.parent
    STATIC_DIR = BASE_DIR / "app" / "static"
ENGINE_DIR = BASE_DIR / "engine"
LLAMA_SERVER = ENGINE_DIR / "llama" / "llama-server.exe"
# 인식 모델은 app/models.py 카탈로그에서 선택 (data/settings.json 에 저장)
LLAMA_PORT = 18080
APP_PORT = 8000

DATA_DIR = BASE_DIR / "data"
TEMPLATES_DIR = DATA_DIR / "templates"
JOBS_DIR = DATA_DIR / "jobs"
for d in (TEMPLATES_DIR, JOBS_DIR):
    d.mkdir(parents=True, exist_ok=True)
