# 미구현 화면 목록 (2026-08-20 갱신)

목업 10개(`docs/design/mockups`, `docs/design/html`) 와 PRD(§32~§36, §41~§43, §52~§53)를 현재 `frontend/`·`backend/` 구현과 대조한 결과다. 배포된 서비스: https://rag-chatbot-ten-cyan.vercel.app

## 한눈에 보기

| # | 화면 | 목업 | PRD | Phase | 프론트 | 백엔드 API | 상태 |
|---|---|---|---|---|---|---|---|
| U1 | 홈(추천 질문·출처·👍/👎) | `user/01-home` | §36, §42 | 1 | `/` ChatView | `/api/chat/stream`, `/api/feedback` | ✅ 완료 |
| U2 | 상담하기(멀티턴·관련 문서 패널) | `user/02-chat` | §6 | 1 | `/` | `/api/chat/stream`, `/api/conversations/{id}` | ✅ 완료 |
| U3 | Fail-Closed 핸드오프 | `user/03-chat-no-answer-handoff` | §24, §43 | 1 | `Messages.tsx` handoff 카드 + 문의 폼 | `POST /api/inquiries` (`NEXT_PUBLIC_HANDOFF_URL` 설정 시 상담원 연결은 외부 URL) | ✅ 완료(2026-08-20) |
| U4 | 부정 피드백 사유 선택 | `user/04-feedback-negative` | §36 | 1 | `Messages.tsx` | `/api/feedback` | ✅ 완료 |
| A1 | 대시보드 | `admin/01-dashboard` | §34 | 3 | `/admin` DashboardView | `GET /api/stats/overview` | ✅ 완료(2026-08-20) — Top-k Hit 지표는 골든셋(Phase 2) 이후 |
| A2 | 지식베이스 목록/문서 정보 | `admin/02-knowledge-base-list` | §30~31 | 1 | `/admin/knowledge` | `/api/knowledge*` | ✅ 완료 |
| A3 | 문서 업로드·색인 진행 | `admin/03-document-upload-indexing` | §30 | 1 | `/admin/knowledge` | `/api/knowledge` POST·폴링 | ✅ 완료 |
| A4 | 검색 테스트 | `admin/04-search-test` | §32 | 2 | `/admin/search-test` SearchTestView | `POST /api/search/test`(정규화·Rewrite·임계값·Hit) | ✅ 완료(2026-08-20) — BM25/Reranker 열은 Phase 2 후 채움 |
| A5 | 상담 로그 | `admin/05-conversation-logs` | §33 | 3 | `/admin/logs` LogsView | `GET /api/logs`(필터·페이징), `/api/logs/{message_id}`, `/api/logs/export.csv` | ✅ 완료(2026-08-20) |
| A6 | 미답변 분석 | `admin/06-unanswered-analysis` | §35 | 3 | `/admin/unanswered` UnansweredView | `GET /api/stats/unanswered`, `PATCH /api/stats/unanswered/{key}`, `/api/inquiries` | ✅ 완료(2026-08-20) |
| — | 플로팅 챗봇 위젯 | (목업 없음) | §41 | 선택 | ❌ | — | ⚪ 미구현(선택) |
| — | 관리자 인증 | (목업 없음) | §29 1단계 | 3 | `/admin/*` AdminGate(토큰 로그인) | `ADMIN_TOKEN` + `GET /api/admin/me`, 관리자 라우터 401 | ✅ 완료(2026-08-20) — 단일 토큰; 역할/문서별 권한(RBAC)은 미구현 |
| — | 문서 버전 관리 / RBAC(역할·문서별 권한) | (목업 없음) | §29, Phase 3 | 3 | ❌ | ❌ | ⚪ 미구현(화면 설계 필요) |

사이드바(`components/Sidebar.tsx`): `상담하기` / 관리자 `대시보드`, `지식베이스`, `검색 테스트`, `상담 로그`, `미답변 분석` — 목업 10개 화면 모두 구현됨.

---

## 미구현 화면 상세

