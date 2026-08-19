"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, type ChunkItem, type DocumentItem } from "@/lib/api";
import { Icon } from "@/components/Icon";

const STEPS = ["uploaded", "parsing", "chunking", "embedding", "indexed"] as const;
const STEP_LABEL: Record<DocumentItem["processing_status"], string> = {
  uploaded: "업로드됨", parsing: "파싱 중", chunking: "청킹 중", embedding: "임베딩 중", indexed: "색인 완료", error: "오류",
};

function ProcStatus({ d }: { d: DocumentItem }) {
  const idx = STEPS.indexOf(d.processing_status as (typeof STEPS)[number]);
  const isErr = d.processing_status === "error";
  const done = d.processing_status === "indexed";
  return (
    <span className="proc" title={d.error_message ?? ""}>
      <span className="steps">
        {STEPS.slice(1).map((s, i) => (
          <i key={s} className={isErr ? "err" : done ? "ok" : i < idx ? "on" : ""} />
        ))}
      </span>
      <span className={`badge ${isErr ? "red" : done ? "green" : "blue"}`}>{STEP_LABEL[d.processing_status]}</span>
      {!done && !isErr && <span className="spinner" />}
    </span>
  );
}

export function KnowledgeView() {
  const [docs, setDocs] = useState<DocumentItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<DocumentItem | null>(null);
  const [chunks, setChunks] = useState<ChunkItem[] | null>(null);
  const [filter, setFilter] = useState<"all" | "active" | "inactive" | "error">("all");

  const load = useCallback(async () => {
    try {
      const list = await api.listDocuments();
      setDocs(list);
      setError(null);
    } catch (e) {
      setError(`문서 목록을 불러오지 못했습니다: ${(e as Error).message}`);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // 처리 중인 문서가 있으면 2초마다 폴링
  const processing = useMemo(() => docs?.some((d) => !["indexed", "error"].includes(d.processing_status)) ?? false, [docs]);
  useEffect(() => {
    if (!processing) return;
    const t = setInterval(load, 2000);
    return () => clearInterval(t);
  }, [processing, load]);

  useEffect(() => {
    if (!selected) return setChunks(null);
    api.getChunks(selected.id).then(setChunks).catch(() => setChunks([]));
  }, [selected]);

  const filtered = (docs ?? []).filter((d) =>
    filter === "all" ? true : filter === "error" ? d.processing_status === "error" : d.status === filter,
  );
  const counts = {
    all: docs?.length ?? 0,
    active: docs?.filter((d) => d.status === "active").length ?? 0,
    inactive: docs?.filter((d) => d.status === "inactive").length ?? 0,
    error: docs?.filter((d) => d.processing_status === "error").length ?? 0,
  };

  const act = async (fn: () => Promise<unknown>) => {
    try {
      await fn();
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <>
      <div className="kb-head">
        <div>
          <h1 className="page-title">지식베이스</h1>
          <p className="page-sub">AI 상담 도우미가 답변에 참고하는 문서를 관리하세요. 등록 즉시 파싱 → 청킹 → 임베딩 → 색인이 진행됩니다.</p>
        </div>
        <button className="btn" onClick={load}><Icon name="refresh" /> 새로고침</button>
      </div>

      {error && <div className="alert error" style={{ marginBottom: 14 }}><Icon name="alert-circle" /> {error}</div>}

      <div className="kb-grid">
        <div>
          <div className="kb-stats">
            {(["all", "active", "inactive", "error"] as const).map((k) => (
              <button key={k} className={`stat ${filter === k ? "on" : ""}`} onClick={() => setFilter(k)}>
                {{ all: "전체", active: "활성", inactive: "비활성", error: "오류" }[k]} <b>{counts[k]}</b>
              </button>
            ))}
          </div>
          <div className="card">
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>문서명</th><th>카테고리</th><th>버전</th><th>상태</th><th>처리 상태</th><th>청크</th><th>업데이트일</th><th style={{ textAlign: "right", paddingRight: 18 }}>작업</th>
                  </tr>
                </thead>
                <tbody>
                  {docs === null && (
                    <tr><td colSpan={8}><div className="empty-state"><span className="spinner" /> 불러오는 중…</div></td></tr>
                  )}
                  {docs !== null && filtered.length === 0 && (
                    <tr><td colSpan={8}><div className="empty-state">등록된 문서가 없습니다. 오른쪽에서 Markdown/HTML 문서를 업로드하세요.</div></td></tr>
                  )}
                  {filtered.map((d) => (
                    <tr key={d.id} className={selected?.id === d.id ? "selected" : ""} onClick={() => setSelected(selected?.id === d.id ? null : d)} style={{ cursor: "pointer" }}>
                      <td>
                        <div className="doc-name">
                          <div className="doc-ico" style={d.status === "inactive" ? { background: "#eceff4", color: "#a3abba" } : undefined}><Icon name="file-fill" /></div>
                          <div><b>{d.title}</b><small>{d.document_id} · {d.filename ?? d.content_type}</small></div>
                        </div>
                      </td>
                      <td className="cell-cat" title={d.category ?? undefined}>{d.category ?? <span className="muted">-</span>}</td>
                      <td>{d.version ? `v${d.version}` : "-"}</td>
                      <td><span className={`badge ${d.status === "active" ? "green" : "gray"}`}>{d.status === "active" ? "활성" : "비활성"}</span></td>
                      <td><ProcStatus d={d} /></td>
                      <td>{d.chunk_count}</td>
                      <td>{d.updated_at ?? d.effective_date ?? d.created_at.slice(0, 10)}</td>
                      <td onClick={(e) => e.stopPropagation()}>
                        <div className="acts">
                          <button className="icon-btn" title={d.status === "active" ? "비활성화" : "활성화"} onClick={() => act(() => api.patchDocument(d.id, { status: d.status === "active" ? "inactive" : "active" }))}>
                            <Icon name="power" />
                          </button>
                          <button className="icon-btn" title="재색인" onClick={() => act(() => api.reindexDocument(d.id))}><Icon name="refresh" /></button>
                          <button className="icon-btn danger" title="삭제" onClick={() => { if (confirm(`'${d.title}' 문서를 삭제할까요?`)) act(() => api.deleteDocument(d.id)); }}><Icon name="trash" /></button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {selected && (
            <div className="card detail-card" style={{ marginTop: 16 }}>
              <h3>
                <span>{selected.title} — 청크 미리보기{chunks ? ` (${chunks.length})` : ""}</span>
                <button className="icon-btn" onClick={() => setSelected(null)}><Icon name="x" /></button>
              </h3>
              {selected.error_message && <div className="alert error" style={{ marginTop: 10 }}><Icon name="alert-circle" /> {selected.error_message}</div>}
              {chunks === null ? <div className="muted" style={{ marginTop: 10 }}>불러오는 중…</div> : chunks.length === 0 ? <div className="muted" style={{ marginTop: 10 }}>청크가 없습니다.</div> : chunks.map((c) => (
                <div className="chunk" key={c.id}>
                  <div className="sec">#{c.chunk_index + 1} · {c.section ?? "-"} · {c.char_count}자{c.embedding_model ? ` · ${c.embedding_model}` : ""}</div>
                  <pre>{c.content}</pre>
                </div>
              ))}
            </div>
          )}
        </div>

        <UploadForm onUploaded={load} />
      </div>
    </>
  );
}

function UploadForm({ onUploaded }: { onUploaded: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [over, setOver] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ kind: "ok" | "err"; text: string } | null>(null);
  const [meta, setMeta] = useState({ title: "", document_id: "", category: "", version: "", effective_date: "" });
  const [suggest, setSuggest] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // 미답변 분석 → "새 문서 추가/기존 문서 보완"으로 넘어온 경우(?suggest=질문) 안내 표시
  useEffect(() => {
    const q = new URLSearchParams(window.location.search).get("suggest");
    if (q) setSuggest(q);
  }, []);

  const pick = (f: File | null) => {
    setFile(f);
    setMsg(null);
    if (f && !meta.title) setMeta((m) => ({ ...m, title: f.name.replace(/\.[^.]+$/, "") }));
  };

  const submit = async () => {
    if (!file) return;
    setBusy(true);
    setMsg(null);
    try {
      const form = new FormData();
      form.append("file", file);
      Object.entries(meta).forEach(([k, v]) => v && form.append(k, v));
      const doc = await api.uploadDocument(form);
      setMsg({ kind: "ok", text: `'${doc.title}' 등록됨 — 색인을 진행합니다.` });
      setFile(null);
      setMeta({ title: "", document_id: "", category: "", version: "", effective_date: "" });
      if (inputRef.current) inputRef.current.value = "";
      onUploaded();
    } catch (e) {
      setMsg({ kind: "err", text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card upload-card">
      <h2>문서 업로드</h2>
      <div className="sub">Markdown(.md) 권장 · HTML(.html) 지원 · 최대 5MB. front matter(document_id, title, category, version…)가 있으면 자동으로 읽습니다.</div>
      <div
        className={`drop ${over ? "over" : ""}`}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setOver(true); }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); pick(e.dataTransfer.files?.[0] ?? null); }}
      >
        <div className="cloud"><Icon name="cloud-upload" /></div>
        <div className="t1">파일을 드래그 &amp; 드롭하거나 클릭하여 선택하세요</div>
        <div className="t2">Markdown, HTML, TXT 파일을 지원합니다.</div>
        {file && <div className="file">{file.name} ({Math.round(file.size / 1024)} KB)</div>}
        <input ref={inputRef} type="file" accept=".md,.markdown,.txt,.html,.htm" hidden onChange={(e) => pick(e.target.files?.[0] ?? null)} />
      </div>
      <div className="f-grid">
        <div className="full"><label className="field-label">문서명</label><input className="input" value={meta.title} onChange={(e) => setMeta({ ...meta, title: e.target.value })} placeholder="예) 환불 및 교환 정책 안내 (비우면 front matter/파일명 사용)" /></div>
        <div><label className="field-label">문서 ID</label><input className="input" value={meta.document_id} onChange={(e) => setMeta({ ...meta, document_id: e.target.value })} placeholder="REFUND-001" /></div>
        <div><label className="field-label">카테고리</label><input className="input" value={meta.category} onChange={(e) => setMeta({ ...meta, category: e.target.value })} placeholder="customer_service" /></div>
        <div><label className="field-label">버전</label><input className="input" value={meta.version} onChange={(e) => setMeta({ ...meta, version: e.target.value })} placeholder="1.0" /></div>
        <div><label className="field-label">시행일</label><input className="input" type="date" value={meta.effective_date} onChange={(e) => setMeta({ ...meta, effective_date: e.target.value })} /></div>
      </div>
      {suggest && (
        <div className="alert warn" style={{ marginTop: 12, fontSize: 13 }}>
          <Icon name="help" /> <span>미답변 질문 <b>“{suggest}”</b>에 답할 수 있는 문서를 추가하거나, 관련 문서를 보완해 재색인하세요.</span>
        </div>
      )}
      {msg && <div className={`alert ${msg.kind === "ok" ? "warn" : "error"}`} style={{ marginTop: 12, ...(msg.kind === "ok" ? { background: "var(--green-bg)", color: "#0f6f55", borderColor: "#bfead9" } : {}) }}><Icon name={msg.kind === "ok" ? "check-circle" : "alert-circle"} /> {msg.text}</div>}
      <div className="f-btns">
        <button className="btn primary" disabled={!file || busy} onClick={submit}>
          {busy ? <span className="spinner" style={{ borderTopColor: "#fff" }} /> : <Icon name="cloud-upload" />} 업로드 시작
        </button>
      </div>
    </div>
  );
}
