# handwrite-scanner

📖 **[사용 안내서](https://bun3.github.io/handwrite-scanner/)** · ⬇ **[다운로드 (Releases)](https://github.com/Bun3/handwrite-scanner/releases)**

프린트된 양식에 손으로 작성한 문서 사진을 → 필드별 텍스트로 인식 → 검수 →
**검색 가능한 PDF**로 만들어주는 localhost 웹앱. 모든 처리(비전-LLM 포함)가
로컬 CPU에서 돌아가며 **데이터가 PC 밖으로 나가지 않는다**.

## 요구 사양

- Windows, RAM 16GB 권장 (8GB면 3B 모델로 교체 — `app/config.py`)
- GPU 불필요. 사무용 CPU 기준 문서 1장당 수 분 (배치로 걸어두고 나중에 검수)

## 설치 — 배포판 (권장, Python 불필요)

`build.ps1` 로 만든 `dist\handwrite-scanner.zip` 을 아무 폴더에 풀고:

- **개인용**: `handwrite-scanner.exe` 실행 → 첫 실행 시 엔진(~6GB) 자동 다운로드 → 브라우저 자동 열림
- **서버용**: 한 PC에서 `server-mode.bat` 실행 → 콘솔에 표시되는 `http://<서버IP>:8000` 주소로
  다른 PC들이 브라우저 접속 (최초 1회 Windows 방화벽 허용 필요). 데이터는 사내망 밖으로 안 나감

## 설치 — 소스 (개발용)

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -c "from app.engine_setup import ensure_engine; ensure_engine()"  # llama.cpp + 모델 ~6GB
.\run.ps1   # 이후 브라우저에서 http://localhost:8000
```

배포판 빌드: `powershell -ExecutionPolicy Bypass -File build.ps1` → `dist\handwrite-scanner.zip`

## 사용법

1. **템플릿 등록** (인식률의 핵심): 템플릿 메뉴 → 빈 양식 이미지/PDF 등록 →
   이미지 위에 드래그로 필드 박스를 그리고 라벨·타입 지정.
   - 타입: 자유텍스트 / 후보목록(예: 이름 명단) / 전화번호 / 숫자(범위 지정 가능) / 동그라미 선택
   - 후보목록·범위 제약을 걸수록 인식률이 크게 올라간다
2. **업로드**: 작업 메뉴에서 사진 업로드 + 템플릿 선택 → 인식 시작
3. **검수**: 완료 후 필드별 crop 이미지와 인식 결과를 비교, 노란 강조(신뢰도 낮음)만 확인·수정
4. **다운로드**: PDF 2종 — 원본 모습 그대로 + 투명 텍스트층(검색/복사 가능), 또는 텍스트 재구성본

오류 또는 중단된 작업은 **이어하기**로 완료된 페이지의 결과를 유지하고 미완료 페이지부터 다시 처리할 수 있습니다. 처리 도중 멈춘 페이지는 그 페이지의 첫 항목부터 다시 인식합니다. **처음부터 재인식**은 기존 결과를 지우고 1페이지부터 다시 처리하므로, 템플릿이나 규칙을 바꾼 뒤 전체에 적용할 때 사용하세요.

**인식 시작**을 누르면 업로드 중 표시가 즉시 나타납니다. 파일 접수 후 PDF 변환은 백그라운드에서 진행하며, 작업 목록에서 문서 준비·엔진 준비·인식 상태를 확인할 수 있습니다. 오류가 발생하면 브라우저 알림과 작업 목록에 원인 및 해결 방법을 표시합니다. **기술 상세**를 펼치면 엔진 로그를 포함한 진단 내용을 복사할 수 있습니다. 저장 공간 부족으로 오류 상태조차 기록할 수 없을 때는 실행 중인 프로그램의 메모리에 안내를 유지합니다.

## 프로그램 업데이트

자동 업데이트 기능이 포함된 Windows 배포판에서는 새 버전 알림의 **지금 업데이트**를 누르면 다운로드·파일 검증·프로그램 교체·재실행을 자동으로 진행합니다. 실행 중인 작업과 모델 다운로드를 끝내고, 폰 업로드도 끈 뒤 진행하세요. 서버 모드라면 서버 PC의 브라우저에서 업데이트해야 합니다.

`data/`(템플릿·작업 기록·설정)와 `engine/`(모델)는 교체하지 않습니다. 새 버전 실행에 실패하면 이전 프로그램을 복원해 다시 실행합니다. 백업과 진단 기록은 `data/updates/`에 남으며, 전원 중단 등으로 도우미까지 종료된 경우에는 프로그램을 종료한 상태에서 해당 업데이트 폴더의 `recover.cmd`로 이전 프로그램 복구를 시도할 수 있습니다.

v0.7.0·v0.7.1처럼 이 기능이 없는 버전은 자동 업데이트 기능이 포함된 배포판으로 한 번 수동 전환해야 합니다. 개발용 Python 실행 환경은 자동 교체 대상이 아닙니다.

## 테스트

```powershell
.venv\Scripts\python -m pytest tests\test_postprocess.py     # 단위 테스트
.venv\Scripts\python -X utf8 -m pytest tests\test_e2e.py     # E2E (서버 기동 필요, 수 분)
```

## 구조


```
app/main.py        FastAPI 라우트 + 정적 프론트 서빙
app/llm.py         llama-server(Qwen3-VL-8B GGUF) 기동·호출
app/worker.py      인식 워커: 정합→필드 crop→VLM→후처리→2차 검증
app/postprocess.py 후보 유사도 매칭(자모 분해)·형식 검증·범위 보정
app/align.py       ORB+homography 로 사진을 템플릿 좌표계에 정합
app/pdf_gen.py     PDF 생성 (투명 텍스트층 / 텍스트 재구성)
data/templates/    템플릿(필드 좌표·라벨·후보) — 파일이 곧 상태, DB 없음
data/jobs/         작업별 입력·결과·PDF
```
