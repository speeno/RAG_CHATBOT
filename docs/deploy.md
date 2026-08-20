# 배포 가이드 — Vercel(프론트) + Render(백엔드) + Supabase(DB), 전부 무료 티어

> 결론: **가능하다.** 단, 무료 티어 제약 때문에 (1) SQLite 대신 Supabase Postgres를 쓰고, (2) Render↔Supabase는 **Session Pooler(IPv4)** 로 연결하며, (3) 콜드스타트/무활동 정지를 감수(또는 keep-alive)해야 한다.
> 이 리포는 위 사항이 모두 코드에 반영되어 있다(`DATABASE_URL`, `CORS_ORIGIN_REGEX`, `render.yaml`, 프론트 "서버 깨우는 중" 안내).

> 이 절차는 Claude Code 플러그인 **deploy-3tier**(`/plugin marketplace add speeno/claude-plugins` → `/plugin install deploy-3tier@speeno-plugins`)로 다른 프로젝트에도 적용할 수 있다. 설치 가이드: [deploy-3tier-plugin-install.md](deploy-3tier-plugin-install.md)

## 현재 배포 상태 (2026-08-19)

| 구성 | URL / 식별자 |
|---|---|
| 프론트(Vercel, 프로젝트 `rag-chatbot`, 스코프 mudotmusic-6437) | https://rag-chatbot-ten-cyan.vercel.app (사용자 공유용: **/embed**) |
| 백엔드(Render, `rag-chatbot-api`, free, singapore, `srv-da2qv00n74is738hld7g`) | https://rag-chatbot-api-6aqk.onrender.com (`/api/health`) |
| DB(Supabase, `rag-chatbot`, ap-southeast-1, ref `ytlprajblmrjfkgjnivv`) | Session Pooler `aws-0-ap-southeast-1.pooler.supabase.com:5432` — 비밀번호는 Render env `DATABASE_URL`에만 있음 |

운영 중 배포 명령(로컬 CLI):
```bash
# 백엔드 재배포 (Render는 GitHub 앱 미연결 상태라 push만으로는 자동 배포되지 않음 → 수동 트리거 또는 대시보드에서 GitHub 연결)
render deploys create srv-da2qv00n74is738hld7g --confirm
# 프론트 재배포
cd frontend && vercel deploy --prod --yes --scope mudotmusic-6437s-projects
# 백엔드 env 변경은 Render 대시보드(Environment) 또는 REST API(PUT /v1/services/{id}/env-vars)
```

배포 과정에서 확인된 것:
- CLI 로그인: `render login`(브라우저 승인 → 자동 완료), `supabase login`(브라우저에 뜬 8자리 코드를 **터미널에 입력**해야 완료).
- Render 서비스 생성 직후 수 분간 `x-render-routing: no-server` 404가 간헐적으로 발생 → `render deploys create`로 한 번 재배포하니 해소. 프론트 `api.health()`는 404/5xx에 짧게 재시도하도록 보강됨.
- Vercel CLI로 Preview 환경변수 추가가 `api_error`로 실패(Git 미연결 프로젝트) → Production만 설정. Preview를 쓰려면 대시보드에서 `NEXT_PUBLIC_API_URL` 추가.

## 0. 왜 이 구성인가

| 구성 요소 | 무료 티어 제약 | 이 프로젝트에서의 대응 |
|---|---|---|
| **Render** Web Service(Free) | 디스크 휘발성(persistent disk 불가) · 15분 유휴 시 스핀다운(첫 요청 ~1분) · 512MB RAM / 0.1 CPU · 월 750 인스턴스-시간 · IPv4만 지원 | 데이터는 전부 Supabase Postgres에 저장(원문도 `documents.raw_text` 컬럼 → 파일 저장소 불필요). 벡터 검색은 numpy 인메모리(수천 청크 규모 OK) |
| **Supabase** Free | DB 500MB · **7일 무활동 시 일시정지** · 직결(5432 direct)은 IPv6 전용 | `/api/health`가 `SELECT 1`을 수행 → keep-alive ping 하나로 Render·Supabase 둘 다 깨어 있음. 접속은 **Session Pooler URI** 사용 |
| **Vercel** Hobby | 비상업 용도 · 100GB 대역폭 | 프론트는 정적/클라이언트 호출만 하므로 제약 없음. SSE는 브라우저→Render 직접 연결이라 Vercel 함수 제한과 무관 |

