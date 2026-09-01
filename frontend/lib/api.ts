const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type DemoUser = {
  id: string;
  name: string;
  role: string;
  department: string;
  country: string;
};

export type Citation = {
  document_title: string;
  is_current_version: boolean;
  text: string;
};

export type AskResponse = {
  answer: string;
  abstained: boolean;
  citations: Citation[];
  has_version_conflict: boolean;
  trace_id: string;
};

export async function listDemoUsers(): Promise<DemoUser[]> {
  const res = await fetch(`${API_URL}/demo/users`);
  if (!res.ok) throw new Error("Failed to load demo users");
  return res.json();
}

export async function login(userId: string): Promise<string> {
  const res = await fetch(`${API_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId }),
  });
  if (!res.ok) throw new Error("Login failed");
  const data = await res.json();
  return data.access_token;
}

export async function ask(token: string, question: string): Promise<AskResponse> {
  const res = await fetch(`${API_URL}/ask`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ question }),
  });
  if (!res.ok) throw new Error("Ask failed");
  return res.json();
}
