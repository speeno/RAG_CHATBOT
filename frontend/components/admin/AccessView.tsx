"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type DocumentItem } from "@/lib/api";
import { Icon } from "@/components/Icon";

export function AccessView() {
  const [docs, setDocs] = useState<DocumentItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setDocs(await api.listDocuments());
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const setLevel = async (d: DocumentItem, level: "public" | "internal") => {
    setBusy(d.id);
    try {
      await api.patchDocument(d.id, { access_level: level });
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const pub = docs?.filter((d) => d.access_level === "public").length ?? 0;
  const internal = docs?.filter((d) => d.access_level === "internal").length ?? 0;

  return (
    <>
      <div className="kb-head">
        <div>
          <h1 className="page-title">권한 관리</h1>
          <p className="page-sub">문서별 접근 레벨을 관리합니다. 필터는 <b>검색 단계</b>에서 적용됩니다(PRD §29) — LLM에는 허용된 문서만 전달됩니다.</p>
        </div>
        <button className="btn" onClick={load}><Icon name="refresh" /> 새로고침</button>
      </div>

      <div className="alert warn" style={{ marginBottom: 14, fontSize: 13 }}>
        <Icon name="shield-check" />
        <span><b>public</b> — 사용자 챗봇이 검색·인용 가능. <b>internal</b> — 사용자 챗봇에서 제외되며, 관리자 검색 테스트("내부 문서 포함")에서만 조회됩니다. 현재 공개 {pub}건 · 내부 {internal}건.</span>
      </div>

      {error && <div className="alert error" style={{ marginBottom: 14 }}><Icon name="alert-circle" /> {error}</div>}

      <section className="card" style={{ padding: "6px 0 4px" }}>
        <div className="table-wrap">
          <table className="table ac-table">
            <thead><tr><th>문서명</th><th>카테고리</th><th>상태</th><th>처리 상태</th><th>접근 레벨</th></tr></thead>
            <tbody>
              {docs === null && <tr><td colSpan={5}><div className="empty-state"><span className="spinner" /> 불러오는 중…</div></td></tr>}
              {docs?.map((d) => (
                <tr key={d.id}>
                  <td className="doc-cell">
                    <div className="doc-name">
                      <div className="doc-ico"><Icon name="file-fill" /></div>
                      <div><b>{d.title}</b><small>{d.document_id}{d.tags.length ? ` · ${d.tags.join(", ")}` : ""}</small></div>
                    </div>
                  </td>
                  <td>{d.category ?? <span className="muted">-</span>}</td>
                  <td><span className={`badge ${d.status === "active" ? "green" : "gray"}`}>{d.status === "active" ? "활성" : "비활성"}</span></td>
                  <td><span className={`badge ${d.processing_status === "indexed" ? "green" : d.processing_status === "error" ? "red" : "blue"}`}>{d.processing_status}</span></td>
                  <td>
                    <div className="seg sm">
                      <button className={d.access_level === "public" ? "on" : ""} disabled={busy === d.id} onClick={() => d.access_level !== "public" && setLevel(d, "public")}>public</button>
                      <button className={d.access_level === "internal" ? "on warn" : ""} disabled={busy === d.id} onClick={() => d.access_level !== "internal" && setLevel(d, "internal")}>internal</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <div className="muted" style={{ fontSize: 12.5, marginTop: 12 }}>
        역할(사용자 그룹)별 권한은 후속 과제입니다 — 현재는 익명 사용자(public)와 관리자(전체) 2단계로 동작합니다.
      </div>
    </>
  );
}
