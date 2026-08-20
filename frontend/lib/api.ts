/** 백엔드 API 클라이언트 (FastAPI). 타입은 backend/app/api/schemas.py 와 1:1 대응 */

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** 관리자 토큰(브라우저 localStorage). 백엔드 ADMIN_TOKEN 이 설정된 경우 관리자 API 호출에 Bearer 로 첨부된다. */
export const ADMIN_TOKEN_KEY = "rag.adminToken";
export const getAdminToken = () => (typeof window === "undefined" ? null : localStorage.getItem(ADMIN_TOKEN_KEY));
export const setAdminToken = (t: string | null) => {
  if (typeof window === "undefined") return;
  if (t) localStorage.setItem(ADMIN_TOKEN_KEY, t);
  else localStorage.removeItem(ADMIN_TOKEN_KEY);
};
/** 모든 API 호출에 사용하는 fetch 래퍼: 토큰 첨부 + 401 시 전역 이벤트(rag:unauthorized) 발행 */
export async function f(input: string, init?: RequestInit): Promise<Response> {
  const token = getAdminToken();
  const headers = new Headers(init?.headers ?? {});
  if (token && !headers.has("Authorization")) headers.set("Authorization", `Bearer ${token}`);
  const res = await fetch(input, { ...init, headers });
  if (res.status === 401 && typeof window !== "undefined") window.dispatchEvent(new CustomEvent("rag:unauthorized"));
  return res;
}

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

export type SearchTestResult = Source & {
  rank: number;
  content: string;
  passes_threshold: boolean;
  bm25_score: number | null;
  rerank_score: number | null;
  fused_score: number | null;
};

export type SearchTestResponse = {
  query: string;
  normalized_query: string;
  rewritten_query: string | null;
  search_query: string;
  multi_queries: string[];
  retrieval_mode: string;
  reranker: string;
  threshold: number;
  passes_threshold: boolean;
  top_score: number;
  elapsed_ms: number;
  embedding_provider: string;
  indexed_chunks: number;
  hit: { top1: boolean; top3: boolean; top5: boolean; rank: number | null } | null;
  results: SearchTestResult[];
};

export type TurnLog = {
  id: string;
  conversation_id: string;
  message_id: string;
  user_query: string;
  rewritten_query: string | null;
  retrieved: Source[];
  answer: string | null;
  answerable: boolean | null;
  llm_provider: string | null;
  embedding_provider: string | null;
  retrieval_ms: number | null;
  llm_ms: number | null;
  total_ms: number | null;
  feedback: "positive" | "negative" | null;
  feedback_reason: string | null;
  created_at: string;
};

export type LogsQuery = {
  limit?: number;
  offset?: number;
  date_from?: string;
  date_to?: string;
  answerable?: boolean;
  feedback?: "positive" | "negative" | "none";
  q?: string;
};

export type LogsPage = { items: TurnLog[]; total: number; limit: number; offset: number };

export type ConversationOut = { conversation_id: string; messages: { id: string; role: string; content: string; sources: Source[]; answerable: boolean | null; created_at: string }[] };

export function logsQueryString(q: Record<string, string | number | boolean | undefined | null>): string {
  const p = new URLSearchParams();
  Object.entries(q).forEach(([k, v]) => {
    if (v === undefined || v === null || v === "") return;
    p.set(k, String(v));
  });
  return p.toString();
}

export type StatsKpi = {
  questions: number; answered: number; unanswered: number;
  answer_rate: number | null; no_answer_rate: number | null;
  feedback_count: number; positive_rate: number | null; negative_rate: number | null;
  conversations: number; avg_turns: number | null;
  avg_total_ms: number | null; avg_retrieval_ms: number | null; avg_llm_ms: number | null;
};

export type StatsOverview = {
  range: { from: string; to: string; days: number; prev_from: string; prev_to: string };
  kpi: StatsKpi;
  kpi_prev: StatsKpi;
  delta: Record<"questions" | "answer_rate" | "no_answer_rate" | "positive_rate" | "avg_total_ms" | "conversations", number | null>;
  daily: { date: string; questions: number; answered: number; unanswered: number; positive: number; negative: number }[];
  categories: { category: string; count: number; share: number | null }[];
  feedback: { positive: number; negative: number; none: number; total: number };
  top_questions: { question: string; category: string; count: number; unanswered_rate: number | null }[];
};

export type UnansweredItem = {
  key: string; question: string; count: number; share: number | null; growth: number | null; last_at: string;
  top_score: number | null; category: string; recommendation: "new_document" | "improve_document";
  status: "open" | "resolved"; note: string | null; conversation_id: string; message_id: string;
};

export type StatsUnanswered = {
  range: { from: string; to: string; days: number };
  kpi: { unanswered: number; unanswered_prev: number; growth: number | null; rate: number | null; rate_prev: number | null;
    questions: number; distinct: number; resolved: number; resolved_rate: number | null };
  top: UnansweredItem[];
  daily: { date: string; unanswered: number }[];
  categories: { category: string; count: number; share: number | null }[];
  recommendations: { new_document: number; improve_document: number; faq_candidates: number };
};

