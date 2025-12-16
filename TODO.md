# TODO (You)

## 1) 외부 서비스 준비

- OpenAI: API Key 발급 → `.env`의 `OPENAI_API_KEY` 설정
- Postgres/Supabase:
  - 로컬: `docker-compose.yml`로 Postgres 실행 후 `.env`의 `DATABASE_URL` 설정
  - 또는 Supabase 프로젝트 생성 후 connection string으로 `DATABASE_URL` 설정
  - Supabase에서 `paper-review init`가 `getaddrinfo failed`로 실패하면: **Connection Pooling(Pooler) URI**로 바꿔서 IPv4 호스트(`*.pooler.supabase.com`)를 사용
- Google Drive 접근 방식 결정(둘 중 하나)
  - OAuth(개인 Drive 권장): GCP에서 OAuth Client 생성 → refresh token 발급 → `GOOGLE_CLIENT_ID/SECRET/REFRESH_TOKEN` 설정
  - Service Account(Shared Drive/팀 권장): 키 JSON 생성 → `GOOGLE_SERVICE_ACCOUNT_FILE` 설정 + 대상 Drive 파일/폴더 공유 권한 부여
  - 공통: Google Cloud Console에서 **Google Drive API(drive.googleapis.com) Enable** (미설정 시 403/“missing API key” 또는 “SERVICE_DISABLED” 발생)
- (선택) Semantic Scholar: 필요 시 API 키 발급 → `SEMANTIC_SCHOLAR_API_KEY` 설정

## 2) 로컬 실행 체크리스트

- `.env.example` → `.env` 복사 후 값 채우기
- DB 테이블 생성: `paper-review init`
- API/워커 실행: `paper-review serve`, `paper-review worker`

## 3) 데이터 준비(Drive file_id)

- 분석할 PDF를 Google Drive에 업로드
- URL에서 `file_id` 확보(예: `.../file/d/<file_id>/view`)
- Service Account를 쓰는 경우: 해당 파일(또는 상위 폴더)을 서비스 계정 이메일에 공유

## 4) MVP 검증 플로우

- Paper 생성: `POST /api/papers` (drive_file_id, doi 선택)
- 분석 큐잉: `POST /api/papers/{id}/analyze`
- 결과 확인: `GET /api/papers/{id}` (latest_run/status, latest_output)

$driveId = "YOUR_DRIVE_FILE_ID"
$headers = @{}  # API_KEY를 .env에 설정했다면: @{ "X-API-Key" = "YOUR_API_KEY" }
$paper = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/papers" -ContentType "application/json"         -Headers $headers `
    -Body (@{ drive_file_id = $driveId; doi = $doi } | ConvertTo-Json)
$run = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/papers/$($paper.id)/analyze" -Headers $headers
$detail = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/papers/$($paper.id)" -Headers $headers
$detail.latest_run.status}
$detail.latest_content_md

## 5) 다음 구현 우선순위(결정/작업)

- Frontend: 로그인 + Drive Resumable Upload + 페르소나 탭 UI
- Auth: Supabase Auth(JWT) 연동 + RLS 정책
- 대용량 PDF(>50MB): 텍스트 추출(A) 또는 분할(B) 파이프라인 구현(main.txt 9.1)
- DOI-only 플로우: evidence 제약 반영한 스키마/UX 분기(main.txt 9.2)
- 검색/필터 고도화: tags, rating, 상태, 전문검색
- 추천/유사논문: pgvector + Semantic Scholar Recommendations(main.txt 10)
- Zotero/Obsidian 연동(main.txt 11)
