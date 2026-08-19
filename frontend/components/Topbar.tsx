"use client";

import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

const TITLES: Record<string, string> = {
  "/": "상담하기",
  "/admin/knowledge": "지식베이스 관리",
};

export function Topbar() {
  const path = usePathname();
  const [ok, setOk] = useState<boolean | null>(null);
  useEffect(() => {
    api.health().then(() => setOk(true)).catch(() => setOk(false));
  }, [path]);
  return (
    <header className="topbar">
      <div className="title">{TITLES[path] ?? "AI 상담 도우미"}</div>
      <div className="top-right">
        <div className={`status-pill ${ok === false ? "warn" : ""}`}>
          <i /> {ok === null ? "확인 중" : ok ? "시스템 정상" : "백엔드 연결 안 됨"}
        </div>
        <div className="profile">
          <img src="/avatar-user.png" alt="" />
          <div>
            <div className="p-name">김지원</div>
            <div className="p-team">지원팀</div>
          </div>
        </div>
      </div>
    </header>
  );
}
