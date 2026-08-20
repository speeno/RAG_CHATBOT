"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type ConversationOut } from "@/lib/api";
import { Icon } from "@/components/Icon";
import { CONVERSATIONS_KEY, type SavedConversation } from "./ChatView";

const fmt = (s: string) => {
  const d = new Date(s);
  return isNaN(d.getTime()) ? s : d.toLocaleString("ko-KR", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
};

export function HistoryView() {
  const [list, setList] = useState<SavedConversation[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [conv, setConv] = useState<ConversationOut | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    try {
      setList(JSON.parse(localStorage.getItem(CONVERSATIONS_KEY) ?? "[]") as SavedConversation[]);
    } catch {
      setList([]);
    }
  }, []);

  useEffect(() => {
    if (!selected) return setConv(null);
    setConv(null);
    api.getConversation(selected)
      .then((c) => { setConv(c); setError(null); })
      .catch(() => setError("대화를 불러오지 못했습니다. 서버에서 삭제되었을 수 있습니다."));
  }, [selected]);

  const remove = (id: string) => {
    const next = list.filter((c) => c.id !== id);
    setList(next);
    localStorage.setItem(CONVERSATIONS_KEY, JSON.stringify(next));
    if (selected === id) setSelected(null);
  };

  return (
    <>
      <div className="kb-head">
        <div>
          <h1 className="page-title">상담 이력</h1>
          <p className="page-sub">이 브라우저에서 진행한 상담 목록입니다. 대화를 선택해 내용을 확인하거나 이어서 상담할 수 있습니다.</p>
        </div>
        <Link className="btn primary" href="/"><Icon name="chat" /> 새 상담 시작</Link>
      </div>

      {error && <div className="alert error" style={{ marginBottom: 14 }}><Icon name="alert-circle" /> {error}</div>}

      {list.length === 0 ? (
        <div className="card"><div className="empty-state">저장된 상담 이력이 없습니다. <Link className="link" href="/">상담을 시작</Link>하면 이곳에 기록됩니다.</div></div>
      ) : (
        <div className="hist-grid">
          <section className="card hist-list">
            {list.map((c) => (
              <button key={c.id} className={`hist-item ${selected === c.id ? "on" : ""}`} onClick={() => setSelected(selected === c.id ? null : c.id)}>
                <div className="doc-ico"><Icon name="chat" /></div>
                <div className="b">
                  <div className="t">{c.first_question}</div>
                  <div className="s muted">{fmt(c.updated_at)} · {c.turns}개 질문{c.turns > 1 && c.last_question !== c.first_question ? ` · 마지막: ${c.last_question}` : ""}</div>
                </div>
                <span className="icon-btn danger" role="button" tabIndex={0} title="이력에서 삭제"
                  onClick={(e) => { e.stopPropagation(); remove(c.id); }}
                  onKeyDown={(e) => { if (e.key === "Enter") { e.stopPropagation(); remove(c.id); } }}><Icon name="trash" /></span>
              </button>
            ))}
            <div className="muted" style={{ fontSize: 12, padding: "10px 4px 2px" }}>이력은 이 브라우저(localStorage)에만 저장되며 최대 50건 보관됩니다.</div>
          </section>

          <aside className="card hist-detail">
            {!selected ? (
              <div className="muted" style={{ fontSize: 13 }}>왼쪽에서 상담을 선택하세요.</div>
            ) : !conv ? (
              <div className="empty-state"><span className="spinner" /> 불러오는 중…</div>
            ) : (
              <>
                <div className="hist-detail-head">
                  <b>대화 내용</b>
                  <Link className="btn sm primary" href={`/?conversation=${selected}`}><Icon name="chat" /> 이어서 상담하기</Link>
                </div>
                <div className="lg-conv" style={{ borderTop: 0, paddingTop: 0 }}>
                  {conv.messages.map((m) => (
                    <div key={m.id} className={`m ${m.role}`}>
                      <div className="who">{m.role === "user" ? "나" : "AI"} <span className="muted">{fmt(m.created_at)}</span></div>
                      <div className="body">{m.content}</div>
                      {m.role === "assistant" && m.sources.length > 0 && (
                        <div className="srcs muted">출처: {m.sources.map((s) => s.title).filter((v, i, a) => a.indexOf(v) === i).join(", ")}</div>
                      )}
                    </div>
                  ))}
                </div>
              </>
            )}
          </aside>
        </div>
      )}
    </>
  );
}
