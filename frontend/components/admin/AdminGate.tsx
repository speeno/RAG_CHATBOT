"use client";

import { useCallback, useEffect, useState } from "react";
import { api, getAdminToken, setAdminToken } from "@/lib/api";
import { Icon } from "@/components/Icon";

type State = "checking" | "open" | "login" | "ok";

/** 관리자 화면 보호: 백엔드에 ADMIN_TOKEN 이 설정돼 있으면 토큰 입력을 요구한다(localStorage 보관).
 *  API 가 401 을 돌려주면(rag:unauthorized) 다시 로그인 화면으로. */
export function AdminGate({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<State>("checking");
  const [token, setToken] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const check = useCallback(async () => {
    try {
      const h = await api.health();
      if (!h.admin_auth) return setState("open");
      if (!getAdminToken()) return setState("login");
      await api.adminMe();
      setState("ok");
    } catch {
      setState(getAdminToken() ? "login" : "login");
    }
  }, []);

  useEffect(() => {
    check();
    const onUnauthorized = () => { setAdminToken(null); setErr("인증이 만료되었거나 토큰이 올바르지 않습니다."); setState("login"); };
    window.addEventListener("rag:unauthorized", onUnauthorized);
    return () => window.removeEventListener("rag:unauthorized", onUnauthorized);
  }, [check]);

  const login = async () => {
    if (!token.trim()) return;
    setBusy(true); setErr(null);
    setAdminToken(token.trim());
    try {
      await api.adminMe();
      setState("ok");
      setToken("");
    } catch {
      setAdminToken(null);
      setErr("토큰이 올바르지 않습니다.");
    } finally {
      setBusy(false);
    }
  };

  if (state === "checking") return <div className="empty-state"><span className="spinner" /> 관리자 인증 확인 중…</div>;
  if (state === "login") {
    return (
      <div className="gate">
        <div className="card gate-card">
          <div className="gate-ico"><Icon name="shield-check" /></div>
          <h2>관리자 인증</h2>
          <p>관리자 화면은 토큰으로 보호됩니다. 서버 환경변수 <code>ADMIN_TOKEN</code> 값을 입력하세요.</p>
          <input className="input" type="password" placeholder="관리자 토큰" value={token} onChange={(e) => setToken(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.nativeEvent.isComposing) login(); }} autoFocus />
          {err && <div className="alert error" style={{ marginTop: 10 }}><Icon name="alert-circle" /> {err}</div>}
          <button className="btn primary" style={{ marginTop: 12, width: "100%" }} disabled={busy || !token.trim()} onClick={login}>{busy ? "확인 중…" : "로그인"}</button>
          <div className="muted" style={{ fontSize: 12, marginTop: 10 }}>토큰은 이 브라우저에만 저장되며 관리자 API 호출 시 Bearer 헤더로 전송됩니다.</div>
        </div>
      </div>
    );
  }
  return (
    <>
      {state === "ok" && (
        <div className="gate-bar">
          <span><Icon name="shield-check" /> 관리자 인증됨</span>
          <button className="link" onClick={() => { setAdminToken(null); setState("login"); }}>로그아웃</button>
        </div>
      )}
      {children}
    </>
  );
}
