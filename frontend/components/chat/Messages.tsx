"use client";

import { Fragment, useState } from "react";
import type { ChatResponse, Source } from "@/lib/api";
import { Icon } from "@/components/Icon";

export type BotMsg = {
  id: string;
  messageId: string | null;
  text: string;
  sources: Source[];
  candidateSources: Source[];
  streaming: boolean;
  done: ChatResponse | null;
  time: string;
  feedback?: "positive" | "negative";
  feedbackReason?: string;
};

const fmtMs = (ms?: number) => (ms == null ? "-" : ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`);

const NEG_REASONS = ["답변이 틀렸어요", "질문과 관련 없어요", "설명이 부족해요", "최신 정보가 아니에요", "기타"];

export function UserMessage({ text, time }: { text: string; time: string }) {
  return (
    <div className="msg-user">
      <div className="bubble-user">{text}</div>
      <div className="time">{time}</div>
    </div>
  );
}

/** "[1]" 인용 마커를 배지로 렌더링 */
function renderWithCitations(text: string, sourceCount: number) {
  const parts = text.split(/(\[\d{1,2}\])/g);
  return parts.map((p, i) => {
    const m = /^\[(\d{1,2})\]$/.exec(p);
    if (m && Number(m[1]) <= Math.max(sourceCount, 0)) {
      return <sup key={i} className="cite" title={`출처 ${m[1]}`}>{m[1]}</sup>;
    }
    return <Fragment key={i}>{p}</Fragment>;
  });
}

export function BotMessage({
  msg,
  onFeedback,
  onAsk,
}: {
  msg: BotMsg;
  onFeedback: (rating: "positive" | "negative", reason?: string) => void;
  onAsk: (q: string) => void;
}) {
  const [showReasons, setShowReasons] = useState(false);
  const done = msg.done;
  const failClosed = done ? !done.answerable : false;
  const sources = msg.sources.length ? msg.sources : [];

  return (
    <div className="msg-bot">
      <img className="bot-avatar" src="/avatar-bot.png" alt="" />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div className="bubble-bot">
          <p>
            {msg.text ? renderWithCitations(msg.text, sources.length || msg.candidateSources.length) : null}
            {msg.streaming && <span className="cursor" />}
            {!msg.text && !msg.streaming && <span className="muted">응답이 없습니다.</span>}
          </p>

          {sources.length > 0 && !failClosed && (
            <div className="sources">
              <div className="sc-label">출처{sources.length > 1 ? ` (${sources.length})` : ""}</div>
              {sources.map((s, i) => (
                <div className="source-row" key={s.chunk_id}>
                  <span className="num">{i + 1}</span>
                  <div className="doc-ico"><Icon name="file-fill" /></div>
                  <div>
                    <div className="sc-title">{s.title}</div>
                    <div className="sc-sub">{s.section?.split(" > ").slice(1).join(" > ") || s.section}{s.version ? ` · v${s.version}` : ""}</div>
                  </div>
                  <div className="sc-date">{s.updated_at ? `업데이트: ${s.updated_at}` : ""}</div>
                </div>
              ))}
            </div>
          )}

          {failClosed && (
            <div className="handoff">
              <img src="/shield.png" alt="" />
              <div>
                <b>현재 등록된 자료에서는 해당 내용을 확인하기 어렵습니다.</b>
                <p>AI가 보유한 지식 범위를 벗어난 질문이거나, 관련 정책이 아직 등록되지 않았을 수 있습니다. 담당자에게 문의하시거나 다른 표현으로 다시 질문해 보세요.</p>
                <div className="acts">
                  <button className="btn sm"><Icon name="headset" /> 상담원 연결</button>
                  <button className="btn sm"><Icon name="mail" /> 문의 남기기</button>
                  <button className="btn sm" onClick={() => onAsk("환불은 어떻게 신청하나요?")}><Icon name="file-text" /> 관련 정책 보기</button>
                </div>
              </div>
            </div>
          )}

          {done && (
            <div className="meta-line">
              <span>응답 {fmtMs(done.timings.total_ms)}</span>
              <span>검색 {fmtMs(done.timings.retrieval_ms)}</span>
              {done.model && <span>모델 {done.model}</span>}
              {done.rewritten_query && <span title={done.rewritten_query}>검색 쿼리 재작성됨</span>}
            </div>
          )}
        </div>

        {done && msg.messageId && (
          <div className="fb-row">
            {msg.feedback ? (
              <span className="fb-thanks">피드백 감사합니다{msg.feedbackReason ? ` (${msg.feedbackReason})` : ""}.</span>
            ) : (
              <>
                <span className="q">답변이 도움이 되었나요?</span>
                <button className="fb-btn" onClick={() => onFeedback("positive")}><Icon name="thumbs-up" /> 도움이 돼요</button>
                <button className={`fb-btn ${showReasons ? "active" : ""}`} onClick={() => setShowReasons((v) => !v)}><Icon name="thumbs-down" /> 도움이 안 돼요</button>
              </>
            )}
            <span className="time" style={{ marginLeft: "auto" }}>{msg.time}</span>
          </div>
        )}
        {showReasons && !msg.feedback && (
          <div className="fb-reasons">
            {NEG_REASONS.map((r) => (
              <button key={r} onClick={() => { onFeedback("negative", r); setShowReasons(false); }}>{r}</button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
