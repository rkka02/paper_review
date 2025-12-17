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
- 현재 UI의 New paper는 **Analysis JSON 업로드/붙여넣기**를 기본 입력으로 사용합니다.
  - (PDF/Drive/DOI 입력 UI는 현재 숨김 처리되어 있을 수 있습니다. API는 지원합니다.)
- 업로드 후:
  - `Graph` 버튼: 논문 연결 그래프 뷰
  - `Recs` 버튼: 서버에 저장된 “오늘의 추천” 목록/요약

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

## Discord (Role 멘션 → 멀티-페르소나 답장)

Discord에서 `@레이 우리 그 논문 어떻게 생각해?`처럼 **Role 멘션**으로 서버에 질문하면, 봇이 메시지를 수신하고 **Webhook**으로 “페르소나 이름/아이콘”으로 답장합니다.

### 준비 (Discord 설정)
- Discord 설정 → 고급(Advanced) → **Developer Mode** ON
- 페르소나별 Role 생성(예: 히카리/레이/츠구미) 후, Role 우클릭 → **Copy ID**
- Discord Bot 생성 후 **MESSAGE CONTENT INTENT** ON, 서버(길드)에 초대
- 답장을 보낼 채널에서 Webhook 생성 후 URL 확보

### 환경변수(.env) - 공통
- 필수: `DISCORD_BOT_TOKEN`(수신), `DISCORD_WEBHOOK_URL`(발신)
- 접근 제한(선택): `DISCORD_ALLOWED_USER_IDS`, `DISCORD_ALLOWED_GUILD_IDS` (comma-separated)
- 주의: 현재는 `DISCORD_WEBHOOK_URL` **1개 채널**로만 답장합니다(여러 채널 분기는 추후 확장 필요).

### 멀티 페르소나 설정 방법
**A) 간단 설정(기본 3종)**: 히카리/레이/츠구미
- Role ID 지정: `DISCORD_PERSONA_HIKARI_ROLE_ID`, `DISCORD_PERSONA_REI_ROLE_ID`, `DISCORD_PERSONA_TSUGUMI_ROLE_ID`
- 프롬프트 수정: `docs/personas/hikari.md`, `docs/personas/rei.md`, `docs/personas/tsugumi.md`
- (선택) 아바타: `DISCORD_PERSONA_*_AVATAR_URL`

**B) 자유 설정(N종, 권장)**: `DISCORD_PERSONAS_JSON`
- 각 페르소나를 Role 1개에 매핑합니다(메시지에서 `msg.role_mentions`로 판별).
- JSON 항목 필수 키: `key`, `display_name`, `role_id`, `prompt_path`
- 선택 키: `llm_provider`(`openai`|`google`|`ollama`), `avatar_url`

예시(실제 `.env`에는 한 줄로 넣는 걸 권장):
```env
DISCORD_PERSONAS_JSON=[{"key":"hikari","display_name":"히카리","role_id":111,"prompt_path":"docs/personas/hikari.md","llm_provider":"openai"},{"key":"rei","display_name":"레이","role_id":222,"prompt_path":"docs/personas/rei.md","llm_provider":"openai"},{"key":"tsugumi","display_name":"츠구미","role_id":333,"prompt_path":"docs/personas/tsugumi.md","llm_provider":"ollama"}]
DISCORD_PERSONA_DEFAULT_LLM_PROVIDER=openai
```

### 페르소나 답장 LLM 선택
- 기본값: `DISCORD_PERSONA_DEFAULT_LLM_PROVIDER=openai`
- `openai`: `OPENAI_API_KEY`, `OPENAI_MODEL` 필요
- `google`: `GOOGLE_AI_API_KEY`, `GOOGLE_AI_MODEL` 필요
- `ollama`: `ollama serve` 실행 + `OLLAMA_BASE_URL`, `LOCAL_LLM_MODEL` 설정
  - 팁: Gemini 출력이 중간에 끊기면(`finishReason=MAX_TOKENS`), `.env`의 `GOOGLE_AI_MAX_OUTPUT_TOKENS` 값을 올려보세요.

### 실행
- Bot 실행: `paper-review discord-bot`
- PaaS에서 포트가 필요하면: `paper-review discord-bot-serve --host 0.0.0.0 --port $PORT`
- 참고: Discord Bot은 서버 API를 호출하지 않고 DB를 직접 읽습니다 → `DATABASE_URL`이 서버와 동일해야 합니다.

### 사용 팁
- 한 메시지에는 페르소나 Role을 **1개만** 멘션하세요(여러 개면 어떤 페르소나로 처리될지 보장되지 않음).
- 특정 논문을 지정하려면 DOI 또는 paper id(UUID)를 같이 보내면 정확도가 올라갑니다.

