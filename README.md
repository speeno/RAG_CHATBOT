# AI 상담 도우미 (RAG 기반 상담 챗봇)

기업/기관의 공식 문서를 지식베이스로 삼아, 검색된 근거 안에서만 답변하고 출처를 제시하는 RAG 상담 챗봇 프로젝트입니다.
**Phase 1(MVP)** 이 구현되어 있습니다: 문서 등록(Markdown/HTML) → 구조 기반 청킹 → 임베딩 → 벡터 검색 → 근거 기반 답변(스트리밍) + 출처 + Fail-Closed + 피드백/상담 로그.

## 빠른 시작

```bash
# 1) 백엔드 (FastAPI, http://localhost:8000)
cd backend
uv venv .venv && uv pip install -e ".[dev]"     # 또는 python -m venv .venv && pip install -e ".[dev]"
cp .env.example .env                              # 키 설정 (아래 참고)
.venv/bin/python scripts/seed.py                  # 샘플 문서 3건 색인
.venv/bin/uvicorn app.main:app --reload --port 8000

# 2) 프론트엔드 (Next.js, http://localhost:3100)
cd frontend
npm install
npm run dev
```

브라우저에서 http://localhost:3100 (상담) · http://localhost:3100/admin/knowledge (지식베이스 관리) · http://localhost:8000/docs (API 문서)

### 프로바이더 / 키 설정 (`backend/.env`)

| 구성 요소 | 우선순위 (auto) | 키 |
|---|---|---|
| LLM | Anthropic `claude-opus-5` → OpenAI `gpt-4.1-mini` → **extractive**(오프라인 폴백) | `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` 또는 `OPENAI_API_KEY_FILE`(기본 `../openaikey`) |
| 임베딩 | Voyage `voyage-3` → OpenAI `text-embedding-3-small` → **hash**(로컬 n-gram 폴백) | `VOYAGE_API_KEY` / OpenAI 키 |

키가 하나도 없으면 오프라인 모드로 동작합니다(추출형 답변 + 어휘 검색). 실제 서비스 품질은 키 설정 후 확인하세요.
Fail-Closed 임계값은 프로바이더별 기본값(voyage 0.35 / openai 0.30 / hash 0.22)이며 `RETRIEVAL_SCORE_THRESHOLD`로 조정합니다.

### 테스트

```bash
cd backend && .venv/bin/python -m pytest -q     # 15 tests (오프라인 프로바이더로 실행, 키 불필요) + Postgres 테스트는 skip
TEST_DATABASE_URL=postgresql://localhost/rag_chatbot_test .venv/bin/python -m pytest -q tests/test_postgres.py  # Postgres 어댑터 검증
cd frontend && npx tsc --noEmit                  # 타입 체크
```

### 배포 (무료 티어: Vercel + Render + Supabase)

`DATABASE_URL`(Supabase Postgres Session Pooler)을 설정하면 SQLite 대신 Postgres를 사용합니다. 순서·주의사항은 **[docs/deploy.md](docs/deploy.md)**, Render 설정은 리포 루트 `render.yaml` 참고.

## 폴더 구조

```
.
├── CLAUDE.md                # Claude Code용 프로젝트 가이드
├── README.md
├── render.yaml              # Render Blueprint(백엔드 무료 티어)
├── backend/                 # FastAPI + SQLite/Postgres(문서/청크/대화/로그) — MVP RAG 백엔드
│   ├── app/
│   │   ├── main.py          # 앱 엔트리 (CORS, lifespan)
│   │   ├── api/             # routes.py(REST/SSE), schemas.py
│   │   ├── core/            # config.py(설정), db.py(SQLite), services.py(조립)
│   │   ├── ingestion/       # parser.py(MD/HTML+메타), chunker.py(구조 기반 청킹), indexer.py(색인 파이프라인)
│   │   ├── providers/       # embeddings.py(Voyage/OpenAI/local/hash), llm.py(Anthropic/OpenAI/extractive)
│   │   └── rag/             # retriever.py(VectorStore+Retriever), orchestrator.py(검색→Fail-Closed→LLM→출처)
│   ├── sample_docs/         # 환불/배송/주문취소 샘플 문서 (md, html)
│   ├── scripts/seed.py      # 샘플 문서 색인
│   └── tests/               # pytest (ingestion, API e2e)
├── frontend/                # Next.js 15 (App Router) + TypeScript
│   ├── app/                 # / (상담), /admin/knowledge (지식베이스), globals.css(디자인 토큰)
│   ├── components/          # Sidebar, Topbar, Icon, chat/(ChatView, Messages), admin/(KnowledgeView)
│   └── lib/api.ts           # API 클라이언트 + SSE 스트림 파서
└── docs/
    ├── prd/
    │   └── rag-chatbot-prd.md   # 제품 요구사항 문서 (단일 기준 문서)
    └── design/
        ├── mockups/             # AI 생성 UI 목업 PNG (참고용, 픽셀 단위 스펙 아님)
        │   ├── user/            # 일반 사용자 화면
        │   └── admin/           # 관리자 화면
        └── html/                # 위 목업을 HTML/CSS로 재현한 정적 화면 (1586×992)
            ├── index.html       # 전체 화면 갤러리 (HTML ↔ 원본 PNG 토글)
            ├── shared.css       # 디자인 토큰 + 공용 컴포넌트
            ├── shell.js         # 사이드바/상단바/아이콘 렌더러 (window.PAGE 설정으로 구동)
            ├── assets/          # 목업에서 잘라낸 로고·아바타·일러스트
            ├── user/            # user/01-home.html … 04-feedback-negative.html
            └── admin/           # admin/01-dashboard.html … 06-unanswered-analysis.html
```

