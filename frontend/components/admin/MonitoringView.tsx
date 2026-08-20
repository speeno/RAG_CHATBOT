"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, type Monitoring } from "@/lib/api";
import { Icon } from "@/components/Icon";

const STEP_PCT: Record<string, number> = { uploaded: 10, parsing: 35, chunking: 55, embedding: 80, indexed: 100, error: 0 };
const fmtTime = (s: string | null) => {
  if (!s) return "-";
  const d = new Date(s);
  return isNaN(d.getTime()) ? s : d.toLocaleString("ko-KR", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
};
const fmtUptime = (s: number) => {
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60);
  return d > 0 ? `${d}일 ${h}시간` : h > 0 ? `${h}시간 ${m}분` : `${m}분`;
};

export function MonitoringView() {
  const [data, setData] = useState<Monitoring | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [auto, setAuto] = useState(true);
  const seq = useRef(0);

  const load = useCallback(async () => {
    const my = ++seq.current;
    try {
      const r = await api.monitoring();
      if (my !== seq.current) return;
      setData(r);
      setError(null);
    } catch (e) {
      if (my !== seq.current) return;
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (!auto) return;
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [auto, load]);

  const reindex = async (id: string) => {
    try {
      await api.reindexDocument(id);
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const sys = data?.system;

  return (
    <>
      <div className="kb-head">
        <div>
          <h1 className="page-title">모니터링</h1>
          <p className="page-sub">색인 작업과 시스템 상태를 확인합니다. {auto && <span className="muted">5초마다 자동 갱신 중</span>}</p>
        </div>
        <div className="st-headbtns">
          <button className={`btn ${auto ? "on" : ""}`} onClick={() => setAuto((v) => !v)}><Icon name="history" /> 자동 갱신 {auto ? "켜짐" : "꺼짐"}</button>
          <button className="btn" onClick={load}><Icon name="refresh" /> 새로고침</button>
        </div>
      </div>

      {error && <div className="alert error" style={{ marginBottom: 14 }}><Icon name="alert-circle" /> {error}</div>}

      <div className="kpis four">
        <div className="card kpi">
          <div className="kico green"><Icon name="check-circle" /></div>
          <div><div className="lbl">색인 완료</div><div className="val">{data ? `${data.summary.indexed}/${data.summary.total}` : "-"}</div>
            <div className="trend muted">색인 청크 {sys?.indexed_chunks ?? "-"}개</div></div>
        </div>
        <div className="card kpi">
          <div className="kico blue"><Icon name="history" /></div>
          <div><div className="lbl">처리 중</div><div className="val">{data?.summary.processing ?? "-"}</div>
            <div className="trend muted">{(data?.summary.processing ?? 0) > 0 ? "색인 파이프라인 진행 중" : "대기 중인 작업 없음"}</div></div>
        </div>
        <div className="card kpi">
          <div className="kico orange"><Icon name="alert-circle" /></div>
          <div><div className="lbl">오류</div><div className="val">{data?.summary.error ?? "-"}</div>
            <div className="trend muted">{(data?.summary.error ?? 0) > 0 ? "아래 표에서 재색인하세요" : "정상"}</div></div>
        </div>
        <div className="card kpi">
          <div className="kico blue"><Icon name="shield-check" /></div>
          <div><div className="lbl">시스템</div>
            <div className="val" style={{ fontSize: 18 }}>{sys ? (sys.db_ok ? "정상" : "DB 오류") : "-"}</div>
            <div className="trend muted">가동 {data ? fmtUptime(data.uptime_s) : "-"} · {sys?.db_backend ?? "-"} · 미처리 문의 {data?.open_inquiries ?? "-"}건</div></div>
        </div>
      </div>

      <section className="card" style={{ padding: "6px 0 4px" }}>
        <div className="table-wrap">
          <table className="table mon-table">
            <thead><tr><th>문서</th><th>카테고리</th><th>접근</th><th>진행 상태</th><th className="num">진행률</th><th className="num">청크</th><th>업로드</th><th className="num">처리 시간</th><th>오류</th><th style={{ textAlign: "right" }}>작업</th></tr></thead>
            <tbody>
              {!data && <tr><td colSpan={10}><div className="empty-state"><span className="spinner" /> 불러오는 중…</div></td></tr>}
              {data?.jobs.map((jb) => {
                const pct = STEP_PCT[jb.processing_status] ?? 0;
                const err = jb.processing_status === "error";
                return (
                  <tr key={jb.id}>
                    <td className="doc-cell"><b>{jb.title}</b><small className="muted"> {jb.document_id}</small></td>
                    <td>{jb.category ?? <span className="muted">-</span>}</td>
                    <td><span className={`badge ${jb.access_level === "internal" ? "orange" : "gray"}`}>{jb.access_level}</span></td>
                    <td><span className={`badge ${err ? "red" : jb.processing_status === "indexed" ? "green" : "blue"}`}>{jb.processing_status}</span></td>
                    <td className="num">
                      <div className="mon-bar" title={`${pct}%`}><i style={{ width: `${pct}%`, background: err ? "var(--red)" : pct === 100 ? "var(--green)" : "var(--primary)" }} /></div>
                    </td>
                    <td className="num">{jb.chunk_count}</td>
                    <td className="muted" style={{ whiteSpace: "nowrap" }}>{fmtTime(jb.created_at)}</td>
                    <td className="num">{jb.elapsed_s !== null ? `${jb.elapsed_s}s` : "-"}</td>
                    <td className="err-cell" title={jb.error_message ?? ""}>{jb.error_message ? jb.error_message : <span className="muted">-</span>}</td>
                    <td className="acts-r"><button className="icon-btn" title="재색인" onClick={() => reindex(jb.id)}><Icon name="refresh" /></button></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <div className="muted" style={{ fontSize: 12.5, marginTop: 12 }}>
        무료 티어 특성상 서버 재시작·스핀다운 중 진행되던 색인은 중단될 수 있습니다 — 해당 문서는 처리 중 상태로 남으니 재색인하세요.
        keep-alive 상태는 <Link className="link" href="https://github.com/speeno/RAG_CHATBOT/actions/workflows/keepalive.yml" target="_blank">GitHub Actions</Link>에서 확인.
      </div>
    </>
  );
}
