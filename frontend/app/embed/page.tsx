import { ChatView } from "@/components/chat/ChatView";

export const metadata = { title: "AI 상담 도우미" };

/** 사용자에게만 공유하는 상담 전용 경로 — 관리 메뉴 없이 상담 화면만 노출된다. iframe 임베드에도 사용 가능. */
export default function EmbedPage() {
  return (
    <div className="embed-wrap">
      <header className="embed-head">
        <img src="/logo-robot.png" alt="" className="embed-logo" />
        <b>AI 상담 도우미</b>
        <span className="muted">등록된 공식 문서를 근거로만 답변합니다</span>
      </header>
      <ChatView />
    </div>
  );
}
