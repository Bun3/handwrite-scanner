# handwrite-scanner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 수기 작성된 양식 문서 사진 → 필드별 인식 → 검수 → PDF 2종을 만드는 localhost 웹앱. 기준 테스트: `tests/fixtures/vacation-filled.png`(휴가신청서)가 정답 텍스트와 일치할 때까지.

**Architecture:** FastAPI 단일 앱(정적 프론트 + API + 백그라운드 워커 스레드) + llama.cpp `llama-server`(Qwen2.5-VL-7B Q4 GGUF, OpenAI 호환 API, CPU). 저장은 `data/` 파일 시스템.

**Tech Stack:** Python 3.14, FastAPI/uvicorn, httpx, Pillow, PyMuPDF(PDF→이미지), reportlab(PDF 생성), opencv-python(정합; cp314 휠 없으면 무보정 폴백), stdlib difflib(유사도). 프론트는 순수 HTML+JS.

**Spec:** `docs/superpowers/specs/2026-08-22-handwrite-scanner-design.md`

## Global Constraints

- 외부 API 호출 금지 — 모든 인식은 localhost llama-server로.
- CPU 단독 동작 (llama.cpp CPU 빌드 사용, GPU 코드 없음).
- DB 금지 — `data/` 폴더의 JSON 파일이 상태.
- 프론트 빌드 도구 금지 — `app/static/`의 정적 파일 그대로 서빙.
- 새 의존성은 위 Tech Stack 목록으로 한정.

## 기준 테스트 (E2E 성공 조건)

`tests/fixtures/vacation-filled.png` 를 휴가신청서 템플릿으로 인식했을 때 (공백 정규화 후 비교):

| 필드 | 정답 |
|---|---|
| 성명 | 홍길동 |
| 비상시 연락처 | 010-1234-5678 |
| 일시 | 2026년 8월 21일 9시부터 2026년 8월 22일 18시까지 1일간 |
| 월차잔여수(전) | 7 |
| 월차잔여수(후) | 6 |
| 사유 | 개인 사유 |
| 승인종류 | 월차 |

---

### Task 1: 프로젝트 스캐폴드 + 엔진 기동 확인

**Files:** Create `requirements.txt`, `app/main.py`, `app/config.py`, `app/llm.py`, `run.ps1`, `.gitignore`
**Produces:** `llm.ask_image(image_bytes: bytes, prompt: str) -> str` (llama-server /v1/chat/completions 호출, base64 data URI)

- [ ] venv 생성, `pip install fastapi uvicorn[standard] httpx pillow pymupdf reportlab pytest` (+ `opencv-python-headless` 시도, 실패 시 생략)
- [ ] `.gitignore`: `.venv/ engine/ data/ __pycache__/`
- [ ] `app/config.py`: 모델 경로·llama-server 포트(18080)·앱 포트(8000) 상수
- [ ] `app/llm.py`: llama-server subprocess 기동(`llama-server -m <gguf> --mmproj <mmproj> --port 18080`) + `ask_image()`
- [ ] `app/main.py`: FastAPI, `/api/health`에서 llama-server 응답 확인
- [ ] 수동 확인: 고정 텍스트 이미지 하나 `ask_image` 스모크 → 커밋

### Task 2: 후처리 모듈 (단위 테스트 대상)

**Files:** Create `app/postprocess.py`, `tests/test_postprocess.py`
**Produces:** `match_candidate(text, candidates) -> (best, confidence)` / `validate(text, field_type) -> (normalized, ok)` / `normalize_ws(text)`

- [ ] 실패 테스트 작성: 이름 유사도(오인식 "홍길동"→후보 [홍길동,김영수..] 최근접), 전화번호 정규화("010ㅡ1234 5678"→"010-1234-5678"), 숫자, 공백 정규화
- [ ] 구현: difflib.SequenceMatcher + 한글 자모 분해 비교, 정규식(전화/숫자/날짜), 신뢰도 산출
- [ ] pytest 통과 확인 → 커밋

### Task 3: 템플릿 저장소 + 정합

**Files:** Create `app/templates_store.py`, `app/align.py`
**Produces:** template.json 스키마 `{name, reference: "reference.png", fields: [{id,label,type,box:[x,y,w,h],candidates?}]}`; `align.to_reference(photo_bytes, ref_png_path) -> PIL.Image` (ORB+homography, 실패·opencv 부재 시 크기 맞춤 리사이즈 폴백)