**백엔드를 Vercel에 올리는 것**은 기술적으로는 가능(Python 런타임, 스트리밍 지원)하나 권장하지 않는다: 업로드 후 백그라운드 색인 스레드(`index_async`)가 서버리스에서는 보장되지 않고, 콜드스타트마다 임베딩 행렬을 다시 로드하며, 어차피 SQLite는 쓸 수 없다. 상시 프로세스인 Render가 현재 구조에 맞다. (정말 Vercel로 가야 한다면 `sync=true` 색인만 쓰고 `vercel.json`에 `@vercel/python` 빌드를 추가하는 방식 — 이 문서 범위 밖.)

---

## 1. 사전 준비 (로컬)

```bash
# 백엔드: 의존성(psycopg 포함) 설치 + 테스트
cd backend && uv pip install -e ".[dev]" --python .venv/bin/python
.venv/bin/python -m pytest -q                      # SQLite 경로 15개 통과, Postgres 테스트는 skip

# Postgres 어댑터 실검증(로컬 PG 또는 Supabase URI 아무거나)
TEST_DATABASE_URL=postgresql://localhost/rag_chatbot_test .venv/bin/python -m pytest -q tests/test_postgres.py
```

- GitHub 리포(`speeno/RAG_CHATBOT`)에 push 되어 있어야 한다. `openaikey`, `backend/.env`, `backend/data/`는 `.gitignore` 되어 있는지 확인(`git status` 깨끗함).
- 운영에서는 `../openaikey` 파일 폴백이 동작하지 않으므로 **LLM/임베딩 키는 반드시 환경변수**로 넣는다. 키가 없으면 `extractive`/`hash` 오프라인 데모 모드로 조용히 강등된다(`/api/health`의 `offline_mode:true`로 확인).

## 2. Supabase — 프로젝트 생성 & 접속 문자열

1. https://supabase.com → New project (Free). **리전은 Render와 같은 권역**(예: Singapore ↔ Render `singapore`)으로. DB 비밀번호를 기록.
2. 프로젝트 ▸ 상단 **Connect** ▸ *Connection string* ▸ **Session pooler** 탭 선택 → URI 복사
   `postgresql://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres`
   끝에 `?sslmode=require`를 붙여 `DATABASE_URL`로 사용한다.
   - ⚠️ *Direct connection*(`db.<ref>.supabase.co:5432`)은 IPv6 전용이라 **Render에서 연결 실패**한다. 반드시 pooler 주소(IPv4).
   - Transaction pooler(6543)도 동작하지만(prepared statement를 꺼 두었음) 세션 모드를 권장.
3. 테이블은 앱 기동 시 `CREATE TABLE IF NOT EXISTS`로 자동 생성된다. 별도 마이그레이션 불필요.
4. 로컬에서 먼저 확인:
   ```bash
   cd backend
   DATABASE_URL='<session pooler uri>?sslmode=require' .venv/bin/uvicorn app.main:app --port 8000
   curl -s localhost:8000/api/health   # db_backend:"postgres", db_ok:true
   DATABASE_URL='<...>' .venv/bin/python scripts/seed.py   # 샘플 문서 3건 색인(운영 임베딩 키로!)
   ```
   > 임베딩 provider가 바뀌면 벡터 차원이 달라져 검색 결과가 0건(Fail-Closed)이 된다. 운영에서 쓸 임베딩 키(Voyage/OpenAI)를 설정한 상태로 시드/색인할 것.

## 3. Render — 백엔드 배포

1. https://dashboard.render.com → **New ▸ Blueprint** → GitHub 리포 선택 → 리포 루트의 `render.yaml`을 읽어 `rag-chatbot-api`(Free, rootDir `backend`)를 만든다.
   (수동으로 할 경우: New ▸ Web Service, Root Directory `backend`, Build `pip install --upgrade pip && pip install .`, Start `uvicorn app.main:app --host 0.0.0.0 --port $PORT`, Health Check Path `/api/health`, env `PYTHON_VERSION=3.12.7`.)
2. 환경변수 입력(`sync: false` 항목):
   | key | 값 |
   |---|---|
   | `DATABASE_URL` | 2단계의 Session pooler URI (+`?sslmode=require`) |
   | `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `VOYAGE_API_KEY` | 사용할 것만 (auto: Anthropic→OpenAI→extractive / Voyage→OpenAI→hash) |
   | `CORS_ORIGINS` | 일단 비워두고 4단계 후 `https://<project>.vercel.app` |
   | `CORS_ORIGIN_REGEX` | `https://.*\.vercel\.app` (Preview 배포 허용; 필요 없으면 비움) |
   | `ADMIN_TOKEN` | 관리자 화면/API 보호 토큰(긴 랜덤 문자열). 비우면 관리자 화면이 공개됨 |
