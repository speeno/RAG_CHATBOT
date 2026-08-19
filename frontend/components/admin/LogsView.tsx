"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, type ConversationOut, type LogsQuery, type TurnLog } from "@/lib/api";
import { Icon } from "@/components/Icon";

type Range = "7d" | "30d" | "all" | "custom";
const PAGE_SIZES = [10, 20, 50];

const isoDate = (d: Date) => d.toISOString().slice(0, 10);
const fmtTime = (s: string) => {
  const d = new Date(s);
  return isNaN(d.getTime()) ? s : d.toLocaleString("ko-KR", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
};
const fmtSec = (ms: number | null | undefined) => (ms === null || ms === undefined ? "-" : `${(ms / 1000).toFixed(1)}초`);

function rangeDates(r: Range, from: string, to: string): { date_from?: string; date_to?: string } {
  const today = new Date();
  if (r === "all") return {};
  if (r === "custom") return { date_from: from || undefined, date_to: to || undefined };
  const days = r === "7d" ? 6 : 29;
  const start = new Date(today);
  start.setDate(today.getDate() - days);
  return { date_from: isoDate(start), date_to: isoDate(today) };
}

export function LogsView() {
  const [range, setRange] = useState<Range>("all");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [feedback, setFeedback] = useState<"" | "positive" | "negative" | "none">("");
  const [answerable, setAnswerable] = useState<"" | "true" | "false">("");
  const [q, setQ] = useState("");
  const [qInput, setQInput] = useState("");
  const [pageSize, setPageSize] = useState(10);
  const [page, setPage] = useState(0);
  const [items, setItems] = useState<TurnLog[] | null>(null);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<TurnLog | null>(null);
  const [conv, setConv] = useState<ConversationOut | null>(null);
  const [showConv, setShowConv] = useState(false);
  const reqSeq = useRef(0); // 필터를 빠르게 바꿀 때 늦게 도착한 이전 응답이 최신 결과를 덮어쓰지 않도록
  const convRef = useRef<HTMLDivElement>(null);

  const query: LogsQuery = useMemo(
    () => ({
      ...rangeDates(range, from, to),
      feedback: feedback || undefined,
      answerable: answerable === "" ? undefined : answerable === "true",
      q: q || undefined,
      limit: pageSize,
      offset: page * pageSize,
    }),
    [range, from, to, feedback, answerable, q, pageSize, page],
  );

  const load = useCallback(async () => {
    const seq = ++reqSeq.current;
    try {
      const r = await api.listLogs(query);
      if (seq !== reqSeq.current) return; // stale
      setItems(r.items);
      setTotal(r.total);
      setError(null);
      setSelected((prev) => (prev && r.items.find((x) => x.message_id === prev.message_id)) || r.items[0] || null);
    } catch (e) {
      if (seq !== reqSeq.current) return;
      setError(`로그를 불러오지 못했습니다: ${(e as Error).message}`);
    }
  }, [query]);

  useEffect(() => {
    load();
  }, [load]);

  // 미답변 분석 → "상담 로그에서 보기"(?q=질문)로 넘어온 경우 검색어 프리필
  useEffect(() => {
    const initial = new URLSearchParams(window.location.search).get("q");
    if (initial) { setQInput(initial); setQ(initial); }
  }, []);

  useEffect(() => {
    setConv(null);
    setShowConv(false);
  }, [selected?.conversation_id]);

  useEffect(() => {
    if (showConv && conv) convRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [showConv, conv]);

  const openConv = async () => {
    if (!selected) return;
    if (!conv) {
      try {
        setConv(await api.getConversation(selected.conversation_id));
      } catch (e) {
        setError(`대화를 불러오지 못했습니다: ${(e as Error).message}`);
        return;
      }
    }
    setShowConv((v) => !v);
  };

  const resetFilters = () => {
    setRange("all"); setFrom(""); setTo(""); setFeedback(""); setAnswerable(""); setQ(""); setQInput(""); setPage(0);
  };
  const applySearch = () => { setQ(qInput.trim()); setPage(0); };
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const pageNums = useMemo(() => {
    const out: number[] = [];
    const start = Math.max(0, Math.min(page - 2, pages - 5));
    for (let i = start; i < Math.min(pages, start + 5); i++) out.push(i);
    return out;
  }, [page, pages]);

  const fbBadge = (l: TurnLog) =>
    l.feedback === "positive" ? <span className="badge green"><Icon name="thumbs-up" /> 도움이 됐어요</span>
      : l.feedback === "negative" ? <span className="badge red"><Icon name="thumbs-down" /> 도움이 안 돼요</span>
      : <span className="muted">-</span>;
  const stBadge = (l: TurnLog) =>
    l.answerable ? <span className="badge green">성공</span> : <span className="badge orange">미답변</span>;

  return (
    <>
      <div className="kb-head">
        <div>
          <h1 className="page-title">상담 로그</h1>
          <p className="page-sub">사용자 상담 내역과 응답 품질을 확인하고 관리할 수 있습니다. 모든 턴은 질문·재작성 쿼리·검색 문서·점수·답변·응답 시간·피드백과 함께 기록됩니다.</p>
        </div>
        <div className="st-headbtns">
          <button className="btn" onClick={() => api.downloadLogsCsv({ ...query, limit: undefined, offset: undefined }).catch((e) => setError(`CSV 내보내기 실패: ${(e as Error).message}`))}><Icon name="file-text" /> 내보내기(CSV)</button>
          <button className="btn" onClick={load}><Icon name="refresh" /> 새로고침</button>
        </div>
      </div>

      {error && <div className="alert error" style={{ marginBottom: 14 }}><Icon name="alert-circle" /> {error}</div>}

      <div className="card lg-filters">
        <div className="lg-filter">
          <span className="field-label">기간</span>
          <div className="seg">
            {([["7d", "최근 7일"], ["30d", "최근 30일"], ["all", "전체"], ["custom", "직접 지정"]] as [Range, string][]).map(([k, label]) => (
              <button key={k} className={range === k ? "on" : ""} onClick={() => { setRange(k); setPage(0); }}>{label}</button>
            ))}
          </div>
          {range === "custom" && (
            <div className="lg-dates">
              <input className="input" type="date" value={from} onChange={(e) => { setFrom(e.target.value); setPage(0); }} />
              <span className="muted">~</span>
              <input className="input" type="date" value={to} onChange={(e) => { setTo(e.target.value); setPage(0); }} />
            </div>
          )}
        </div>
        <div className="lg-filter">
          <span className="field-label">응답 상태</span>
          <select className="input" value={answerable} onChange={(e) => { setAnswerable(e.target.value as typeof answerable); setPage(0); }}>
            <option value="">전체</option><option value="true">성공</option><option value="false">미답변(Fail-Closed)</option>
          </select>
        </div>
        <div className="lg-filter">
          <span className="field-label">피드백</span>
          <select className="input" value={feedback} onChange={(e) => { setFeedback(e.target.value as typeof feedback); setPage(0); }}>
            <option value="">전체</option><option value="positive">도움이 됐어요</option><option value="negative">도움이 안 돼요</option><option value="none">피드백 없음</option>
          </select>
        </div>
        <div className="lg-filter grow">
          <span className="field-label">검색</span>
          <div className="lg-search">
            <input className="input" placeholder="사용자 질문 또는 답변 내용으로 검색" value={qInput} onChange={(e) => setQInput(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && !e.nativeEvent.isComposing) applySearch(); }} />
            <button className="btn" onClick={applySearch}><Icon name="search" /> 검색</button>
          </div>
        </div>
        <div className="lg-filter end">
          <button className="btn sm" onClick={resetFilters}><Icon name="rotate-ccw" /> 필터 초기화</button>
        </div>
      </div>

      <div className="lg-grid">
        <section className="card lg-list">
          <div className="lg-list-head">
            <b>전체 {total.toLocaleString()}건</b>
            <span className="muted" style={{ fontSize: 12.5 }}>{total > 0 ? `${page * pageSize + 1}–${Math.min(total, (page + 1) * pageSize)} 표시` : ""}</span>
          </div>
          <div className="table-wrap">
            <table className="table lg-table">
              <thead>
                <tr><th>시간</th><th>사용자 질문</th><th>재작성 쿼리</th><th>응답 상태</th><th>피드백</th><th className="num">응답 시간</th></tr>
              </thead>
              <tbody>
                {items === null && <tr><td colSpan={6}><div className="empty-state"><span className="spinner" /> 불러오는 중…</div></td></tr>}
                {items !== null && items.length === 0 && <tr><td colSpan={6}><div className="empty-state">조건에 맞는 상담 로그가 없습니다.</div></td></tr>}
                {items?.map((l) => (
                  <tr key={l.id} className={selected?.message_id === l.message_id ? "selected" : ""} onClick={() => setSelected(l)} style={{ cursor: "pointer" }}>
                    <td className="time">{fmtTime(l.created_at)}</td>
                    <td className="q" title={l.user_query}>{l.user_query}</td>
                    <td className="rq" title={l.rewritten_query ?? ""}>{l.rewritten_query ? l.rewritten_query : <span className="muted">-</span>}</td>
                    <td>{stBadge(l)}</td>
                    <td>{fbBadge(l)}</td>
                    <td className="num">{fmtSec(l.total_ms)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="lg-pager">
            <div className="pages">
              <button className="pg" disabled={page === 0} onClick={() => setPage(0)}>«</button>
              <button className="pg" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>‹</button>
              {pageNums.map((n) => <button key={n} className={`pg ${n === page ? "on" : ""}`} onClick={() => setPage(n)}>{n + 1}</button>)}
              <button className="pg" disabled={page >= pages - 1} onClick={() => setPage((p) => p + 1)}>›</button>
              <button className="pg" disabled={page >= pages - 1} onClick={() => setPage(pages - 1)}>»</button>
            </div>
            <select className="input sm" value={pageSize} onChange={(e) => { setPageSize(Number(e.target.value)); setPage(0); }}>
              {PAGE_SIZES.map((n) => <option key={n} value={n}>{n} / 페이지</option>)}
            </select>
          </div>
        </section>

        <aside className="card lg-detail">
          <div className="lg-detail-head"><b>상담 상세 정보</b>{selected && <span className="muted" style={{ fontSize: 12 }}>{fmtTime(selected.created_at)}</span>}</div>
          {!selected ? (
            <div className="muted" style={{ fontSize: 13, marginTop: 12 }}>목록에서 로그를 선택하세요.</div>
          ) : (
            <>
              <div className="lbl">원본 질문</div>
              <div className="val strong">{selected.user_query}</div>
              <div className="lbl">재작성 쿼리</div>
              <div className="val">{selected.rewritten_query ?? <span className="muted">재작성 없음</span>}</div>
              <div className="lbl">검색된 문서 <span className="muted">총 {selected.retrieved.length}개</span></div>
              {selected.retrieved.length === 0 ? <div className="val muted">없음</div> : (
                <div className="lg-docs">
                  {selected.retrieved.map((s, i) => (
                    <div className="lg-doc" key={`${s.chunk_id}-${i}`}>
                      <div className="doc-ico"><Icon name="file-fill" /></div>
                      <div className="b">
                        <div className="t">{s.title}</div>
                        <div className="s">{s.section?.split(" > ").slice(-1)[0] ?? "-"}{s.version ? ` • v${s.version}` : ""}</div>
                      </div>
                      <div className="sc">점수 {s.score.toFixed(2)}</div>
                    </div>
                  ))}
                </div>
              )}
              <div className="lbl">최종 답변 {stBadge(selected)}</div>
              <div className="lg-answer">{selected.answer ?? <span className="muted">-</span>}</div>
              <div className="lbl">응답 시간</div>
              <div className="lg-timing">
                <span>검색 <b>{fmtSec(selected.retrieval_ms)}</b></span><span>LLM <b>{fmtSec(selected.llm_ms)}</b></span><span>전체 <b>{fmtSec(selected.total_ms)}</b></span>
              </div>
              <div className="lbl">피드백</div>
              <div className="val">{fbBadge(selected)}{selected.feedback_reason && <span className="muted" style={{ marginLeft: 8, fontSize: 12.5 }}>사유: {selected.feedback_reason}</span>}</div>
              <div className="lbl">모델</div>
              <div className="val muted" style={{ fontSize: 12.5 }}>LLM {selected.llm_provider ?? "-"} · 임베딩 {selected.embedding_provider ?? "-"}</div>
              <div className="lbl">대화 ID</div>
              <div className="val mono">{selected.conversation_id}</div>
              <button className="btn sm" style={{ marginTop: 12 }} onClick={openConv}><Icon name="chat" /> {showConv ? "대화 닫기" : "전체 대화 보기"}</button>
              {showConv && conv && (
                <div className="lg-conv" ref={convRef}>
                  {conv.messages.map((m) => (
                    <div key={m.id} className={`m ${m.role}`}>
                      <div className="who">{m.role === "user" ? "사용자" : "AI"} <span className="muted">{fmtTime(m.created_at)}</span></div>
                      <div className="body">{m.content}</div>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </aside>
      </div>
    </>
  );
}