- [ ] CRUD API: GET/POST/DELETE `/api/templates`, 기준 이미지 업로드(PDF면 PyMuPDF로 1페이지 300dpi PNG 렌더)
- [ ] `align.py` 구현 + 폴백
- [ ] 스모크: vacation-form.pdf 업로드 → reference.png 생성 확인 → 커밋

### Task 4: 인식 워커 + job API

**Files:** Create `app/worker.py`, `app/jobs.py`, main.py에 라우트 추가
**Produces:** POST `/api/jobs`(사진들+템플릿명) → job id; `data/jobs/<id>/status.json`(`queued|running|done|error`, progress), `results.json`(`[{page, fields:[{id,label,value,confidence,box}]}]`); GET `/api/jobs`, GET `/api/jobs/<id>`
**프롬프트 규약:** 필드 crop + "이 이미지는 '<라벨>' 칸의 손글씨다. <타입별 지시>. 값만 출력." / circle-choice는 "동그라미 쳐진 항목 하나만 출력. 선택지: [...]" / 템플릿 없으면 전면 이미지 → "모든 라벨: 값 JSON"

- [ ] 워커 스레드(큐 순차), 필드 crop(박스 여백 8px) → `llm.ask_image` → `postprocess` 적용
- [ ] 재시작 시 미완료 job 재큐잉
- [ ] 스모크: 템플릿 없이 vacation-filled.png 1회 처리 → 커밋

### Task 5: PDF 생성

**Files:** Create `app/pdf_gen.py`, 라우트 GET `/api/jobs/<id>/pdf?kind=searchable|text`
**Produces:** ⓐ 원본 이미지 + 필드 위치 투명 텍스트(reportlab render mode 3, 폰트 `C:\Windows\Fonts\malgun.ttf`) ⓑ "라벨: 값" 목록 PDF

- [ ] 구현 + 수동 확인(생성 PDF에서 텍스트 검색·복사) → 커밋

### Task 6: 프론트 UI

**Files:** Create `app/static/index.html`(업로드+작업목록), `app/static/template.html`(편집기), `app/static/review.html`(검수), 공용 `app/static/app.css`
**Produces:** 템플릿 편집기 = 이미지 위 canvas 드래그로 박스 → 라벨/타입/후보 입력; 검수 = 필드 crop 이미지 + 값 나란히, confidence<0.7 강조, 수정 PATCH `/api/jobs/<id>/fields`

- [ ] index: 업로드 폼(다중), 템플릿 선택, 작업 목록+진행률 폴링
- [ ] template.html: 박스 드로잉·편집·저장
- [ ] review.html: 필드 검수·수정, PDF 다운로드 버튼 2개
- [ ] 커밋

### Task 7: E2E — 기준 테스트 통과까지 반복

**Files:** Create `tests/test_e2e.py`(정답 비교, 서버 기동 전제 스킵 가능), `data/templates/휴가신청서/`

- [ ] orca 브라우저로 템플릿 편집기 열어 휴가신청서 템플릿 작성(성명=후보목록[홍길동 외 더미], 연락처=전화, 일시=자유텍스트, 월차잔여수 전/후=숫자, 사유=자유텍스트, 승인종류=circle-choice[지각,조퇴,결근,병가,반차,월차,경조사,공가,공적사유(교육)])
- [ ] vacation-filled.png 업로드 → 인식 → 결과를 기준 테이블과 비교
- [ ] 불일치 필드는 (crop 박스 조정 → 프롬프트 조정 → 후처리 보강) 순으로 수정, 전 필드 일치까지 반복
- [ ] PDF 2종 생성 확인, orca 브라우저로 전체 플로우 확인 → 커밋

## Self-Review

- 스펙 대비: 엔진(T1), 후처리(T2), 템플릿·정합(T3), 워커·폴백(T4), PDF 2종(T5), UI 3면(T6), 검수·E2E(T7) — 커버. 서버 재시작 재개는 T4에 포함.
- 타입 일관성: `ask_image`/`match_candidate`/template.json 스키마를 소비처(T4,T6,T7)와 동일 표기로 통일함.
