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

## 목업에 있으나 미구현인 것 (2026-08-20 재대조)

위 표의 "목업 10개 = 화면 10개"는 **각 목업의 주 화면** 기준이다. 목업의 사이드바 내비게이션·화면 내부 요소까지 대조하면 아래가 남아 있다.

### A. 목업 내비게이션에는 있으나 화면 자체가 없는 것

| # | 화면 | 목업 근거 | 비고 |
|---|---|---|---|
| N1 | **상담 이력** (사용자 본인 대화 목록) | user/01~04 nav `상담 이력`, user/04는 "상담 이력으로 돌아가기"로 이 화면에서 진입 | 백엔드는 `GET /api/conversations/{id}`만 있고 사용자별 대화 목록 API 없음(익명 사용자 개념 필요 — localStorage의 conversation_id 목록으로 1차 구현 가능) |
| N2 | **도움말** | user/01~04, admin nav `도움말` | 정적 안내 페이지 |
| N3 | **설정 / 시스템 설정** | admin/01 nav `설정`, admin/03 nav `시스템 설정` | 임계값·Top-K·프로바이더 등 런타임 설정 UI(현재는 env로만) |
| N4 | **카테고리 관리 / 태그 관리** | admin/03 nav 지식베이스 하위 `카테고리 관리`, `태그 관리` | 현재 카테고리는 자유 문자열, 태그는 스키마에 없음 |
| N5 | **권한 관리** | admin/03 nav 지식베이스 하위 `권한 관리` | = RBAC(§29). 문서별 접근 권한 → 검색 단계 필터 |
| N6 | **모니터링** | admin/03 nav `모니터링` | 색인 작업 큐/오류 모니터링(대시보드와 별개) |
| N7 | 홈 ↔ 상담하기 분리 | user/01(홈)과 user/02(상담하기)가 별도 화면 | 구현은 `/` 하나로 통합 — 의도적 결정. 분리하려면 `/`(홈) + `/chat` |
| N8 | 통계 | admin/02 nav `통계` | 대시보드(`/admin`)로 커버된 것으로 간주 |
| N9 | 상단 통합 검색바 | admin/02 topbar "문서명, 카테고리, 키워드 검색" | Topbar에 검색 없음. 지식베이스 목록에도 텍스트 검색 없음(상태 필터만) |

### B. 화면은 구현됐으나 목업 요소가 빠진 것

| 화면 | 빠진 요소 (목업 기준) | 현재 구현 |
|---|---|---|
| 부정 피드백 (user/04) | **전용 피드백 페이지**, 사유 **복수 선택**, 추가 의견 텍스트박스(0/500), **"상담원에게 전달" 체크**, 취소/제출 | 채팅 인라인 카드에서 사유 **단일 선택**만(`feedback_reason` 문자열 1개) |
| 문서 업로드 (admin/03) | **PDF/DOCX 지원**, 최대 100MB·**여러 파일**, 메타데이터 **보안등급/언어/태그**, **임시 저장**, 6단계 진행 시각화(**진행률 %**), **최근 업로드 작업 테이블**(진행률·처리 시간·작업자) | 지식베이스 사이드 패널: md/html/txt 단일 파일 5MB, 문서명/ID/카테고리/버전/시행일, 4단계 상태 바(％ 없음) |
| 상담 로그 (admin/05) | 필터 **카테고리/상담 채널/담당 부서**, 피드백 **"보통이에요 😐"(중립)** | 기간/응답 상태/피드백(긍·부정·없음)/검색어 — 채널·부서는 저장 데이터 없음, 중립 피드백은 백엔드 스키마에 없음 |
| 대시보드 (admin/01) | 피드백 **중립** 항목 | "피드백 없음"으로 대체 |
| 검색 테스트 (admin/04) | Reranker Score 값 | 열은 있으나 `RERANKER=llm` 활성 시에만 값 표시(기본 none) |
| 홈 (user/01) | 추천 질문 **새로고침** 버튼 | 고정 4개 |

### 제안 우선순위 (A/B 통합)
1. **N9 지식베이스 문서 검색**(반나절) + **B-상담 로그 중립 피드백은 스킵**(제품 결정: 👍/👎 2단계 유지)
2. **N1 상담 이력**(localStorage 대화 목록 + `/history` 화면, 1일)
3. **B-피드백 확장**(복수 사유+의견+상담원 전달 → `feedback_reason` JSON화, 1일)
4. **B-업로드 확장**(여러 파일, 진행률, 작업 이력 테이블; PDF는 파서 추가 필요 — pypdf ~1일)
5. **N2 도움말**(정적, 2시간) / **N3 설정 화면**(읽기 전용부터, 반나절)
6. **N4~N6**은 Phase 3 RBAC·운영 고도화와 함께

## 남은 것 (후순위 / Phase 3~4)
- ~~검색 품질(Phase 2)~~ ✅ 2026-08-20: BM25 하이브리드(가중 RRF)·Multi Query(LLM 확장, 검색 테스트 토글/`MULTI_QUERY`)·Reranker 인터페이스(`RERANKER=llm`)·골든셋 평가(`eval/golden.jsonl`+`scripts/eval_retrieval.py`, Recall@5 100%). 검색 테스트 화면 BM25 열·Multi Query 카드 채워짐(Reranker 열은 `RERANKER=llm`일 때).
- 대시보드 Retrieval 지표(Top-k Hit)를 골든셋 정기 실행과 연동(현재는 스크립트 수동 실행)
- RBAC(역할·문서별 권한), 문서 버전 관리 화면, PII 마스킹, 플로팅 챗봇 위젯(§41), 상담원 Agent-assist(§5.2)

각 화면은 `docs/design/html/admin/*.html`의 토큰/컴포넌트(`shared.css`)를 그대로 재사용해 `app/globals.css`에 옮기면 된다.