### A4. 검색 테스트 — `/admin/search-test` ✅ 구현 완료 (2026-08-20)
목업 `admin/04-search-test.png` · PRD §32. 구현: `frontend/components/admin/SearchTestView.tsx`, API `POST /api/search/test`(normalized/rewritten/search_query, threshold·passes_threshold·top_score, hit{top1,3,5,rank}, results[rank,score,passes_threshold,bm25_score,rerank_score,content]). 남은 것: BM25/Reranker 점수·Multi Query 후보(Phase 2 하이브리드 검색 후).

화면 요소(목업 기준):
- 질문 입력 + [검색 실행], 예시 질문 칩, 최근 검색 기록, 설정(Top-K·임계값)
- 질문 정규화 / Rewrite Query / Multi Query 후보 목록 (Phase 2 기능 — 현재는 orchestrator의 단순 rewrite만 존재)
- 검색 결과 표: 순위 · 문서명 · 섹션 · **Vector Score · BM25 Score · Reranker Score** (현재 API는 Vector score만 → BM25/Reranker 열은 Phase 2 하이브리드 검색 도입 후 채움, 그 전까지는 "-")
- Top-1/3/5 Hit 지표(정답 문서 지정 시), 선택 청크/컨텍스트 미리보기, 임계값(Fail-Closed 기준선) 표시, 결과 다운로드
- 검색 시간(ms)

백엔드 보강: `POST /api/search/test`에 `rewritten_query`, `threshold` 대비 pass 여부, (Phase 2) `bm25_score`/`rerank_score` 필드 추가.

### A5. 상담 로그 — `/admin/logs` ✅ 구현 완료 (2026-08-20)
목업 `admin/05-conversation-logs.png` · PRD §33. 구현: `frontend/components/admin/LogsView.tsx`, API `GET /api/logs?limit&offset&date_from&date_to&answerable&feedback&q` → `{items,total,limit,offset}`, `GET /api/logs/{message_id}`, `GET /api/logs/export.csv`(UTF-8 BOM, 최대 5,000건). 목업의 카테고리/채널/담당부서 필터는 데이터가 없어 생략.

화면 요소:
- 필터: 기간, 피드백 상태(긍정/부정/없음), 응답 상태(성공/미답변), 질문 검색어 (목업의 카테고리·채널·담당부서는 데이터 없음 → 생략 또는 문서 카테고리로 대체)
- 목록 표: 시간 · 사용자 질문 · 재작성 쿼리 · 응답 상태 · 피드백 · 응답 시간, 페이지네이션(10/페이지), 내보내기(CSV)
- 상세 패널: 원본/재작성 질문, 검색된 문서(점수), 최종 답변, 응답 시간 분해(검색/LLM/전체), 피드백 사유, 같은 `conversation_id`의 전체 대화 보기

백엔드 보강: `GET /api/logs`에 `offset`, `from/to`, `answerable`, `feedback`, `q` 필터 + `total` 반환; `GET /api/logs/export.csv`.

### A1. 대시보드 — `/admin` ✅ 구현 완료 (2026-08-20)
목업 `admin/01-dashboard.png` · PRD §34. 구현: `DashboardView.tsx` + `components/admin/charts.tsx`(SVG 막대/가로막대/스택), API `GET /api/stats/overview?date_from&date_to&tz_offset`(`app/core/stats.py`: KPI+이전 기간 대비 delta, 일별, 카테고리 TOP5, 피드백 비율, 주요 질문 TOP5).

화면 요소:
- 기간 선택(기본 최근 7일) + 지난 기간 대비 증감
- KPI 카드: 일일 질문 수, 응답률(Answer Rate), 미답변률, 긍정 피드백률, 평균 응답 시간
- 일별 질문 수 추이(막대/선), 질문 카테고리 TOP 5(검색된 문서 카테고리 기준), 피드백 비율(긍정/부정/없음), 최근 주요 질문 TOP 5(질문 수·미답변률)
- PRD §34의 Retrieval 지표(Top-1/3/5 Hit)·성능 지표(검색/LLM/전체 평균 시간)는 `turn_logs`의 `retrieval_ms`/`llm_ms`/`total_ms`로 계산 가능, Hit 지표는 골든셋(Phase 2) 이후

백엔드 보강: `GET /api/stats/overview?from&to`(KPI+증감), `GET /api/stats/daily`, `GET /api/stats/top-questions`, `GET /api/stats/categories` — 모두 `turn_logs`(+`messages`, `documents`) 집계 SQL.

