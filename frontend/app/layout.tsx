import type { Metadata } from "next";
import "./globals.css";
import { Shell } from "@/components/Shell";

export const metadata: Metadata = {
  title: "AI 상담 도우미",
  description: "RAG 기반 AI 상담 챗봇 — 등록된 문서를 근거로만 답변합니다.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body>
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
