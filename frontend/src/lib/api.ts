/**
 * Universal AI Analyst - Frontend API Client & Typed Contracts
 * Connects Next.js to FastAPI Backend (REST & SSE)
 */

export interface User {
  id: string;
  email: string;
  name: string;
  role: "employee" | "unit_admin" | "super_admin" | "tech_admin";
  unit_id: string;
  status: string;
}

export interface ColumnProfile {
  name: string;
  inferred_type: string;
  null_count: number;
  unique_count: number;
  sample_values: string[];
  min?: number | null;
  max?: number | null;
  mean?: number | null;
}

export interface SchemaProfile {
  sheets?: string[];
  row_count?: number;
  column_count?: number;
  columns?: ColumnProfile[];
  error?: string;
}

export interface StoredFile {
  id: string;
  original_name: string;
  content_type: string;
  size_bytes: number;
  status: "pending_upload" | "uploaded" | "scanning" | "ingesting" | "ready" | "needs_mapping" | "error";
  schema_profile?: SchemaProfile;
  created_at: string;
}

export interface ChatSession {
  id: string;
  user_id: string;
  unit_id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ChatMessage {
  id: string;
  chat_id: string;
  user_id?: string;
  role: "user" | "assistant" | "system";
  content: string;
  attachments?: string[];
  file_ids?: string[];
  analysis_id?: string;
  created_at: string;
  metadata?: {
    result?: {
      columns: string[];
      rows: Record<string, any>[];
      duration_ms?: number;
      row_count?: number;
    };
    verification?: any;
    provenance?: any;
  };
}

export interface PolicyRule {
  rule_id: string;
  description: string;
  condition: {
    field: string;
    operator: string;
    value?: any;
    value_source?: string;
  };
  severity: "low" | "medium" | "high" | "critical";
}

export interface Policy {
  id: string;
  policy_code: string;
  title: string;
  department: string;
  unit_ids: string[];
  version: number;
  effective_from: string;
  effective_to?: string | null;
  description: string;
  rules: PolicyRule[];
  status: string;
}

export interface InterruptOption {
  id: string;
  label: string;
  value?: string;
}

export interface PendingInterruptPayload {
  interrupt_id: string;
  type: "choice" | "confirmation" | "free_text";
  reason: string;
  question: string;
  options: InterruptOption[];
  placeholder?: string;
  context?: Record<string, any>;
}

export interface PendingInterruptState {
  pending: boolean;
  analysis_id: string | null;
  thread_id?: string | null;
  interrupt: PendingInterruptPayload | null;
}

export interface AnalysisProvenance {
  source_files?: string[];
  source_sheets?: string[];
  evidence_rows?: number[];
  policy_code?: string;
  policy_version?: number;
  query_hash?: string;
  result_hash?: string;
  verification_status?: string;
}

export interface AnalysisResult {
  id: string;
  chat_id: string;
  message_id?: string;
  user_id: string;
  status: string;
  intent: string;
  question: string;
  plan?: any;
  result?: {
    engine?: string;
    columns?: string[];
    rows?: Record<string, any>[];
    total_violations?: number;
    evidence_rows?: number[];
    violations?: any[];
    rule_summaries?: any[];
    [key: string]: any;
  };
  verification?: {
    passed: boolean;
    checks: Record<string, boolean>;
    warnings?: string[];
  };
  provenance?: AnalysisProvenance;
  created_at: string;
  completed_at?: string;
}

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const TOKEN_KEY = "universal_analyst_token";

let inMemoryToken: string | null = null;

function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp(`(^| )${name}=([^;]+)`));
  return match ? decodeURIComponent(match[2]) : null;
}

export function getStoredToken(): string | null {
  if (inMemoryToken) return inMemoryToken;
  if (typeof window === "undefined") return null;
  return sessionStorage.getItem(TOKEN_KEY) || localStorage.getItem(TOKEN_KEY);
}

export function setStoredToken(token: string): void {
  inMemoryToken = token;
  if (typeof window !== "undefined") {
    // Store in short-lived sessionStorage to prevent persistent localStorage leakage
    sessionStorage.setItem(TOKEN_KEY, token);
  }
}

export function clearStoredToken(): void {
  inMemoryToken = null;
  if (typeof window !== "undefined") {
    sessionStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(TOKEN_KEY);
  }
}

