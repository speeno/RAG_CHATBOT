"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, chatStream, type ChatResponse, type Source } from "@/lib/api";
import { Icon } from "@/components/Icon";
import { BotMessage, UserMessage, type BotMsg } from "./Messages";

const SUGGESTED = [
  { icon: "rotate-ccw", q: "환불은 어떻게 신청하나요?" },
  { icon: "truck", q: "배송비는 얼마인가요?" },
  { icon: "history", q: "주문 취소는 언제까지 가능한가요?" },
  { icon: "headset", q: "교환은 어떤 조건에서 가능한가요?" },
];

const SIDE_QUESTIONS = ["배송 조회는 어떻게 하나요?", "환불 처리 기간은 얼마나 걸리나요?", "배송지 변경 가능한가요?", "배송이 늦어져서 환불받고 싶어요"];

type Msg = { kind: "user"; id: string; text: string; time: string } | ({ kind: "bot" } & BotMsg);

const nowTime = () => new Date().toLocaleTimeString("ko-KR", { hour: "numeric", minute: "2-digit" });

export function ChatView() {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const updateBot = useCallback((id: string, patch: Partial<BotMsg> | ((m: BotMsg) => Partial<BotMsg>)) => {
    setMessages((prev) =>
      prev.map((m) => (m.kind === "bot" && m.id === id ? { ...m, ...(typeof patch === "function" ? patch(m) : patch) } : m)),
    );
  }, []);

  const send = useCallback(
    async (text: string) => {
      const q = text.trim();
      if (!q || busy) return;
      setError(null);
      setInput("");
      const botId = `bot-${Date.now()}`;
      setMessages((prev) => [
        ...prev,
        { kind: "user", id: `u-${Date.now()}`, text: q, time: nowTime() },
        { kind: "bot", id: botId, messageId: null, text: "", sources: [], candidateSources: [], streaming: true, done: null, time: nowTime() },
      ]);
      setBusy(true);
      const ac = new AbortController();
      abortRef.current = ac;
      await chatStream(
        q,
        conversationId,
        {
          onMeta: (m) => {
            setConversationId(m.conversation_id);
            updateBot(botId, { messageId: m.message_id });
          },
          onSources: (s: Source[]) => updateBot(botId, { candidateSources: s }),
          onDelta: (t) => updateBot(botId, (m) => ({ text: m.text + t })),
          onDone: (r: ChatResponse) => updateBot(botId, { text: r.answer, sources: r.sources, done: r, streaming: false }),
          onError: (e) => {
            setError(`응답을 받지 못했습니다: ${e.message}. 백엔드(${process.env.NEXT_PUBLIC_API_URL})가 실행 중인지 확인해 주세요.`);
            updateBot(botId, { streaming: false });
          },
        },
        ac.signal,
      );
      updateBot(botId, (m) => ({ streaming: false, text: m.text }));
      setBusy(false);
      abortRef.current = null;
      taRef.current?.focus();
    },
    [busy, conversationId, updateBot],
  );

  const stop = () => abortRef.current?.abort();

  const feedback = async (botId: string, messageId: string, rating: "positive" | "negative", reason?: string) => {
    updateBot(botId, { feedback: rating, feedbackReason: reason });
    try {
      await api.feedback(messageId, rating, reason);
    } catch {
      /* 피드백 실패는 조용히 무시 */
    }
  };

  const reset = () => {
    abortRef.current?.abort();
    setMessages([]);
    setConversationId(null);
    setError(null);
  };

  const onKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      send(input);
    }
  };

  const lastSources = [...messages].reverse().find((m): m is Extract<Msg, { kind: "bot" }> => m.kind === "bot" && m.sources.length > 0)?.sources ?? [];

  return (
    <div className="chat-layout">
      <section>
        {messages.length === 0 && (
          <div className="hero">
            <div>
              <h1><span>👋</span> 무엇을 도와드릴까요?</h1>
              <p>AI 상담 도우미가 등록된 공식 문서를 근거로 정확하고 신뢰할 수 있는 답변을 제공합니다.</p>
            </div>
            <img src="/hero-robot.png" alt="" />
          </div>
        )}
        <div className={`card chat-card ${messages.length === 0 ? "with-hero" : ""}`}>
          <div className="chat-head">
            <div className="lbl"><Icon name="sparkles" /> {messages.length === 0 ? "추천 질문" : "상담 진행 중"}</div>
            {messages.length > 0 && (
              <button className="btn sm" onClick={reset}><Icon name="refresh" /> 새 상담</button>
            )}
          </div>
          {messages.length === 0 && (
            <div className="suggest">
              {SUGGESTED.map((s) => (
                <button key={s.q} className="chip-q" onClick={() => send(s.q)}>
                  <Icon name={s.icon} /> {s.q}
                </button>
              ))}
            </div>
          )}
          <div className="messages" ref={listRef}>
            {messages.length === 0 && <div className="empty">질문을 입력하거나 추천 질문을 선택해 주세요.</div>}
            {messages.map((m) =>
              m.kind === "user" ? (
                <UserMessage key={m.id} text={m.text} time={m.time} />
              ) : (
                <BotMessage key={m.id} msg={m} onFeedback={(rating, reason) => m.messageId && feedback(m.id, m.messageId, rating, reason)} onAsk={send} />
              ),
            )}
          </div>
          {error && (
            <div className="alert error" style={{ marginTop: 12 }}><Icon name="alert-circle" /> {error}</div>
          )}
          <div className="chat-input">
            <textarea
              ref={taRef}
              rows={1}
              value={input}
              placeholder="궁금한 내용을 입력해 주세요..."
              onChange={(e) => {
                setInput(e.target.value);
                e.target.style.height = "auto";
                e.target.style.height = Math.min(e.target.scrollHeight, 160) + "px";
              }}
              onKeyDown={onKey}
              disabled={busy}
            />
            {busy ? (
              <button className="send stop" onClick={stop}><Icon name="square" /> 중지</button>
            ) : (
              <button className="send" onClick={() => send(input)} disabled={!input.trim()}><Icon name="send" /> 전송</button>
            )}
          </div>
          <div className="chat-hint">
            <span className="chat-note"><Icon name="shield-check" /> AI 상담 도우미는 내부 문서를 기반으로 답변하며, 근거가 없으면 답변하지 않습니다.</span>
            <span>Enter로 전송 / Shift + Enter로 줄바꿈</span>
          </div>
        </div>
      </section>

      <aside className="chat-side">
        <div className="card side-card">
          <div className="side-head"><b>관련 문서</b><span>최근 답변 기준</span></div>
          {lastSources.length === 0 ? (
            <div className="muted" style={{ fontSize: 13 }}>답변에 사용된 문서가 여기에 표시됩니다.</div>
          ) : (
            lastSources.map((s) => (
              <div className="doc-item" key={s.chunk_id}>
                <div className="doc-ico"><Icon name="file-fill" /></div>
                <div>
                  <div className="t">{s.title}</div>
                  <div className="s">{s.section?.split(" > ").slice(-1)[0]}</div>
                  <div className="d">{s.version ? `v${s.version}` : ""}{s.updated_at ? ` · 업데이트: ${s.updated_at}` : ""}</div>
                </div>
              </div>
            ))
          )}
        </div>
        <div className="card side-card">
          <div className="side-head"><b>추천 질문</b><span><Icon name="sparkles" style={{ width: 14, height: 14 }} /> 자주 묻는 질문</span></div>
          {SIDE_QUESTIONS.map((q) => (
            <button key={q} className="q-item" onClick={() => send(q)}>{q}</button>
          ))}
        </div>
      </aside>
    </div>
  );
}
