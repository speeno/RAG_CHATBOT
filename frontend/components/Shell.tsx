"use client";

import { usePathname } from "next/navigation";
import { Sidebar } from "@/components/Sidebar";
import { Topbar } from "@/components/Topbar";

/** /embed* 경로는 사용자에게만 공유하는 상담 전용 화면 — 앱 셸(사이드바·탑바·관리 메뉴) 없이 렌더한다. */
export function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  if (path.startsWith("/embed")) {
    return <div className="embed-root">{children}</div>;
  }
  return (
    <div className="app">
      <Sidebar />
      <Topbar />
      <main className="main">{children}</main>
    </div>
  );
}
