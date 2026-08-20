"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type DocumentItem, type SearchTestResponse, type SearchTestResult } from "@/lib/api";
import { Icon } from "@/components/Icon";

const EXAMPLES = ["환불 기간이 언제인가요?", "배송이 얼마나 걸리나요?", "주문 취소는 언제까지 가능한가요?", "교환은 어떻게 신청하나요?"];
const HISTORY_KEY = "rag.searchTest.history";
const MAX_HISTORY = 20;

type HistoryItem = { query: string; at: string; top_score: number; passes: boolean };

function loadHistory(): HistoryItem[] {
  if (typeof window === "undefined") return [];
  try {
    return JSON.parse(localStorage.getItem(HISTORY_KEY) ?? "[]") as HistoryItem[];
  } catch {
    return [];
  }
}

const fmt = (n: number | null | undefined, digits = 3) => (n === null || n === undefined ? "-" : n.toFixed(digits));

export function SearchTestView() {
  const [query, setQuery] = useState("");
  const [previousQuery, setPreviousQuery] = useState("");
  const [topK, setTopK] = useState(10);
  const [expectedDoc, setExpectedDoc] = useState("");
  const [useMultiQuery, setUseMultiQuery] = useState(false);
  const [includeInternal, setIncludeInternal] = useState(true);
  const [docs, setDocs] = useState<DocumentItem[]>([]);
  const [showSettings, setShowSettings] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [res, setRes] = useState<SearchTestResponse | null>(null);
  const [selected, setSelected] = useState<SearchTestResult | null>(null);

  useEffect(() => {
    setHistory(loadHistory());
    api.listDocuments().then((d) => setDocs(d.filter((x) => x.status === "active" && x.processing_status === "indexed"))).catch(() => setDocs([]));
  }, []);

  const run = useCallback(
    async (q?: string) => {
      const text = (q ?? query).trim();
      if (!text || busy) return;
      if (q !== undefined) setQuery(q);
      setBusy(true);
      setError(null);
      try {
        const r = await api.searchTest({
          query: text,
          top_k: topK,
          previous_query: previousQuery.trim() || null,
          expected_document_id: expectedDoc || null,
          use_multi_query: useMultiQuery,
          include_internal: includeInternal,
        });
        setRes(r);
        setSelected(r.results[0] ?? null);
        const item: HistoryItem = { query: text, at: new Date().toISOString(), top_score: r.top_score, passes: r.passes_threshold };
        const next = [item, ...loadHistory().filter((h) => h.query !== text)].slice(0, MAX_HISTORY);
        localStorage.setItem(HISTORY_KEY, JSON.stringify(next));
        setHistory(next);
      } catch (e) {
        setError(`검색에 실패했습니다: ${(e as Error).message}`);
      } finally {
        setBusy(false);
      }
    },
    [query, busy, topK, previousQuery, expectedDoc, useMultiQuery, includeInternal],
  );

  const onKey = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && !e.nativeEvent.isComposing) run();
  };

  const hitCell = (ok: boolean | undefined, label: string) => (
    <div className="col">
      <b>{label}</b>
      <div className={`v ${res?.hit ? (ok ? "ok" : "miss") : ""}`}>
        {res?.hit ? (
          <>
            <Icon name={ok ? "check-circle" : "x"} /> {ok ? "Hit" : "Miss"}
          </>
        ) : (
          <span className="muted">-</span>
        )}
      </div>
    </div>
  );

  const docLabel = useMemo(() => {
    const d = docs.find((x) => x.document_id === expectedDoc || x.id === expectedDoc);
    return d ? `${d.title} (${d.document_id})` : "";
  }, [docs, expectedDoc]);

  return (
    <>
      <div className="kb-head">
        <div>
          <h1 className="page-title">검색 테스트</h1>
          <p className="page-sub">사용자 질문에 대한 검색 과정을 테스트하고 검색 성능을 평가할 수 있습니다. 점수가 임계값 미만이면 실제 상담에서는 Fail-Closed로 답변하지 않습니다.</p>
        </div>
        <div className="st-headbtns">
          <button className={`btn ${showHistory ? "on" : ""}`} onClick={() => { setShowHistory((v) => !v); setShowSettings(false); }}><Icon name="history" /> 검색 기록{history.length ? ` (${history.length})` : ""}</button>
          <button className={`btn ${showSettings ? "on" : ""}`} onClick={() => { setShowSettings((v) => !v); setShowHistory(false); }}><Icon name="settings" /> 설정</button>
        </div>
      </div>

      {error && <div className="alert error" style={{ marginBottom: 14 }}><Icon name="alert-circle" /> {error}</div>}

      {showHistory && (
        <div className="card st-panel">
          <div className="st-panel-head"><b>최근 검색 기록</b>{history.length > 0 && <button className="btn sm" onClick={() => { localStorage.removeItem(HISTORY_KEY); setHistory([]); }}><Icon name="trash" /> 비우기</button>}</div>
          {history.length === 0 ? <div className="muted" style={{ fontSize: 13 }}>아직 검색 기록이 없습니다.</div> : (
            <div className="st-history">
              {history.map((h) => (
                <button key={h.at} className="st-hist-item" onClick={() => { setShowHistory(false); run(h.query); }}>
                  <span className={`dot ${h.passes ? "ok" : "miss"}`} />
                  <span className="q">{h.query}</span>
                  <span className="meta">{fmt(h.top_score)} · {new Date(h.at).toLocaleString("ko-KR", { month: "numeric", day: "numeric", hour: "numeric", minute: "2-digit" })}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {showSettings && (
        <div className="card st-panel">
          <div className="st-panel-head"><b>검색 설정</b><span className="muted" style={{ fontSize: 12.5 }}>임계값은 서버 설정(RETRIEVAL_SCORE_THRESHOLD)을 따릅니다.</span></div>
          <div className="st-settings">
            <label>
              <span className="field-label">Top-K</span>
              <input className="input" type="number" min={1} max={50} value={topK} onChange={(e) => setTopK(Math.min(50, Math.max(1, Number(e.target.value) || 1)))} />
            </label>
            <label>
              <span className="field-label">직전 사용자 질문 <small className="muted">(후속 질문 Rewrite 시뮬레이션)</small></span>
              <input className="input" placeholder="예) 배송은 며칠 걸리나요?" value={previousQuery} onChange={(e) => setPreviousQuery(e.target.value)} />
            </label>
            <label className="st-check">
              <span className="field-label">Multi Query <small className="muted">(LLM 쿼리 확장 + RRF union)</small></span>
              <label className="st-toggle"><input type="checkbox" checked={useMultiQuery} onChange={(e) => setUseMultiQuery(e.target.checked)} /> 사용</label>
            </label>
            <label className="st-check">
              <span className="field-label">내부 문서 <small className="muted">(access: internal)</small></span>
              <label className="st-toggle"><input type="checkbox" checked={includeInternal} onChange={(e) => setIncludeInternal(e.target.checked)} /> 포함</label>
            </label>
            <label>
              <span className="field-label">정답 문서 <small className="muted">(Top-1/3/5 Hit 계산)</small></span>
              <select className="input" value={expectedDoc} onChange={(e) => setExpectedDoc(e.target.value)}>
                <option value="">선택 안 함</option>
                {docs.map((d) => <option key={d.id} value={d.document_id}>{d.title} ({d.document_id})</option>)}
              </select>
            </label>
          </div>
        </div>
      )}

      <div className="st-row1">
        <section className="card st-qcard">
          <div className="lbl">질문 (Query)</div>
          <div className="st-qrow">
            <div className="st-qinput">
              <input value={query} placeholder="테스트할 질문을 입력하세요" onChange={(e) => setQuery(e.target.value)} onKeyDown={onKey} />
              {query && <button className="icon-btn" title="지우기" onClick={() => setQuery("")}><Icon name="x" /></button>}
            </div>
            <button className="btn primary" disabled={!query.trim() || busy} onClick={() => run()}>
              {busy ? <span className="spinner" style={{ borderTopColor: "#fff", borderColor: "rgba(255,255,255,.4)" }} /> : <Icon name="search" />} 검색 실행
            </button>
          </div>
          <div className="st-examples">
            <span className="muted">예시:</span>
            {EXAMPLES.map((q) => <button key={q} className="st-ex" onClick={() => run(q)}>{q}</button>)}
          </div>
        </section>

        <section className="card st-stats">
          <div className="cols">
            {hitCell(res?.hit?.top1, "Top-1 Hit")}
            {hitCell(res?.hit?.top3, "Top-3 Hit")}
            {hitCell(res?.hit?.top5, "Top-5 Hit")}
          </div>
          <div className="crit">
            <Icon name="info" />
            {res?.hit
              ? <>정답 문서 <b>{docLabel || expectedDoc}</b>{res.hit.rank ? ` — ${res.hit.rank}위에서 발견` : " — 결과에 없음"}</>
              : <>평가 기준: 정답 문서 포함 여부 · <button className="link" onClick={() => { setShowSettings(true); setShowHistory(false); }}>설정에서 정답 문서 선택</button></>}
          </div>
        </section>
      </div>

      {res && (
        <div className={`alert ${res.passes_threshold ? "ok" : "warn"} st-verdict`}>
          <Icon name={res.passes_threshold ? "check-circle" : "alert-circle"} />
          <span>
            {res.passes_threshold
              ? <>최고 점수 <b>{fmt(res.top_score)}</b> ≥ 임계값 <b>{fmt(res.threshold, 2)}</b> → 실제 상담에서는 LLM이 답변을 생성합니다.</>
              : <>최고 점수 <b>{fmt(res.top_score)}</b> &lt; 임계값 <b>{fmt(res.threshold, 2)}</b> → <b>Fail-Closed</b>: 실제 상담에서는 답변하지 않고 담당자 안내를 보냅니다. 관련 문서를 추가하거나 임계값을 조정하세요.</>}
          </span>
          <span className="meta">임베딩 {res.embedding_provider} · 색인 청크 {res.indexed_chunks} · 검색 {res.elapsed_ms}ms</span>
        </div>
      )}

      <div className="st-row2">
        <div className="st-lcol">
          <section className="card st-lcard">
            <div className="t">질문 정규화 <small>(Query Normalization)</small></div>
            <div className="gbox">{res ? res.normalized_query : <span className="muted">검색을 실행하면 표시됩니다.</span>}</div>
          </section>
          <section className="card st-lcard">
            <div className="t">Rewrite Query</div>
            <div className="gbox">
              {!res ? <span className="muted">-</span> : res.rewritten_query
                ? <>{res.rewritten_query}<div className="note">직전 질문을 덧붙여 검색했습니다.</div></>
                : <span className="muted">재작성 없음 — 원문 그대로 검색{previousQuery ? " (후속 질문 패턴 아님)" : ""}</span>}
            </div>
          </section>
          <section className="card st-lcard">
            <div className="t">Multi Query 후보 <small>(자동 생성)</small></div>
            {res && res.multi_queries.length > 0 ? (
              <ol className="mq">{res.multi_queries.map((q, i) => <li key={i}><span>{i + 1}</span><span>{q}</span></li>)}</ol>
            ) : (
              <div className="gbox"><span className="muted">{useMultiQuery ? "생성된 확장 쿼리가 없습니다(오프라인 LLM이거나 생성 실패)." : "설정에서 Multi Query를 켜면 LLM이 확장 쿼리를 생성해 함께 검색합니다."}</span></div>
            )}
          </section>
        </div>

        <section className="card st-ccard">
          <div className="t">검색 결과 <small>(Retrieved Results)</small></div>
          {!res ? (
            <div className="empty-state">질문을 입력하고 검색을 실행하세요.</div>
          ) : res.results.length === 0 ? (
            <div className="empty-state">검색 결과가 없습니다. 활성·색인 완료 문서가 있는지 확인하세요 (색인 청크 {res.indexed_chunks}개).</div>
          ) : (
            <div className="table-wrap">
              <table className="st-rt">
                <thead>
                  <tr>
                    <th>순위</th><th>문서명</th><th>섹션</th><th className="num" title="임베딩 코사인 유사도">Vector</th><th className="num" title="Phase 2: BM25(키워드) 점수">BM25</th><th className="num" title="Phase 2: Reranker 점수">Reranker</th>
                  </tr>
                </thead>
                <tbody>
                  {res.results.map((r) => (
                    <tr key={r.chunk_id} className={`${selected?.chunk_id === r.chunk_id ? "sel" : ""} ${r.passes_threshold ? "" : "below"}`} onClick={() => setSelected(r)}>
                      <td className="rd"><span className={`radio ${selected?.chunk_id === r.chunk_id ? "on" : ""}`} />{r.rank}</td>
                      <td className="doc"><span className="doc-in"><span className="doc-title" title={r.title}>{r.title}</span>{r.category && <span className="chip">{r.category}</span>}</span></td>
                      <td className="sec" title={r.section ?? ""}>{r.section?.split(" > ").slice(-1)[0] ?? "-"}</td>
                      <td className="num"><span className={r.passes_threshold ? "score ok" : "score miss"}>{fmt(r.score)}</span></td>
                      <td className="num muted">{fmt(r.bm25_score, 2)}</td>
                      <td className="num muted">{fmt(r.rerank_score)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {res && res.results.length > 0 && (
            <div className="st-cfoot">
              <span>색인 청크 {res.indexed_chunks}개 중 {res.results.length}개 표시 (검색 시간: {res.elapsed_ms}ms) · <span className="score miss" style={{ fontWeight: 600 }}>회색</span> 행은 임계값 미만</span>
              <button className="link" onClick={() => {
                const blob = new Blob([JSON.stringify(res, null, 2)], { type: "application/json" });
                const a = document.createElement("a");
                a.href = URL.createObjectURL(blob);
                a.download = `search-test-${Date.now()}.json`;
                a.click();
                URL.revokeObjectURL(a.href);
              }}><Icon name="file-text" /> 결과 다운로드(JSON)</button>
            </div>
          )}
        </section>

        <section className="card st-rcard">
          <div className="rh"><b>선택된 청크/컨텍스트 미리보기</b></div>
          {!selected ? (
            <div className="muted" style={{ fontSize: 13, marginTop: 14 }}>결과 행을 선택하면 청크 내용이 표시됩니다.</div>
          ) : (
            <>
              <div className="lbl">문서명</div>
              <div className="val">{selected.title}</div>
              <div className="lbl">섹션</div>
              <div className="val">{selected.section ?? "-"}</div>
              <div className="lbl">출처</div>
              <div className="src">
                <div className="doc-ico"><Icon name="file-fill" /></div>
                <div>
                  <div className="n">{selected.document_id}</div>
                  <div className="s">{selected.category ?? "-"}{selected.version ? ` • v${selected.version}` : ""}</div>
                </div>
                <div className="d">{selected.updated_at ? `업데이트: ${selected.updated_at}` : ""}</div>
              </div>
              <div className="lbl">점수</div>
              <div className="val">
                <span className={selected.passes_threshold ? "score ok" : "score miss"}>{fmt(selected.score)}</span>
                <span className="muted" style={{ fontSize: 12.5 }}> / 임계값 {fmt(res?.threshold ?? 0, 2)} · {selected.rank}위 · {selected.chunk_id}</span>
              </div>
              <div className="lbl">청크 내용 ({selected.content.length}자)</div>
              <div className="chunk"><pre>{selected.content}</pre></div>
            </>
          )}
        </section>
      </div>
    </>
  );
}
