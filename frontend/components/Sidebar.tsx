"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { api, type Health } from "@/lib/api";
import { Icon } from "./Icon";

const USER_NAV = [
  { href: "/", label: "상담하기", icon: "chat" },
];
const ADMIN_NAV = [
  { href: "/admin/knowledge", label: "지식베이스", icon: "book-open" },
  { href: "/admin/search-test", label: "검색 테스트", icon: "search" },
];

export function Sidebar() {
  const path = usePathname();
  const [health, setHealth] = useState<Health | null>(null);
  const [err, setErr] = useState(false);

  useEffect(() => {
    let alive = true;
    const load = () =>
      api.health().then((h) => alive && (setHealth(h), setErr(false))).catch(() => alive && setErr(true));
    load();
    const t = setInterval(load, 15000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);

  const item = (n: { href: string; label: string; icon: string }) => (
    <Link key={n.href} href={n.href} className={`nav-item ${path === n.href ? "active" : ""}`}>
      <Icon name={n.icon} />
      <span>{n.label}</span>
    </Link>
  );

  return (
    <aside className="sidebar">
      <div className="brand">
        <img src="/logo-robot.png" alt="" />
        <span>AI 상담 도우미</span>
      </div>
      <nav className="nav">
        <div className="nav-group">사용자</div>
        {USER_NAV.map(item)}
        <div className="nav-group">관리자</div>
        {ADMIN_NAV.map(item)}
      </nav>
      <div className="sidebar-bottom">
        <div className="status-card">
          <div className="row">
            <b>시스템 상태</b>
            {err ? <span className="tag-offline">연결 안 됨</span> : health?.offline_mode ? <span className="tag-offline">오프라인 모드</span> : health ? <span className="tag-live">LIVE</span> : null}
          </div>
          <div className="row"><span>LLM</span><span>{health?.llm_provider ?? "-"}</span></div>
          <div className="row"><span>임베딩</span><span>{health?.embedding_provider ?? "-"}</span></div>
          <div className="row"><span>색인 청크</span><span>{health?.indexed_chunks ?? "-"}</span></div>
        </div>
      </div>
    </aside>
  );
}
