"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { API_URL, api, chatStream, type ChatResponse, type GeoPoint, type Source } from "@/lib/api";
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

/* ── 날씨 질문 시 브라우저 위치정보 (지역명이 없을 때 현재 위치 날씨 제공) ── */
const GEO_KEY = "rag.geo";                       // {lat, lon, at} 또는 "denied"
const WEATHER_RE = /날씨|기온|온도|비\s|비가|비\s?와|비\s?오|눈\s|눈이|눈\s?와|눈\s?오|폭우|폭설|호우|태풍|특보|우산|강수|더위|추위|더워|추워|덥|춥|바람|습도|맑|흐리|우천|기상/;

function getStoredGeo(): GeoPoint | null | "denied" {
  try {
    const raw = localStorage.getItem(GEO_KEY);
    if (!raw) return null;
    if (raw === "denied") return "denied";
    const v = JSON.parse(raw) as { lat: number; lon: number };
    return typeof v.lat === "number" && typeof v.lon === "number" ? { lat: v.lat, lon: v.lon } : null;
  } catch {
    return null;
  }
}

/** 위치정보 1회 획득 후 localStorage 저장. 거부/실패 시 "denied" 기록(재요청으로 사용자를 귀찮게 하지 않음). */
function requestGeo(): Promise<GeoPoint | null> {
  return new Promise((resolve) => {
    if (typeof navigator === "undefined" || !navigator.geolocation) return resolve(null);
    const done = (v: GeoPoint | null) => resolve(v);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const v = { lat: Math.round(pos.coords.latitude * 10000) / 10000, lon: Math.round(pos.coords.longitude * 10000) / 10000 };
        try { localStorage.setItem(GEO_KEY, JSON.stringify({ ...v, at: Date.now() })); } catch { /* ignore */ }
        done(v);
      },
      () => {
        try { localStorage.setItem(GEO_KEY, "denied"); } catch { /* ignore */ }
        done(null);
      },
      { timeout: 5000, maximumAge: 600000 },
    );
  });
}

async function geoForMessage(text: string): Promise<GeoPoint | null> {
  if (!WEATHER_RE.test(text)) return null;
  const stored = getStoredGeo();
  if (stored === "denied") return null;
  if (stored) return stored;
  return requestGeo();
}

/** 상담 이력(/history)용: 이 브라우저에서 진행한 대화 목록을 localStorage 에 보관 */
export const CONVERSATIONS_KEY = "rag.conversations";
export type SavedConversation = { id: string; first_question: string; last_question: string; started_at: string; updated_at: string; turns: number };

function saveConversation(id: string, question: string) {
  try {
    const list = JSON.parse(localStorage.getItem(CONVERSATIONS_KEY) ?? "[]") as SavedConversation[];
    const now = new Date().toISOString();
    const cur = list.find((c) => c.id === id);
    if (cur) {
      cur.last_question = question;
      cur.updated_at = now;
      cur.turns += 1;
    } else {
      list.unshift({ id, first_question: question, last_question: question, started_at: now, updated_at: now, turns: 1 });
    }
    list.sort((a, b) => (a.updated_at < b.updated_at ? 1 : -1));
    localStorage.setItem(CONVERSATIONS_KEY, JSON.stringify(list.slice(0, 50)));
  } catch {
    /* storage 실패 무시 */
  }
}

export function ChatView() {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // 무료 티어(Render) 백엔드는 유휴 시 잠들어 첫 응답에 최대 1분가량 걸린다 → 마운트 시 미리 깨우고 안내한다.
  const [waking, setWaking] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    const cid = new URLSearchParams(window.location.search).get("conversation");
    if (!cid) return;
    api.getConversation(cid).then((conv) => {
      setConversationId(cid);
      setMessages(conv.messages.map((m, i): Msg => {
        const time = new Date(m.created_at).toLocaleTimeString("ko-KR", { hour: "numeric", minute: "2-digit" });
        return m.role === "user"
          ? { kind: "user", id: `h-u-${i}`, text: m.content, time }
          : { kind: "bot", id: `h-b-${i}`, messageId: m.id, text: m.content, sources: m.sources, candidateSources: [], streaming: false,
              done: { conversation_id: cid, message_id: m.id, answer: m.content, answerable: m.answerable ?? true, handoff: !(m.answerable ?? true),
                      sources: m.sources, rewritten_query: null, timings: {}, model: null }, time };
      }));
    }).catch(() => { /* 만료/삭제된 대화 — 새 상담으로 시작 */ });
  }, []);

  useEffect(() => {
    let alive = true;
    const slow = setTimeout(() => alive && setWaking(true), 2500);
    const ping = async () => {
      for (let i = 0; i < 20 && alive; i++) {
        try {
          await api.health();
          break;
        } catch {
          await new Promise((r) => setTimeout(r, 5000));
        }
      }
      clearTimeout(slow);
      if (alive) setWaking(false);
    };
    ping();
    return () => {
      alive = false;
      clearTimeout(slow);
    };
  }, []);

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
        { kind: "bot", id: botId, messageId: null, userQuestion: q, text: "", sources: [], candidateSources: [], streaming: true, done: null, time: nowTime() },
      ]);
      setBusy(true);
      const location = await geoForMessage(q);  // 날씨 질문일 때만 위치정보 사용(1회 획득 후 저장)
      const ac = new AbortController();
      abortRef.current = ac;
      await chatStream(
        q,
        conversationId,
        {
          onMeta: (m) => {
            setConversationId(m.conversation_id);
            updateBot(botId, { messageId: m.message_id });
            saveConversation(m.conversation_id, q);
          },
          onSources: (s: Source[]) => updateBot(botId, { candidateSources: s }),
          onDelta: (t) => updateBot(botId, (m) => ({ text: m.text + t })),
          onDone: (r: ChatResponse) => updateBot(botId, { text: r.answer, sources: r.sources, done: r, streaming: false }),
          onError: (e) => {
            setError(`응답을 받지 못했습니다: ${e.message}. 서버가 기동 중이면 잠시 후 다시 시도해 주세요. (백엔드: ${API_URL})`);
            updateBot(botId, { streaming: false });
          },
        },
        ac.signal,
        location,
      );
      updateBot(botId, (m) => ({ streaming: false, text: m.text }));
      setBusy(false);
      abortRef.current = null;
      taRef.current?.focus();
    },
    [busy, conversationId, updateBot],
  );

  const stop = () => abortRef.current?.abort();

  const feedback = async (botId: string, messageId: string, rating: "positive" | "negative",
                          detail?: { reasons?: string[]; comment?: string; escalate?: boolean }) => {
    const label = detail?.reasons?.length ? detail.reasons.join(", ") : undefined;
    updateBot(botId, { feedback: rating, feedbackReason: detail?.escalate ? `${label ?? ""}${label ? " · " : ""}상담원 전달됨` : label });
    try {
      await api.feedback(messageId, rating, detail);
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
                <BotMessage key={m.id} msg={m} onFeedback={(rating, detail) => m.messageId && feedback(m.id, m.messageId, rating, detail)} onAsk={send} />
              ),
            )}
          </div>
          {waking && !error && (
            <div className="alert warn" style={{ marginTop: 12 }}>
              <span className="spinner" /> 서버를 깨우는 중입니다. 무료 호스팅 특성상 첫 응답까지 최대 1분 정도 걸릴 수 있어요.
            </div>
          )}
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