async function fetchWithAuth(endpoint: string, options: RequestInit = {}): Promise<any> {
  const token = getStoredToken();
  const csrfToken = getCookie("csrf_token");
  const headers = new Headers(options.headers || {});

  if (!headers.has("Content-Type") && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  if (csrfToken) {
    headers.set("X-CSRF-Token", csrfToken);
  }

  const url = `${API_BASE_URL}${endpoint}`;
  const response = await fetch(url, {
    ...options,
    headers,
    credentials: "include", // Send secure HttpOnly cookies across requests
  });

  if (response.status === 401) {
    clearStoredToken();
    if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
      window.location.replace("/login");
    }
    throw new Error("Authentication session expired.");
  }

  if (!response.ok) {
    let errorMsg = `Request failed with status ${response.status}`;
    try {
      const errorJson = await response.json();
      if (errorJson.error?.message) {
        errorMsg = errorJson.error.message;
      } else if (errorJson.detail) {
        errorMsg = typeof errorJson.detail === "string" ? errorJson.detail : JSON.stringify(errorJson.detail);
      }
    } catch {}
    throw new Error(errorMsg);
  }

  if (response.status === 204) return null;
  return response.json();
}

export const api = {
  // Authentication
  async login(email: string, password: string): Promise<{ access_token: string; user: User }> {
    const res = await fetchWithAuth("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    if (res.access_token) {
      setStoredToken(res.access_token);
    }
    return res;
  },

  async register(data: { email: string; password: string; name: string; role?: string; unit_id?: string }): Promise<User> {
    return fetchWithAuth("/api/v1/auth/register", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  async getMe(): Promise<User> {
    return fetchWithAuth("/api/v1/auth/me");
  },

  async logout(): Promise<void> {
    try {
      await fetchWithAuth("/api/v1/auth/logout", { method: "POST" });
    } catch {}
    clearStoredToken();
  },

  // Files & Datasets
  async uploadFile(file: File): Promise<StoredFile> {
    const formData = new FormData();
    formData.append("file", file);
    return fetchWithAuth("/api/v1/files", {
      method: "POST",
      body: formData,
    });
  },

  async listFiles(): Promise<StoredFile[]> {
    return fetchWithAuth("/api/v1/files");
  },

  async getFile(fileId: string): Promise<StoredFile> {
    return fetchWithAuth(`/api/v1/files/${fileId}`);
  },

  async deleteFile(fileId: string): Promise<{ status: string; id: string }> {
    return fetchWithAuth(`/api/v1/files/${fileId}`, {
      method: "DELETE",
    });
  },

  // Chats & Conversations
  async createChat(title: string = "New Analysis"): Promise<ChatSession> {
    return fetchWithAuth("/api/v1/chats", {
      method: "POST",
      body: JSON.stringify({ title }),
    });
  },

  async listChats(): Promise<ChatSession[]> {
    return fetchWithAuth("/api/v1/chats");
  },

  async getChat(chatId: string): Promise<ChatSession> {
    return fetchWithAuth(`/api/v1/chats/${chatId}`);
  },

  async deleteChat(chatId: string): Promise<{ status: string; id: string }> {
    return fetchWithAuth(`/api/v1/chats/${chatId}`, {
      method: "DELETE",
    });
  },

  async getMessages(chatId: string): Promise<ChatMessage[]> {
    return fetchWithAuth(`/api/v1/chats/${chatId}/messages`);
  },

  async sendMessage(
    chatId: string,
    content: string,
    fileIds: string[] = []
  ): Promise<{ message_id: string; analysis_id: string; status: string }> {
    return fetchWithAuth(`/api/v1/chats/${chatId}/messages`, {
      method: "POST",
      body: JSON.stringify({ content, file_ids: fileIds }),
    });
  },

  // Policies
  async listPolicies(): Promise<Policy[]> {
    return fetchWithAuth("/api/v1/policies");
  },

  async getPolicy(policyId: string): Promise<Policy> {
    return fetchWithAuth(`/api/v1/policies/${policyId}`);
  },

  // Analysis & Verification
  async getAnalysis(analysisId: string): Promise<AnalysisResult> {
    return fetchWithAuth(`/api/v1/analysis/${analysisId}`);
  },

  async getPendingInterrupt(chatId: string): Promise<PendingInterruptState> {
    return fetchWithAuth(`/api/v1/chats/${chatId}/pending-interrupt`);
  },

  async resumeAnalysis(
    analysisId: string,
    interruptId: string,
    response: any
  ): Promise<any> {
    return fetchWithAuth(`/api/v1/analysis/${analysisId}/resume`, {
      method: "POST",
      body: JSON.stringify({ interrupt_id: interruptId, response }),
    });
  },

  async cancelAnalysis(analysisId: string): Promise<{ analysis_id: string; status: string }> {
    return fetchWithAuth(`/api/v1/analysis/${analysisId}/cancel`, {
      method: "POST",
    });
  },

  async submitAnalysisFeedback(
    analysisId: string,
    category: string,
    comment?: string,
    correction?: Record<string, any>
  ): Promise<any> {
    return fetchWithAuth(`/api/v1/analysis/${analysisId}/feedback`, {
      method: "POST",
      body: JSON.stringify({ category, comment, correction }),
    });
  },

  getEventsUrl(analysisId: string): string {
    return `${API_BASE_URL}/api/v1/analysis/${analysisId}/events`;
  },
};