### Discord 알림(추천 완료/실패)
추천 작업(수동 Run / 스케줄러 auto-run)이 끝나면 Discord 웹훅으로 알립니다.

- `DISCORD_NOTIFY_RECOMMENDER=true`
- (선택) `DISCORD_NOTIFY_WEBHOOK_URL` (없으면 `DISCORD_WEBHOOK_URL` 사용)
- (선택) `DISCORD_NOTIFY_USERNAME`, `DISCORD_NOTIFY_AVATAR_URL`
- (스케줄러) `RECOMMENDER_AUTO_RUN=true`, `RECOMMENDER_AUTO_RUN_TIME=06:00`

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

## Local AI 테스트 (Semantic Scholar + Embeddings)

로컬에서 논문 추천/검색용 임베딩 파이프라인을 먼저 검증하기 위한 **통합 테스트**가 있습니다.

- 설치(예시):
  - `pip install -r requirements-dev.txt`
- 실행(Windows PowerShell):
  - `$env:RUN_LOCAL_AI_TESTS="1"`
  - `pytest -q`
- 옵션:
  - `OPENAI_API_KEY`가 필요합니다 (임베딩은 OpenAI 전용).
  - `$env:OPENAI_EMBED_MODEL="text-embedding-3-large"`
  - `SEMANTIC_SCHOLAR_API_KEY`를 설정하면 rate limit에 더 안전합니다.
- 테스트는 Semantic Scholar seed 결과를 `.pytest_cache/local_ai/semantic_scholar_seed.json`에 캐시합니다.

## Embeddings DB 관리

임베딩 모델을 바꾸는 경우(예: `OPENAI_EMBED_MODEL` 변경) 기존 벡터와 섞이지 않도록 `paper_embeddings`를 초기화하는 커맨드를 제공합니다.

- 전체 초기화: `paper-review embeddings-reset --yes`
- 재생성(현재 설정 기준): `paper-review embeddings-rebuild --yes`
- 백엔드 강제(1회): `paper-review embeddings-rebuild --yes --provider openai`

## 오늘의 추천(로컬 파이프라인)

로컬에서 아래 파이프라인을 돌린 뒤, 결과(JSON)를 서버로 업로드해서 Web UI에서 “오늘의 추천”으로 보는 구조입니다.

1) 서버 라이브러리 동기화: `/api/folders`, `/api/papers/summary` 호출
2) 후보 수집: Semantic Scholar에 쿼리 검색 + seed 논문(랜덤 선택) 기준 reference/citation 확장
3) 랭킹: 후보 vs 내 라이브러리(폴더별) 임베딩 유사도 → top-k
4) 최종 선택: LLM이 폴더별 3개 + cross-domain 3개를 고르고 1줄 요약/근거 생성
5) 업로드: `/api/recommendations`로 저장 → Web UI 상단 `Recs` 버튼에서 확인

### 필수 환경변수

- 서버 접근: `SERVER_BASE_URL`, (`SERVER_API_KEY` 또는 `API_KEY`)
- Semantic Scholar: `SEMANTIC_SCHOLAR_API_KEY`
- 서버가 Web 로그인만 켜져 있으면(API_KEY 미설정): `paper-review recommend --web-username ... --web-password ...`
  - `SERVER_BASE_URL`이 `127.0.0.1/localhost`인 경우, CLI는 `API_KEY`가 없으면 `.env`의 `WEB_USERNAME/WEB_PASSWORD`로 자동 로그인도 시도합니다.

### 로컬 LLM(쿼리 생성) - Ollama 권장

로컬 LLM은 **Ollama**를 기본으로 사용합니다.

- Ollama 실행: `ollama serve`
- 모델 준비(예): `ollama pull gpt-oss-20b`
- `.env` 설정:
  - `RECOMMENDER_QUERY_LLM_PROVIDER=ollama` (또는 `local`)
  - `OLLAMA_BASE_URL=http://127.0.0.1:11434`
  - `LOCAL_LLM_MODEL=gpt-oss-20b`
  - (OpenAI로 쿼리 생성도 가능) `RECOMMENDER_QUERY_LLM_PROVIDER=openai` + `OPENAI_API_KEY`, `OPENAI_MODEL`

### 최종 선택 LLM(OpenAI → 나중에 로컬로 교체 가능)

- 기본값: `RECOMMENDER_DECIDER_LLM_PROVIDER=openai` + `OPENAI_API_KEY`, `OPENAI_MODEL`
- 나중에 Ollama로 바꾸려면: `RECOMMENDER_DECIDER_LLM_PROVIDER=ollama` (또는 `local`)

### 실행

- 추천 생성 + 서버 업로드: `paper-review recommend --yes`
- JSON만 저장(업로드 안 함): `paper-review recommend --yes --dry-run --out ./tmp/recommendations.json`
