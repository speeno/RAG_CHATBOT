"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, type StatsOverview } from "@/lib/api";
import { Icon } from "@/components/Icon";
import { BarChart, Delta, HBarList, RangePicker, StackBar, fmtN, fmtPct, fmtSecOf, mmdd, rangeParams, type RangeKey } from "./charts";

export function DashboardView() {
  const [range, setRange] = useState<RangeKey>("7d");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [data, setData] = useState<StatsOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const seq = useRef(0);

  const load = useCallback(async () => {
    const my = ++seq.current;
    setLoading(true);
    try {
      const r = await api.statsOverview({ ...rangeParams(range, from, to), tz_offset: -new Date().getTimezoneOffset() });
      if (my !== seq.current) return;
      setData(r);
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

  const k = data?.kpi;
  const d = data?.delta;
  const daysLabel = data ? `지난 ${data.range.days}일` : "지난 기간";
  const perDay = k && data ? Math.round(k.questions / Math.max(1, data.range.days)) : null;

  return (
    <>
      <div className="kb-head">
        <div>
          <h1 className="page-title">대시보드</h1>
          <p className="page-sub">AI 상담 도우미의 운영 현황을 한눈에 확인하세요. {data && <span className="muted">{data.range.from} ~ {data.range.to} (이전 기간 {data.range.prev_from} ~ {data.range.prev_to} 대비)</span>}</p>
        </div>
        <div className="st-headbtns">
          <RangePicker range={range} from={from} to={to} onChange={(r, f, t) => { setRange(r); setFrom(f); setTo(t); }} />
          <button className="btn" onClick={load} disabled={loading}>{loading ? <span className="spinner" /> : <Icon name="refresh" />} 새로고침</button>
        </div>
      </div>

      {error && <div className="alert error" style={{ marginBottom: 14 }}><Icon name="alert-circle" /> {error}</div>}

      <div className="kpis">
        <div className="card kpi">
          <div className="kico blue"><Icon name="chat" /></div>
          <div>
            <div className="lbl">질문 수 <span className="muted">(일평균 {fmtN(perDay)})</span></div>
            <div className="val">{fmtN(k?.questions)}</div>
            <Delta value={d?.questions} unit="건" baseline={daysLabel} />
          </div>
        </div>
        <div className="card kpi">
          <div className="kico green"><Icon name="check-circle" /></div>
          <div>
            <div className="lbl">응답률</div>
            <div className="val">{fmtPct(k?.answer_rate)}</div>
            <Delta value={d?.answer_rate} baseline={daysLabel} />
          </div>
        </div>
        <div className="card kpi">
          <div className="kico orange"><Icon name="help" /></div>
          <div>
            <div className="lbl">미답변률 <span className="muted">({fmtN(k?.unanswered)}건)</span></div>
            <div className="val">{fmtPct(k?.no_answer_rate)}</div>
            <Delta value={d?.no_answer_rate} goodWhenUp={false} baseline={daysLabel} />
          </div>
        </div>
        <div className="card kpi">
          <div className="kico green"><Icon name="thumbs-up" /></div>
          <div>
            <div className="lbl">긍정 피드백 <span className="muted">(피드백 {fmtN(k?.feedback_count)}건 중)</span></div>
            <div className="val">{fmtPct(k?.positive_rate)}</div>
            <Delta value={d?.positive_rate} baseline={daysLabel} />
          </div>
        </div>
        <div className="card kpi">
          <div className="kico blue"><Icon name="history" /></div>
          <div>
            <div className="lbl">평균 응답 시간 <span className="muted">(검색 {fmtSecOf(k?.avg_retrieval_ms)} · LLM {fmtSecOf(k?.avg_llm_ms)})</span></div>
            <div className="val">{k?.avg_total_ms === null || k?.avg_total_ms === undefined ? "-" : <>{(k.avg_total_ms / 1000).toFixed(1)}<small>초</small></>}</div>
            <Delta value={d?.avg_total_ms === null || d?.avg_total_ms === undefined ? null : Math.round(d.avg_total_ms / 100) / 10} unit="초" goodWhenUp={false} baseline={daysLabel} />
          </div>
        </div>
      </div>

      <div className="dash-row2">
        <section className="card panel">
          <div className="panel-head"><h3>일별 질문 수 추이</h3><span className="muted">막대에 마우스를 올리면 성공/미답변 수가 표시됩니다</span></div>
          {data ? (
            <BarChart
              data={data.daily.map((x) => ({ label: mmdd(x.date), value: x.questions, extra: `성공 ${x.answered} · 미답변 ${x.unanswered} · 👍 ${x.positive} 👎 ${x.negative}` }))}
            />
          ) : <div className="empty-state">불러오는 중…</div>}
        </section>
        <section className="card panel">
          <div className="panel-head"><h3>질문 카테고리 TOP 5</h3><span className="muted">답변에 사용된 1순위 문서의 카테고리</span></div>
          {data ? <HBarList items={data.categories.map((c) => ({ label: c.category, value: c.count, share: c.share }))} /> : <div className="empty-state">불러오는 중…</div>}
        </section>
      </div>

      <div className="dash-row3">
        <section className="card panel">
          <div className="panel-head"><h3>피드백 비율</h3><Link className="link" href="/admin/logs">전체 보기</Link></div>
          {data ? (
            <>
              <div className="fb-total">전체 질문 <b>{data.feedback.total.toLocaleString()}</b>건 중 피드백 <b>{(data.feedback.positive + data.feedback.negative).toLocaleString()}</b>건</div>
              <StackBar parts={[
                { label: "긍정", value: data.feedback.positive, color: "var(--green)" },
                { label: "부정", value: data.feedback.negative, color: "#f04a45" },
                { label: "피드백 없음", value: data.feedback.none, color: "#c9ced8" },
              ]} />
            </>
          ) : <div className="empty-state">불러오는 중…</div>}
        </section>
        <section className="card panel">
          <div className="panel-head"><h3>최근 주요 질문 <span className="muted">(상위 5)</span></h3><Link className="link" href="/admin/unanswered">미답변 분석</Link></div>
          {data && data.top_questions.length === 0 && <div className="empty-state" style={{ padding: "28px 0" }}>기간 내 질문이 없습니다.</div>}
          {data && data.top_questions.length > 0 && (
            <div className="table-wrap">
              <table className="table dash-table">
                <thead><tr><th>순위</th><th>질문</th><th>카테고리</th><th className="num">질문 수</th><th className="num">미답변률</th></tr></thead>
                <tbody>
                  {data.top_questions.map((q, i) => (
                    <tr key={q.question}>
                      <td className="rank">{i + 1}</td>
                      <td className="q" title={q.question}>{q.question}</td>
                      <td><span className="chip">{q.category}</span></td>
                      <td className="num">{q.count.toLocaleString()}</td>
                      <td className={`num ${q.unanswered_rate && q.unanswered_rate >= 50 ? "warn" : ""}`}>{fmtPct(q.unanswered_rate)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>

      {data && (
        <div className="dash-foot muted">
          대화 {fmtN(k?.conversations)}건 · 대화당 평균 {fmtN(k?.avg_turns)}턴 · Retrieval Top-k Hit 지표는 골든 데이터셋(Phase 2) 이후 제공 · 통계는 <code>turn_logs</code> 기준(KST 일자)
        </div>
      )}
    </>
  );
}