export type Inquiry = { id: string; conversation_id: string | null; message_id: string | null; kind: "inquiry" | "agent"; contact: string | null; content: string; status: "open" | "done"; created_at: string };

export type StatsQuery = { date_from?: string; date_to?: string; tz_offset?: number };

export type Health = {
  status: string;
  db_backend: string;
  db_ok: boolean;
  admin_auth: boolean;
  retrieval_mode?: string;
  reranker?: string;
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

/** 무료 호스팅(Render)은 라우팅 전파/콜드스타트 중 일시적으로 404/502/503을 돌려줄 수 있어 짧게 재시도한다. */
async function fetchWithRetry(input: string, init: RequestInit | undefined, retries: number, delayMs: number): Promise<Response> {
  let last: unknown;
  for (let i = 0; i <= retries; i++) {
    try {
      const res = await f(input, init);
      if (res.ok || ![404, 502, 503, 504].includes(res.status) || i === retries) return res;
      last = new Error(`${res.status}`);
    } catch (e) {
      last = e;
      if (i === retries) throw e;
    }
    await new Promise((r) => setTimeout(r, delayMs * (i + 1)));
  }
  throw last instanceof Error ? last : new Error(String(last));
}

export const api = {
  health: () => fetchWithRetry(`${API_URL}/api/health`, { cache: "no-store" }, 2, 800).then(j<Health>),

  adminMe: () => f(`${API_URL}/api/admin/me`, { cache: "no-store" }).then(j<{ ok: boolean; role: string }>),
  downloadLogsCsv: async (q: LogsQuery) => {
    const res = await f(`${API_URL}/api/logs/export.csv?${logsQueryString(q)}`);
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    const blob = await res.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "conversation-logs.csv";
    a.click();
    URL.revokeObjectURL(a.href);
  },
  statsOverview: (q: StatsQuery) => f(`${API_URL}/api/stats/overview?${logsQueryString(q)}`, { cache: "no-store" }).then(j<StatsOverview>),
  statsUnanswered: (q: StatsQuery & { top_n?: number }) => f(`${API_URL}/api/stats/unanswered?${logsQueryString(q)}`, { cache: "no-store" }).then(j<StatsUnanswered>),
  patchUnanswered: (key: string, body: { status: "open" | "resolved"; note?: string | null }) =>
    f(`${API_URL}/api/stats/unanswered/${encodeURIComponent(key)}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).then(j<unknown>),
  createInquiry: (body: { conversation_id?: string | null; message_id?: string | null; kind: "inquiry" | "agent"; contact?: string | null; content: string }) =>
    f(`${API_URL}/api/inquiries`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).then(j<Inquiry>),
  listInquiries: (status?: "open" | "done") => f(`${API_URL}/api/inquiries${status ? `?status=${status}` : ""}`, { cache: "no-store" }).then(j<Inquiry[]>),
  patchInquiry: (id: string, status: "open" | "done") =>
    f(`${API_URL}/api/inquiries/${id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status }) }).then(j<unknown>),

  listLogs: (q: LogsQuery) => f(`${API_URL}/api/logs?${logsQueryString(q)}`, { cache: "no-store" }).then(j<LogsPage>),
  getLog: (messageId: string) => f(`${API_URL}/api/logs/${messageId}`, { cache: "no-store" }).then(j<TurnLog>),
  getConversation: (id: string) => f(`${API_URL}/api/conversations/${id}`, { cache: "no-store" }).then(j<ConversationOut>),

  searchTest: (body: { query: string; top_k?: number; previous_query?: string | null; expected_document_id?: string | null; use_multi_query?: boolean }) =>
    f(`${API_URL}/api/search/test`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then(j<SearchTestResponse>),

  chat: (message: string, conversation_id?: string | null) =>
    f(`${API_URL}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, conversation_id: conversation_id ?? null }),
    }).then(j<ChatResponse>),

  feedback: (message_id: string, rating: "positive" | "negative", reason?: string) =>
    f(`${API_URL}/api/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message_id, rating, reason }),
    }).then(j<{ ok: boolean }>),

  listDocuments: () => f(`${API_URL}/api/knowledge`, { cache: "no-store" }).then(j<DocumentItem[]>),
  getChunks: (id: string) => f(`${API_URL}/api/knowledge/${id}/chunks`, { cache: "no-store" }).then(j<ChunkItem[]>),
  uploadDocument: (form: FormData) => f(`${API_URL}/api/knowledge`, { method: "POST", body: form }).then(j<DocumentItem>),
  deleteDocument: (id: string) => f(`${API_URL}/api/knowledge/${id}`, { method: "DELETE" }).then(j<void>),
  reindexDocument: (id: string) => f(`${API_URL}/api/knowledge/${id}/reindex`, { method: "POST" }).then(j<DocumentItem>),
  patchDocument: (id: string, patch: Partial<Pick<DocumentItem, "status" | "title" | "category" | "version">>) =>
    f(`${API_URL}/api/knowledge/${id}`, {
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
  const res = await f(`${API_URL}/api/chat/stream`, {
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