### A6. 미답변 분석 — `/admin/unanswered` ✅ 구현 완료 (2026-08-20)
목업 `admin/06-unanswered-analysis.png` · PRD §35. 구현: `UnansweredView.tsx`, API `GET /api/stats/unanswered`(TOP N·증가율·최고 점수·추천(new_document/improve_document)·처리 상태), `PATCH /api/stats/unanswered/{key}`(`unanswered_reviews` 테이블), 접수된 문의(`GET/PATCH /api/inquiries`). TOP 항목에서 지식베이스(`?suggest=`)·상담 로그(`?q=`)로 이동.

화면 요소:
- KPI: 미답변 건수, 미답변 비율, 최근 증가율, 처리 완료율
- 답변하지 못한 질문 TOP 10(건수·비율·증가율) — 유사 질문 묶기(초기엔 정규화 문자열 기준, 이후 임베딩 클러스터링)
- 미답변 추이(일별), 미답변 카테고리 분포
- 개선 추천: 새 문서 추가 / 기존 문서 보완 / 상담원 FAQ 생성 → 각 항목에서 **지식베이스 업로드 화면으로 이동**(질문을 메타데이터로 전달)
- 처리 상태(미처리/처리 완료) 표시 → `turn_logs` 또는 별도 `unanswered_reviews` 테이블 필요

백엔드 보강: `GET /api/stats/unanswered?from&to`(TOP N·추이·분포), `PATCH /api/unanswered/{key}`(처리 상태).

### U3. Fail-Closed 핸드오프 버튼 ✅ 구현 완료 (2026-08-20)
`Messages.tsx`: 문의 남기기/상담원 연결 → 인라인 폼(연락처 선택, 내용에 질문 프리필) → `POST /api/inquiries`(conversation_id·message_id·kind 저장). `NEXT_PUBLIC_HANDOFF_URL` 설정 시 상담원 연결은 외부 채널을 새 창으로 연다. 접수 건은 미답변 분석 화면에서 처리.

### 선택/후순위
- **플로팅 챗봇 위젯**(PRD §41): 외부 사이트 임베드용 우측 하단 버튼 + 미니 채팅 패널. 별도 목업 없음.
- **문서 버전 관리 화면**(Phase 3): 같은 `document_id`의 버전 목록·비교·롤백. 현재는 `version` 메타만 저장.
- **권한 관리(RBAC)**(PRD §29, Phase 3): 관리자 로그인·역할, 문서별 접근 권한 → 검색 단계 필터. 현재 관리자 화면은 인증 없음(배포 시 주의).
- **상담원(Agent-assist) 화면**(PRD §5.2, Phase 4): 상담 중 관련 정보 검색·답변 추천·근거 확인·이력 확인.

---

## 구현 순서 (완료)
1. ~~A4 검색 테스트~~ ✅ 2. ~~A5 상담 로그~~ ✅ 3. ~~A1 대시보드~~ ✅ 4. ~~A6 미답변 분석~~ ✅ 5. ~~U3 핸드오프 버튼~~ ✅ 6. ~~관리자 인증(단일 토큰)~~ ✅

## 남은 것 (후순위 / Phase 3~4)
- ~~검색 품질(Phase 2)~~ ✅ 2026-08-20: BM25 하이브리드(가중 RRF)·Multi Query(LLM 확장, 검색 테스트 토글/`MULTI_QUERY`)·Reranker 인터페이스(`RERANKER=llm`)·골든셋 평가(`eval/golden.jsonl`+`scripts/eval_retrieval.py`, Recall@5 100%). 검색 테스트 화면 BM25 열·Multi Query 카드 채워짐(Reranker 열은 `RERANKER=llm`일 때).
- 대시보드 Retrieval 지표(Top-k Hit)를 골든셋 정기 실행과 연동(현재는 스크립트 수동 실행)
- RBAC(역할·문서별 권한), 문서 버전 관리 화면, PII 마스킹, 플로팅 챗봇 위젯(§41), 상담원 Agent-assist(§5.2)

각 화면은 `docs/design/html/admin/*.html`의 토큰/컴포넌트(`shared.css`)를 그대로 재사용해 `app/globals.css`에 옮기면 된다.
