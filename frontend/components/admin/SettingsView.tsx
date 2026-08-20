"use client";

import { useEffect, useState } from "react";
import { api, type AdminSettings } from "@/lib/api";
import { Icon } from "@/components/Icon";

function Row({ k, v, hint }: { k: string; v: React.ReactNode; hint?: string }) {
  return (
    <div className="set-row" title={hint}>
      <span className="k">{k}</span>
      <span className="v">{v}</span>
    </div>
  );
}

const onoff = (b: boolean) => (b ? <span className="badge green">사용</span> : <span className="badge gray">미사용</span>);

export function SettingsView() {
  const [s, setS] = useState<AdminSettings | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.adminSettings().then(setS).catch((e) => setError((e as Error).message));
  }, []);

  return (
    <>
      <div className="kb-head">
        <div>
          <h1 className="page-title">설정</h1>
          <p className="page-sub">현재 서버에 적용된 런타임 설정입니다(읽기 전용). 변경은 배포 환경변수(Render ▸ Environment)에서 하며, 저장 시 자동 재배포됩니다.</p>
        </div>
        <button className="btn" onClick={() => { setS(null); api.adminSettings().then(setS).catch((e) => setError((e as Error).message)); }}><Icon name="refresh" /> 새로고침</button>
      </div>

      {error && <div className="alert error" style={{ marginBottom: 14 }}><Icon name="alert-circle" /> {error}</div>}
      {!s ? <div className="empty-state"><span className="spinner" /> 불러오는 중…</div> : (
        <div className="set-grid">
          <section className="card panel">
            <div className="panel-head"><h3>LLM</h3><span className="chip">{s.llm.provider}</span></div>
            <Row k="Anthropic 모델" v={s.llm.anthropic_model} />
            <Row k="OpenAI 모델" v={s.llm.openai_model} />
            <Row k="Effort / Max tokens" v={`${s.llm.effort} / ${s.llm.max_tokens.toLocaleString()}`} />
          </section>
          <section className="card panel">
            <div className="panel-head"><h3>임베딩</h3><span className="chip">{s.embedding.provider}</span></div>
            <Row k="Voyage 모델" v={s.embedding.voyage_model} />
            <Row k="OpenAI 모델" v={s.embedding.openai_model} />
            <Row k="색인 청크" v={s.storage.indexed_chunks.toLocaleString()} />
            <Row k="DB" v={<span className="badge blue">{s.storage.db_backend}</span>} />
          </section>
          <section className="card panel">
            <div className="panel-head"><h3>검색 (Retrieval)</h3><span className="chip">{s.retrieval.mode}</span></div>
            <Row k="Top-K / 컨텍스트 청크" v={`${s.retrieval.top_k} / ${s.retrieval.max_context_chunks}`} />
            <Row k="Fail-Closed 임계값" v={<b>{s.retrieval.threshold}</b>} hint="최고 벡터 점수가 이 값 미만이면 답변하지 않습니다 (RETRIEVAL_SCORE_THRESHOLD)" />
            <Row k="후보 수 (dense/BM25 각)" v={s.retrieval.candidates} />
            <Row k="RRF k / dense 가중치" v={`${s.retrieval.rrf_k} / ${s.retrieval.dense_weight}`} />
            <Row k="Multi Query (채팅)" v={<>{onoff(s.retrieval.multi_query)} <span className="muted">확장 {s.retrieval.multi_query_n}개</span></>} />
            <Row k="Reranker" v={s.retrieval.reranker === "none" ? <span className="badge gray">none</span> : <span className="badge green">{s.retrieval.reranker}</span>} />
          </section>
          <section className="card panel">
            <div className="panel-head"><h3>청킹</h3></div>
            <Row k="최대 길이" v={`${s.chunking.max_chars.toLocaleString()}자`} hint="≈ 400~800 토큰 (한국어)" />
            <Row k="오버랩" v={`${s.chunking.overlap_chars}자`} />
          </section>
          <section className="card panel">
            <div className="panel-head"><h3>보안 / CORS</h3></div>
            <Row k="관리자 인증" v={onoff(s.security.admin_auth)} hint="ADMIN_TOKEN 설정 여부" />
            <Row k="허용 오리진" v={<span className="set-mono">{s.security.cors_origins.join(", ") || "-"}</span>} />
            <Row k="오리진 정규식" v={<span className="set-mono">{s.security.cors_origin_regex ?? "-"}</span>} />
          </section>
          <section className="card panel">
            <div className="panel-head"><h3>Fail-Closed 안내 문구</h3></div>
            <div className="gbox" style={{ background: "#f4f6fa", borderRadius: 8, padding: "10px 12px", fontSize: 13 }}>{s.no_answer_message}</div>
            <div className="muted" style={{ fontSize: 12, marginTop: 10 }}>이 문구는 코드 상수(NO_ANSWER_MESSAGE)로 관리됩니다.</div>
          </section>
        </div>
      )}
    </>
  );
}
