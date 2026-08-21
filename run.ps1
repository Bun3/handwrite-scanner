# handwrite-scanner 실행 (브라우저에서 http://localhost:8000)
& "$PSScriptRoot\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
