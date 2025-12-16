# paper_review

개인용 논문 리뷰 시스템 (Google Drive 보관 + DOI 메타데이터 + OpenAI 단일 세션 멀티-페르소나 분석).

현재는 **백엔드 API + 워커(MVP 파이프라인) + 간단한 Web UI**가 포함되어 있습니다.

## Quickstart (Local)

1) DB 실행

- `docker compose up -d db`

2) 가상환경/의존성

- `python -m venv .venv`
- Windows PowerShell: `.venv\\Scripts\\Activate.ps1`
- `pip install -e .`

3) 환경변수

- `.env.example` → `.env` 복사 후 값 채우기
- 최소 필요: `DATABASE_URL`, `OPENAI_API_KEY`, (Google Drive 인증 1종)
- Supabase를 쓰는 경우: **Connection Pooling(Pooler) URI**를 `DATABASE_URL`로 쓰는 걸 권장합니다(특히 IPv6 없는 네트워크에서 `db.<ref>.supabase.co`가 실패할 수 있음). 예:
  - `postgresql://postgres.<project_ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres?sslmode=require`
- Google Drive: 사용하는 OAuth 프로젝트에서 **Google Drive API(drive.googleapis.com)** 를 Enable 해야 다운로드가 됩니다.

4) 테이블 생성

- `paper-review init`

5) 서버/워커 실행

- API: `paper-review serve`
- Worker: `paper-review worker`

## Web UI

- 브라우저에서 `http://127.0.0.1:8000` 접속
- New paper에서 아래 중 하나(또는 조합)로 등록:
  - 로컬 PDF 업로드
  - Google Drive file id 입력
  - DOI-only (PDF 없이도 등록/분석 가능: no-PDF 모드로 evidence는 빈 배열로 처리)
- 로컬 PDF 업로드는 `UPLOAD_DIR`(기본 `./data/uploads`)에 저장되며, `data/`는 gitignore 처리되어 있습니다.

## Web UI 로그인(Cloud 배포용)

`.env`에 아래를 설정하면 로그인 화면이 활성화됩니다.

- `WEB_USERNAME`, `WEB_PASSWORD`, `SESSION_SECRET`
- HTTPS 환경이면 `COOKIE_HTTPS_ONLY=true` 권장

## Cloudtype 배포 체크리스트

권장 구조: **API 서비스 1개 + Worker 서비스 1개** (둘 다 같은 레포/이미지 사용).

1) DB 준비

- Cloudtype 내장 DB 또는 외부 Postgres(Supabase 등) 준비
- `DATABASE_URL` 설정 (Supabase면 Pooler + `?sslmode=require` 권장)

2) 서비스 2개 생성

- API (웹): 시작 커맨드 예시
  - `paper-review serve --host 0.0.0.0 --port $PORT --no-reload`
- Worker(백그라운드): 시작 커맨드 예시
  - `paper-review worker --log-level INFO`
  - (플랫폼이 포트 리슨을 요구하면) `paper-review worker-serve --host 0.0.0.0 --port $PORT`

3) 환경변수(둘 다 동일하게)

- 필수: `DATABASE_URL`, `OPENAI_API_KEY`
- Web 로그인(권장): `WEB_USERNAME`, `WEB_PASSWORD`, `SESSION_SECRET`, `COOKIE_HTTPS_ONLY=true`
- Drive 다운로드(선택: 둘 중 하나)
  - OAuth: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN`
  - Service account: `GOOGLE_SERVICE_ACCOUNT_FILE`(Cloudtype의 secret file/mount 기능 필요)
- 업로드 테스트(선택):
  - `UPLOAD_BACKEND=drive` 권장(서비스 분리 시 로컬 디스크는 공유되지 않음)
  - `GOOGLE_DRIVE_SCOPE=https://www.googleapis.com/auth/drive`
  - (선택) `GOOGLE_DRIVE_UPLOAD_FOLDER_ID`
  - (로컬 저장을 쓰면) `UPLOAD_DIR` (Cloud 환경이면 `/tmp/uploads` 같은 경로 권장)

4) 동작 확인

- API URL에서 `/health` 확인 후, 루트(`/`)로 접속해 Web UI 로그인/등록/분석

## API 사용 예시

- 논문 등록(Drive 파일 ID 기반):
  - `curl -X POST http://127.0.0.1:8000/api/papers -H "Content-Type: application/json" -d "{\"drive_file_id\":\"...\",\"doi\":\"10.1234/...\"}"`
- 논문 등록(DOI-only):
  - `curl -X POST http://127.0.0.1:8000/api/papers -H "Content-Type: application/json" -d "{\"doi\":\"10.1234/...\"}"`
- 논문 등록(로컬 PDF 업로드):
  - `curl -X POST "http://127.0.0.1:8000/api/papers/upload?doi=10.1234/..." -H "Content-Type: application/pdf" --data-binary "@paper.pdf"`
- 분석 큐잉:
  - `curl -X POST http://127.0.0.1:8000/api/papers/<paper_id>/analyze`
- 상태/결과 조회:
  - `curl http://127.0.0.1:8000/api/papers/<paper_id>`

## DB 스키마

- 참고 SQL: `sql/0001_init.sql`
- 앱은 개발 편의를 위해 시작 시 `create_all`로 테이블을 생성합니다(프로덕션은 마이그레이션 권장).
