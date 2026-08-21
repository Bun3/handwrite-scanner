# handwrite-scanner

프린트된 양식에 손으로 작성한 문서 사진을 → 필드별 텍스트로 인식 → 검수 →
**검색 가능한 PDF**로 만들어주는 localhost 웹앱. 모든 처리(비전-LLM 포함)가
로컬 CPU에서 돌아가며 **데이터가 PC 밖으로 나가지 않는다**.

## 요구 사양

- Windows, RAM 16GB 권장 (8GB면 3B 모델로 교체 — `app/config.py`)
- GPU 불필요. 사무용 CPU 기준 문서 1장당 수 분 (배치로 걸어두고 나중에 검수)

## 설치 (최초 1회)

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
powershell -ExecutionPolicy Bypass -File setup_engine.ps1   # llama.cpp + 모델 ~6GB
```

## 실행

```powershell
.\run.ps1   # 이후 브라우저에서 http://localhost:8000
```

## 사용법

1. **템플릿 등록** (인식률의 핵심): 템플릿 메뉴 → 빈 양식 이미지/PDF 등록 →
   이미지 위에 드래그로 필드 박스를 그리고 라벨·타입 지정.
   - 타입: 자유텍스트 / 후보목록(예: 이름 명단) / 전화번호 / 숫자(범위 지정 가능) / 동그라미 선택
   - 후보목록·범위 제약을 걸수록 인식률이 크게 올라간다
2. **업로드**: 작업 메뉴에서 사진 업로드 + 템플릿 선택 → 인식 시작
3. **검수**: 완료 후 필드별 crop 이미지와 인식 결과를 비교, 노란 강조(신뢰도 낮음)만 확인·수정
4. **다운로드**: PDF 2종 — 원본 모습 그대로 + 투명 텍스트층(검색/복사 가능), 또는 텍스트 재구성본

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