3. Deploy → 로그에 `services ready: {... 'db_backend': 'postgres', 'db_ok': True ...}` 확인 → `https://<svc>.onrender.com/api/health` 응답 확인.
4. 시드: 무료 티어는 Shell이 제한적이므로 로컬에서 `DATABASE_URL=<supabase> python scripts/seed.py`로 넣거나, 배포된 프론트 `/admin/knowledge`에서 업로드한다.

## 4. Vercel — 프론트 배포

1. https://vercel.com/new → Import `speeno/RAG_CHATBOT` → **Root Directory = `frontend`**, Framework Preset = Next.js (자동 감지).
2. Environment Variables: `NEXT_PUBLIC_API_URL = https://<svc>.onrender.com` (Production·Preview 모두 체크). **빌드 시 인라인되므로 값 변경 후에는 Redeploy 필요.**
3. Deploy → `https://<project>.vercel.app`.

## 5. CORS 마감

Render 환경변수 `CORS_ORIGINS=https://<project>.vercel.app` (커스텀 도메인 있으면 쉼표로 추가) 저장 → 자동 재배포. Preview 도메인은 `CORS_ORIGIN_REGEX`가 처리한다.

## 6. E2E 점검 체크리스트

- [ ] Vercel 페이지 첫 진입: 백엔드가 잠들어 있으면 "서버를 깨우는 중" 배너 → ~1분 내 사라짐(사이드바 상태 LIVE).
- [ ] 근거 있는 질문("환불은 며칠 이내에 신청해야 하나요?") → 스트리밍 답변 + 인용 배지 + 출처 카드.
- [ ] 근거 없는 질문 → `현재 등록된 자료에서는 해당 내용을 확인할 수 없습니다. 담당자에게 문의해주세요.` + 상담원 연결 카드.
- [ ] 👍/👎 → `GET https://<svc>.onrender.com/api/logs` 에 feedback 기록.
- [ ] `/admin/knowledge` 업로드 → 상태 폴링 `uploaded→…→indexed`, 비활성화 시 검색 제외.
- [ ] Supabase Table Editor에서 `documents/chunks/turn_logs` 행 확인.

## 7. keep-alive (적용됨: `.github/workflows/keepalive.yml`)

GitHub Actions가 **10분 간격**으로 `GET https://rag-chatbot-api-6aqk.onrender.com/api/health`를 호출해 Render 스핀다운과 Supabase 7일 정지를 함께 막는다(health가 DB를 실제 조회하므로 Supabase 활동으로 집계). 200 + `"db_ok":true`가 아니면 실패로 표시돼 GitHub 알림이 간다. 수동 실행: `gh workflow run keepalive.yml`, 확인: `gh run list --workflow keepalive.yml`.
- URL 변경은 Repository Variable `KEEPALIVE_URL`로. 리포에 60일간 커밋이 없으면 GitHub가 스케줄을 비활성화하니 Actions 탭에서 다시 Enable.
- Render free 750h/월은 워크스페이스 공유 → 상시 가동은 이 서비스 1개만(다른 free 웹서비스는 suspended 상태 유지). 필요 없으면 워크플로 파일을 삭제하면 원래대로 잠든다.

## 8. 운영 시 알아둘 것

- **콜드스타트**: keep-alive 없이는 첫 요청 ~50초+. 프론트는 마운트 시 health를 먼저 쳐서 깨운다.
- **백그라운드 색인 중 재배포/스핀다운** → 문서가 `parsing/chunking/embedding` 상태로 남을 수 있음 → 관리 화면 "재색인"으로 복구.
- **임베딩 provider 변경** = 전체 재색인 필요(차원 불일치 시 검색 0건 → Fail-Closed).
- **메모리**: 임베딩 행렬은 청크 수 × 차원 × 4B (예: 5,000 × 1,536 → 30MB). 512MB 내 충분.
- **Supabase 정지 시** 대시보드에서 Restore(수동). 무료 플랜은 백업 없음 → 중요 문서 원본은 별도 보관.
- **비용**: 호스팅 3종은 무료지만 LLM/임베딩 API는 과금된다.
- **롤백**: `DATABASE_URL`을 비우면 즉시 SQLite(로컬)로 돌아간다. 코드 경로는 동일(`app/core/db.py`의 `build_database`).
