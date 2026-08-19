/** 백엔드 API 클라이언트 (FastAPI). 타입은 backend/app/api/schemas.py 와 1:1 대응 */

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Source = {
  chunk_id: string;
  document_id: string;
  document_pk: string;
  title: string;
  section: string | null;
  version: string | null;
  updated_at: string | null;
  category: string | null;
  score: number;
};

export type ChatResponse = {
  conversation_id: string;
  message_id: string;
  answer: string;
  answerable: boolean;
  handoff: boolean;
  sources: Source[];
  rewritten_query: string | null;
  timings: Record<string, number>;
  model: string | null;
};

export type Health = {
  status: string;
  llm_provider: string;
  embedding_provider: string;
  score_threshold: number;
  indexed_chunks: number;
  offline_mode: boolean;
};

export type DocumentItem = {
  id: string;
  document_id: string;
  title: string;
  category: string | null;
  source: string | null;
  version: string | null;
  effective_date: string | null;
  updated_at: string | null;
  status: "active" | "inactive";
  language: string | null;
  filename: string | null;
  content_type: string | null;
  processing_status: "uploaded" | "parsing" | "chunking" | "embedding" | "indexed" | "error";
  error_message: string | null;
  chunk_count: number;
  created_at: string;
  indexed_at: string | null;
};

export type ChunkItem = {
  id: string;
  chunk_index: number;
  section: string | null;
  content: string;
  char_count: number;
  embedding_model: string | null;
};

async function j<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? JSON.stringify(body);
    } catch {
      /* ignore */
    }
    throw new Error(`${res.status} ${detail}`);
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

export const api = {
  health: () => fetch(`${API_URL}/api/health`, { cache: "no-store" }).then(j<Health>),

  chat: (message: string, conversation_id?: string | null) =>
    fetch(`${API_URL}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, conversation_id: conversation_id ?? null }),
    }).then(j<ChatResponse>),

  feedback: (message_id: string, rating: "positive" | "negative", reason?: string) =>
    fetch(`${API_URL}/api/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message_id, rating, reason }),
    }).then(j<{ ok: boolean }>),

  listDocuments: () => fetch(`${API_URL}/api/knowledge`, { cache: "no-store" }).then(j<DocumentItem[]>),
  getChunks: (id: string) => fetch(`${API_URL}/api/knowledge/${id}/chunks`, { cache: "no-store" }).then(j<ChunkItem[]>),
  uploadDocument: (form: FormData) => fetch(`${API_URL}/api/knowledge`, { method: "POST", body: form }).then(j<DocumentItem>),
  deleteDocument: (id: string) => fetch(`${API_URL}/api/knowledge/${id}`, { method: "DELETE" }).then(j<void>),
  reindexDocument: (id: string) => fetch(`${API_URL}/api/knowledge/${id}/reindex`, { method: "POST" }).then(j<DocumentItem>),
  patchDocument: (id: string, patch: Partial<Pick<DocumentItem, "status" | "title" | "category" | "version">>) =>
    fetch(`${API_URL}/api/knowledge/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    }).then(j<DocumentItem>),
};

/** SSE 스트리밍 채팅. 이벤트: meta → sources → delta* → done */
export type StreamHandlers = {
  onMeta?: (m: { conversation_id: string; message_id: string }) => void;
  onSources?: (s: Source[]) => void;
  onDelta?: (text: string) => void;
  onDone?: (r: ChatResponse) => void;
  onError?: (err: Error) => void;
};

export async function chatStream(
  message: string,
  conversation_id: string | null,
  h: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${API_URL}/api/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({ message, conversation_id }),
    signal,
  });
  if (!res.ok || !res.body) {
    h.onError?.(new Error(`${res.status} ${res.statusText}`));
    return;
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  const dispatch = (raw: string) => {
    let event = "message";
    let data = "";
    for (const line of raw.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) data += line.slice(5).trim();
    }
    if (!data) return;
    const payload = JSON.parse(data);
    if (event === "meta") h.onMeta?.(payload);
    else if (event === "sources") h.onSources?.(payload.sources);
    else if (event === "delta") h.onDelta?.(payload.text);
    else if (event === "done") h.onDone?.(payload);
  };
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let idx;
      while ((idx = buf.indexOf("\n\n")) !== -1) {
        const chunk = buf.slice(0, idx);
        buf = buf.slice(idx + 2);
        if (chunk.trim()) dispatch(chunk);
      }
    }
    if (buf.trim()) dispatch(buf);
  } catch (e) {
    if ((e as Error).name !== "AbortError") h.onError?.(e as Error);
  }
}
