import type { Metadata } from "next";
import "./globals.css";
import { Sidebar } from "@/components/Sidebar";
import { Topbar } from "@/components/Topbar";

export const metadata: Metadata = {
  title: "AI 상담 도우미",
  description: "RAG 기반 AI 상담 챗봇 — 등록된 문서를 근거로만 답변합니다.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body>
        <div className="app">
          <Sidebar />
          <Topbar />
          <main className="main">{children}</main>
        </div>
      </body>
    </html>
  );
}