HTML 목업 보기: `docs/design/html/index.html`을 브라우저로 열거나, `cd docs/design/html && python3 -m http.server 8765` 후 http://localhost:8765/ 접속.

## 목업 목록

| 파일 | 화면 |
|---|---|
| `user/01-home.png` | 홈 — 추천 질문, 답변 + 출처 카드, 👍/👎 |
| `user/02-chat.png` | 상담하기 — 멀티턴 대화, 관련 문서 패널 |
| `user/03-chat-no-answer-handoff.png` | Fail-Closed 응답 — 상담원 연결 / 문의 접수 / 정책 보기 |
| `user/04-feedback-negative.png` | 부정 피드백 사유 선택 |
| `admin/01-dashboard.png` | 대시보드 — 질문 수, 응답률, 미답변률, 피드백 |
| `admin/02-knowledge-base-list.png` | 지식베이스 문서 목록 / 문서 정보 |
| `admin/03-document-upload-indexing.png` | 문서 업로드 + 메타데이터 + 색인 진행 상태 |
| `admin/04-search-test.png` | 검색 테스트 — Rewrite/Multi Query, Vector·BM25·Reranker 점수 |
| `admin/05-conversation-logs.png` | 상담 로그 — 원본/재작성 쿼리, 검색 문서, 피드백 |
| `admin/06-unanswered-analysis.png` | 미답변 분석 — TOP 10, 추이, 개선 추천 |

## API 요약 (backend)

| Method | Path | 설명 |
|---|---|---|
| POST | `/api/chat` | 질문 → 답변+출처 (`conversation_id`로 멀티턴) |
| POST | `/api/chat/stream` | SSE 스트리밍 (`meta → sources → delta* → done`) |
| GET | `/api/conversations/{id}` | 대화 이력 |
| POST | `/api/feedback` | 👍/👎 + 사유 |
| GET | `/api/logs` | 상담 로그 목록 — `limit/offset/date_from/date_to/answerable/feedback/q` 필터 → `{items,total}` (`/admin/logs` 화면) |
| GET | `/api/logs/{message_id}`, `/api/logs/export.csv` | 로그 상세 / 현재 필터 CSV 내보내기 |
| GET/POST | `/api/knowledge` | 문서 목록 / 등록(multipart `file` 또는 `content`, 폼 필드가 front matter보다 우선) |
| GET/PATCH/DELETE | `/api/knowledge/{id}` | 상세(원문) / 상태·메타 수정 / 삭제 |
| GET | `/api/knowledge/{id}/chunks` | 청크 목록 |
| POST | `/api/knowledge/{id}/reindex` | 재색인 |
| POST | `/api/search/test` | 검색 테스트(정규화·Rewrite·임계값 판정·정답 문서 Hit·청크) — `/admin/search-test` 화면 |
| GET | `/api/health` | 프로바이더/임계값/색인 청크 수 |

## 다음 단계 (Phase 2~)

미구현 화면 목록과 제안 순서: [docs/screens-todo.md](docs/screens-todo.md)


BM25 + Hybrid Search, LLM 기반 Query Rewrite/Multi Query, Reranker, 골든 데이터셋 기반 Retrieval 평가(Recall@5), 관리자 검색 테스트 화면, 대시보드/미답변 분석, 권한 관리, PII 마스킹.
