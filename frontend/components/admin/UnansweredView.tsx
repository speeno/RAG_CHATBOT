"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, type Inquiry, type StatsUnanswered, type UnansweredItem } from "@/lib/api";
import { Icon } from "@/components/Icon";
import { BarChart, Delta, HBarList, RangePicker, fmtN, fmtPct, mmdd, rangeParams, type RangeKey } from "./charts";

const fmtTime = (s: string) => {
  const d = new Date(s);
  return isNaN(d.getTime()) ? s : d.toLocaleString("ko-KR", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
};

export function UnansweredView() {
  const [range, setRange] = useState<RangeKey>("7d");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [data, setData] = useState<StatsUnanswered | null>(null);
  const [inquiries, setInquiries] = useState<Inquiry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [noteFor, setNoteFor] = useState<string | null>(null);
  const [noteText, setNoteText] = useState("");
  const seq = useRef(0);

  const load = useCallback(async () => {
    const my = ++seq.current;
    setLoading(true);
    try {
      const [r, inq] = await Promise.all([
        api.statsUnanswered({ ...rangeParams(range, from, to), tz_offset: -new Date().getTimezoneOffset(), top_n: 10 }),
        api.listInquiries("open").catch(() => [] as Inquiry[]),
      ]);
      if (my !== seq.current) return;
      setData(r);
      setInquiries(inq);
      setError(null);
    } catch (e) {
      if (my !== seq.current) return;
      setError(`통계를 불러오지 못했습니다: ${(e as Error).message}`);
    } finally {
      if (my === seq.current) setLoading(false);
    }
  }, [range, from, to]);

  useEffect(() => {
    load();
  }, [load]);

  const setStatus = async (it: UnansweredItem, status: "open" | "resolved", note?: string | null) => {
    try {
      await api.patchUnanswered(it.key, { status, note: note === undefined ? it.note : note });
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const k = data?.kpi;
  const daysLabel = data ? `지난 ${data.range.days}일` : "지난 기간";
  const uploadHref = (q: string) => `/admin/knowledge?suggest=${encodeURIComponent(q)}`;

  return (
    <>
      <div className="kb-head">
        <div>
          <h1 className="page-title">미답변 분석</h1>
          <p className="page-sub">답변하지 못한 질문을 분석하고 개선하여 상담 품질을 높여보세요. 미답변 = 검색 점수가 임계값 미만이라 Fail-Closed로 응답한 턴입니다. {data && <span className="muted">{data.range.from} ~ {data.range.to}</span>}</p>
        </div>
        <div className="st-headbtns">
          <RangePicker range={range} from={from} to={to} onChange={(r, f, t) => { setRange(r); setFrom(f); setTo(t); }} />
          <button className="btn" onClick={load} disabled={loading}>{loading ? <span className="spinner" /> : <Icon name="refresh" />} 새로고침</button>
        </div>
      </div>

      {error && <div className="alert error" style={{ marginBottom: 14 }}><Icon name="alert-circle" /> {error}</div>}

      <div className="kpis four">
        <div className="card kpi">
          <div className="kico orange"><Icon name="help" /></div>
          <div><div className="lbl">미답변 건수</div><div className="val">{fmtN(k?.unanswered)}<small>건</small></div>
            <Delta value={k?.growth ?? null} unit="%" goodWhenUp={false} baseline={daysLabel} /></div>
        </div>
        <div className="card kpi">
          <div className="kico orange"><Icon name="line-chart" /></div>
          <div><div className="lbl">미답변 비율 <span className="muted">(전체 {fmtN(k?.questions)}건 대비)</span></div><div className="val">{fmtPct(k?.rate)}</div>
            <Delta value={k && k.rate !== null && k.rate_prev !== null ? Math.round((k.rate - k.rate_prev) * 10) / 10 : null} goodWhenUp={false} baseline={daysLabel} /></div>
        </div>
        <div className="card kpi">
          <div className="kico blue"><Icon name="message-square" /></div>
          <div><div className="lbl">고유 질문 수</div><div className="val">{fmtN(k?.distinct)}<small>개</small></div>
            <div className="trend muted">유사 질문은 하나로 묶어 집계</div></div>
        </div>
        <div className="card kpi">
          <div className="kico green"><Icon name="check-circle" /></div>
          <div><div className="lbl">처리 완료율 <span className="muted">({fmtN(k?.resolved)}건)</span></div><div className="val">{fmtPct(k?.resolved_rate)}</div>
            <div className="trend muted">미답변 중 '처리 완료' 표시 비율</div></div>
        </div>
      </div>

      <div className="dash-row2 un-row">
        <section className="card panel">
          <div className="panel-head"><h3>답변하지 못한 질문 TOP 10</h3><span className="muted">기준: 미답변 건수 · 증가율은 이전 기간 대비</span></div>
          {!data ? <div className="empty-state">불러오는 중…</div> : data.top.length === 0 ? (
            <div className="empty-state" style={{ padding: "36px 0" }}>기간 내 미답변 질문이 없습니다 🎉</div>
          ) : (
            <div className="table-wrap">
              <table className="table un-table">
                <thead><tr><th>순위</th><th>질문</th><th className="num">건수</th><th className="num">비율</th><th className="num">증가율</th><th>최고 점수</th><th>추천</th><th>상태</th><th></th></tr></thead>
                <tbody>
                  {data.top.map((it, i) => (
                    <tr key={it.key} className={it.status === "resolved" ? "resolved" : ""}>
                      <td className="rank">{i + 1}</td>
                      <td className="q">
                        <div className="qt" title={it.question}>{it.question}</div>
                        <div className="qs muted">{it.category} · 최근 {fmtTime(it.last_at)}{it.note ? ` · 메모: ${it.note}` : ""}</div>
                      </td>
                      <td className="num"><b>{it.count}</b></td>
                      <td className="num">{fmtPct(it.share)}</td>
                      <td className={`num ${it.growth !== null && it.growth > 0 ? "warn" : ""}`}>{it.growth === null ? "-" : `${it.growth > 0 ? "▲" : it.growth < 0 ? "▼" : "—"} ${Math.abs(it.growth).toFixed(1)}%`}</td>
                      <td className="num" title="검색된 문서의 최고 유사도(임계값 미만)">{it.top_score === null ? "-" : it.top_score.toFixed(3)}</td>
                      <td>
                        <Link className={`chip ${it.recommendation === "new_document" ? "rec-new" : "rec-fix"}`} href={uploadHref(it.question)} title="지식베이스로 이동">
                          {it.recommendation === "new_document" ? "새 문서 추가" : "기존 문서 보완"}
                        </Link>
                      </td>
                      <td>
                        {it.status === "resolved"
                          ? <span className="badge green">처리 완료</span>
                          : <span className="badge orange">미처리</span>}
                      </td>
                      <td className="acts-cell">
                        <div className="acts">
                          <Link className="icon-btn" href={`/admin/logs?q=${encodeURIComponent(it.question)}`} title="상담 로그에서 보기"><Icon name="user-log" /></Link>
                          <button className="icon-btn" title="메모" onClick={() => { setNoteFor(noteFor === it.key ? null : it.key); setNoteText(it.note ?? ""); }}><Icon name="file-text" /></button>
                          {it.status === "resolved"
                            ? <button className="icon-btn" title="미처리로 되돌리기" onClick={() => setStatus(it, "open")}><Icon name="rotate-ccw" /></button>
                            : <button className="icon-btn" title="처리 완료로 표시" onClick={() => setStatus(it, "resolved")}><Icon name="check-circle" /></button>}
                        </div>
                        {noteFor === it.key && (
                          <div className="note-box">
                            <input className="input" placeholder="처리 메모 (예: REFUND-002 문서 추가)" value={noteText} onChange={(e) => setNoteText(e.target.value)} />
                            <button className="btn sm primary" onClick={async () => { await setStatus(it, it.status, noteText.trim() || null); setNoteFor(null); }}>저장</button>
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <div className="un-side">
          <section className="card panel">
            <div className="panel-head"><h3>개선 추천</h3></div>
            {data && (
              <div className="recs">
                <div className="rec"><div className="rec-ico new"><Icon name="cloud-upload" /></div><div><b>새 문서 추가</b><p>관련 문서가 거의 없는 질문입니다. 문서를 추가해 답변 가능 범위를 넓히세요.</p></div><div className="rec-n">{data.recommendations.new_document}건</div></div>
                <div className="rec"><div className="rec-ico fix"><Icon name="file-text" /></div><div><b>기존 문서 보완</b><p>유사 문서는 있지만 점수가 임계값에 못 미칩니다. 해당 섹션을 보강하세요.</p></div><div className="rec-n">{data.recommendations.improve_document}건</div></div>
                <div className="rec"><div className="rec-ico faq"><Icon name="headset" /></div><div><b>상담원 FAQ 생성</b><p>2회 이상 반복된 미답변 질문입니다. 상담원용 FAQ 후보입니다.</p></div><div className="rec-n">{data.recommendations.faq_candidates}건</div></div>
                <Link className="btn sm" href="/admin/knowledge" style={{ alignSelf: "flex-start" }}><Icon name="book-open" /> 지식베이스로 이동</Link>
              </div>
            )}
          </section>
          <section className="card panel">
            <div className="panel-head"><h3>접수된 문의 <span className="muted">(미처리 {inquiries.length})</span></h3></div>
            {inquiries.length === 0 ? <div className="muted" style={{ fontSize: 13 }}>상담원 연결·문의 남기기로 접수된 건이 없습니다.</div> : (
              <div className="inq-list">
                {inquiries.slice(0, 8).map((q) => (
                  <div key={q.id} className="inq">
                    <div className="inq-h"><span className={`badge ${q.kind === "agent" ? "blue" : "gray"}`}>{q.kind === "agent" ? "상담원 연결" : "문의"}</span><span className="muted">{fmtTime(q.created_at)}</span></div>
                    <div className="inq-c">{q.content}</div>
                    <div className="inq-f"><span className="muted">{q.contact ?? "연락처 없음"}</span><button className="link" onClick={async () => { await api.patchInquiry(q.id, "done"); load(); }}>처리 완료</button></div>
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      </div>

      <div className="dash-row2">
        <section className="card panel">
          <div className="panel-head"><h3>미답변 추이</h3><span className="muted">일별</span></div>
          {data ? <BarChart data={data.daily.map((x) => ({ label: mmdd(x.date), value: x.unanswered }))} color="var(--orange)" height={200} /> : <div className="empty-state">불러오는 중…</div>}
        </section>
        <section className="card panel">
          <div className="panel-head"><h3>미답변 카테고리 분포</h3><span className="muted">가장 가까운 문서의 카테고리</span></div>
          {data ? <HBarList items={data.categories.map((c) => ({ label: c.category, value: c.count, share: c.share }))} color="var(--orange)" /> : <div className="empty-state">불러오는 중…</div>}
        </section>
      </div>
    </>
  );
}
