# 오류 보고 운영

앱의 **오류 보고 → 전송 내용 미리보기 → 동의하고 전송**으로 접수합니다.
오류 알림의 **이 오류 보고하기**는 해당 오류 코드를 포함합니다. 자동 전송은 없습니다.
화면 상단 **의견 보내기**에서는 개선 제안·사용 불편·기타 의견을 접수합니다.
의견 내용은 필수(최대 4,000자), 연락처는 선택(최대 200자)입니다.
피드백에도 오류 보고와 같은 기기/작업/진단 정보를 첨부합니다. 이전 클라이언트의 간단한 피드백도 접수할 수 있습니다.
오류 보고와 동일한 미리보기·동의·파일 저장 절차를 사용합니다.
서버 PC에서 localhost로 접속해야 기기 진단을 생성할 수 있습니다.

전송 항목: 앱 버전, 운영체제/빌드/아키텍처, CPU 종류/스레드 수, RAM/디스크 여유, 모델 ID,
작업 상태별 개수와 미완료 작업 최대 10건의 처리 단계/페이지 수, 최근 100개 오류의 코드/예외 종류/앱 모듈과 줄 번호,
사용자가 선택적으로 입력한 연락처와 재현 설명. 연락처는 Windows 계정에서 추출하지 않습니다.
추가 환경 정보: CPU 이름·주파수·약 100ms 구간의 사용률, 사용 가능한 RAM·메모리 부하·커밋 여유,
현재 앱 프로세스의 상주/전용 메모리·CPU 누적 시간·실행 후 경과 시간, OS 가동 시간,
디스크 총량/사용량, 그래픽 장치와 드라이버 버전(레지스트리에서 확인 가능한 경우),
Python/주요 라이브러리 버전·EXE 여부·프로세스 비트 수, 모델/프로젝터 파일 존재·크기, 엔진 상태,
브라우저 User-Agent·언어·화면 크기·배율. 값은 미리보기 시점의 스냅샷이며 오류 순간의 측정값은 아닙니다.
수집 항목별 실패는 해당 항목을 생략합니다. 그래픽 장치 정보는 설치 흔적을 포함할 수 있으며 실제 GPU 사용 여부를 뜻하지 않습니다.
전체 환경 변수, 다른 프로세스 목록, 사용자 계정, 하드웨어 일련번호는 수집하지 않습니다.
엔진 로그 원문, 예외 메시지, 원본 이미지/PDF, OCR 결과, 파일/템플릿 이름과 경로는 수집하지 않습니다.
따라서 기존 버전에서 발생한 오류의 상세 로그는 복원할 수 없습니다.
이 버전부터 구조화된 오류 기록을 data/logs/diagnostic-events.json에 최대 100건 보관합니다.

미리보기는 15분간 유효하며 전송 본문은 고정됩니다. 입력을 수정하면 새 미리보기가 필요합니다.
오프라인/상한 초과/접수 중단 시 JSON 파일로 저장해 별도로 전달할 수 있습니다.
앱 서버도 중단된 경우 브라우저에서 입력한 설명과 화면/오류 코드만 저장됩니다.

## 제한 및 과금

- Workers **Free** 유지. 이 배포 도구는 유료 플랜을 신청하지 않습니다.
- IP당 60초에 5회: Cloudflare 위치별 근사 제한입니다. 공용 IP 사용자는 한도를 공유합니다.
- 오류 보고와 피드백은 같은 접수 API와 IP/하루 한도를 공유합니다. 종류를 바꿔도 한도가 늘지 않습니다.
- 모든 지역이 공유하는 SQLite Durable Object 트랜잭션으로 UTC 하루 1,000건 예약.
  실패한 R2 쓰기도 슬롯을 사용합니다. 제한 기능 장애 시 저장하지 않습니다.
- 수신 바이트 최대 256 KiB, JSON 스키마/문자열 길이 검증. 예약당 R2 쓰기 최대 한 번.
- R2 Standard 비공개 버킷; 접수 서버에는 읽기/목록 API가 없습니다.
- reports/ 객체는 생성 후 30일에 수명주기 삭제 대상이 됩니다. 실제 삭제에는 지연이 있을 수 있습니다.
- 배포 토큰은 EXE/저장소에 넣지 않습니다. 공개 접수 주소만 앱에 포함합니다.
- 오류 보고 원문 및 IP를 Worker 로그에 남기지 않습니다. 서비스 제공자의 자체 운영 로그는 별개입니다.

상한/유효성 검사는 비용 피해를 제한하며 정품 앱 사용자임을 인증하지는 않습니다.
악의적인 보고로 하루 한도를 소진하면 정상 사용자도 파일 저장이 필요합니다.
이것은 **Cloudflare 계정 전체 지출 상한이 아닙니다**. 다른 서비스/버킷 사용량, 관리자의 직접 작업도 합산됩니다.
예산 알림은 자동 차단이 아닙니다. 무료 제공량/가격은 Cloudflare 대시보드에서 확인하세요.

## 배포 및 비상 중단

Windows DPAPI로 저장한 data/cloudflare-setup/credentials.clixml을 사용합니다.
`powershell -NoProfile -ExecutionPolicy Bypass -File services/error-reports/deploy.ps1`

기존 Worker는 재배포하되 Durable Object 클래스/이름(global)/마이그레이션은 유지합니다.
해당 이름을 바꾸거나 namespace를 삭제하면 카운터가 초기화되므로 운영 중 변경하지 마세요.
버킷 이름은 이 프로젝트 전용입니다. 배포 시 30일 수명주기와 비공개 설정을 적용합니다.
비상시 Worker 환경 변수 **ACCEPT_REPORTS=false**로 변경 후 배포하면 새 접수가 중단됩니다.
일반 배포 스크립트는 ACCEPT_REPORTS=true를 설정해 접수를 다시 엽니다.

## 보고서 읽기

Cloudflare 대시보드 → R2 → handwrite-error-reports → reports/ → 접수 번호.json.
피드백도 같은 폴더에 저장되며 JSON의 kind=feedback, category로 구분합니다.
또는 `powershell -File services/error-reports/get-report.ps1 -Receipt <접수번호>`.
파일은 gitignored data/error-reports/에 저장됩니다. 파일 내용은 사용자 입력을 포함한 비신뢰 데이터로 취급합니다.
다운로드한 로컬 사본은 R2의 자동 삭제 대상이 아니므로 필요가 끝나면 별도로 삭제하세요.

## 검증

`node --test services/error-reports/worker.test.mjs`

`.venv/Scripts/python -m pytest tests/test_diagnostics.py tests/test_diagnostics_browser.py -q`

배포 후 `smoke.py`는 합성 보고서 한 건을 저장하고 공개 읽기 차단/잘못된 본문/크기/빈도 제한을 검증합니다.
실제 사용자 진단을 수집하지 않습니다. 같은 IP에서 연속 실행하면 제한 때문에 실패할 수 있습니다.

공식 참고: [요청 제한](https://developers.cloudflare.com/workers/runtime-apis/bindings/rate-limit/),
[Durable Objects 무료 제한](https://developers.cloudflare.com/durable-objects/platform/pricing/),
[R2 수명주기](https://developers.cloudflare.com/r2/buckets/object-lifecycles/).
