"use client";

import { useEffect, useState } from "react";
import { listDemoUsers, login, ask, DemoUser, AskResponse } from "../lib/api";

type Message = {
  role: "user" | "assistant";
  text: string;
  data?: AskResponse;
};

type ExamplePrompt = {
  question: string;
  /** What this question is meant to demonstrate. */
  hint: string;
};

/**
 * Demo prompts per role, mirroring the scenarios in DEMO_SCENARIOS.md.
 * The point of keying these by role is that the same question is expected to
 * behave DIFFERENTLY depending on who asks -- that contrast is the demo.
 */
const EXAMPLE_PROMPTS: Record<string, ExamplePrompt[]> = {
  Employee: [
    {
      question: "Can I work remotely from Turkey for 30 days?",
      hint: "Multi-document + version resolution (2026 supersedes 2025)",
    },
    {
      question: "What is the HR exception policy allowing up to 40 days of remote work?",
      hint: "Asks directly for HR-only content — should refuse without leaking it",
    },
    {
      question: "What are the salary bands for senior engineers?",
      hint: "Department-restricted document — should refuse",
    },
    {
      question: "Can I expense a home office chair?",
      hint: "Not covered by any policy — should abstain, not guess",
    },
  ],
  Manager: [
    {
      question: "How many days can I work abroad this year?",
      hint: "Version resolution — current policy, not the older one",
    },
    {
      question: "Can I work remotely from Spain for three weeks?",
      hint: "EU destination — no HR approval needed, unlike non-EU",
    },
    {
      question: "What is the HR exception policy for remote work days?",
      hint: "Managers are still not HR — should refuse",
    },
  ],
  HR: [
    {
      question: "Can I work remotely from Turkey for 30 days?",
      hint: "Same question as the Employee — HR also sees the 40-day exception",
    },
    {
      question: "What exceptions can be approved for remote work duration?",
      hint: "HR-only guideline, retrievable for this role",
    },
    {
      question: "What are the salary bands for senior engineers?",
      hint: "HR-only document, accessible here",
    },
  ],
  "Finance Admin": [
    {
      question: "What class of flight am I entitled to for a long-haul trip?",
      hint: "Clean single-source answer, no conflicts",
    },
    {
      question: "How soon must travel expenses be submitted?",
      hint: "Straightforward factual lookup",
    },
    {
      question: "What are the salary bands for senior engineers?",
      hint: "Finance is not HR — should refuse",
    },
  ],
};

export default function Home() {
  const [users, setUsers] = useState<DemoUser[]>([]);
  const [activeUserId, setActiveUserId] = useState<string>("");
  const [token, setToken] = useState<string>("");
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    listDemoUsers().then((u) => {
      setUsers(u);
      if (u.length > 0) switchUser(u[0].id);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function switchUser(userId: string) {
    setActiveUserId(userId);
    const t = await login(userId);
    setToken(t);
    setMessages([]);
  }

  async function handleAsk(preset?: string) {
    const q = (preset ?? question).trim();
    if (!q || !token || loading) return;
    setMessages((m) => [...m, { role: "user", text: q }]);
    setQuestion("");
    setLoading(true);
    try {
      const res = await ask(token, q);
      setMessages((m) => [...m, { role: "assistant", text: res.answer, data: res }]);
    } catch (e) {
      setMessages((m) => [...m, { role: "assistant", text: "Error contacting the copilot." }]);
    } finally {
      setLoading(false);
    }
  }

  const activeUser = users.find((u) => u.id === activeUserId);
  const examples = activeUser ? EXAMPLE_PROMPTS[activeUser.role] ?? [] : [];

  return (
    <main style={{ maxWidth: 820, margin: "0 auto", padding: "2rem 1.5rem" }}>
      <h1 style={{ fontSize: "1.4rem", marginBottom: "0.25rem" }}>Enterprise Policy Copilot</h1>
      <p style={{ color: "#9aa4b2", marginTop: 0, fontSize: "0.9rem" }}>
        Permission-aware RAG demo — same question, different role, different answer.
      </p>

      <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", margin: "1rem 0 1.5rem" }}>
        {users.map((u) => (
          <button
            key={u.id}
            onClick={() => switchUser(u.id)}
            style={{
              padding: "0.4rem 0.8rem",
              borderRadius: 8,
              border: u.id === activeUserId ? "1px solid #6ea8fe" : "1px solid #2a2f3a",
              background: u.id === activeUserId ? "#1b2740" : "#161a22",
              color: "#e6e6e6",
              cursor: "pointer",
              fontSize: "0.85rem",
            }}
          >
            {u.name} <span style={{ color: "#9aa4b2" }}>({u.role})</span>
          </button>
        ))}
      </div>

      {activeUser && (
        <div
          style={{
            fontSize: "0.8rem",
            color: "#9aa4b2",
            marginBottom: "1rem",
            display: "flex",
            alignItems: "center",
            gap: "0.75rem",
          }}
        >
          <span>
            Logged in as <strong>{activeUser.name}</strong> — {activeUser.role}, {activeUser.department},{" "}
            {activeUser.country}
          </span>
          {messages.length > 0 && (
            <button
              onClick={() => setMessages([])}
              style={{
                padding: "0.2rem 0.5rem",
                borderRadius: 6,
                border: "1px solid #2a2f3a",
                background: "transparent",
                color: "#6ea8fe",
                cursor: "pointer",
                fontSize: "0.75rem",
                fontFamily: "inherit",
              }}
            >
              Reset
            </button>
          )}
        </div>
      )}

      <div
        style={{
          border: "1px solid #2a2f3a",
          borderRadius: 12,
          minHeight: 320,
          padding: "1rem",
          marginBottom: "1rem",
          background: "#0b0e13",
        }}
      >
        {messages.length === 0 && (
          <div>
            <p style={{ color: "#6b7280", fontSize: "0.8rem", margin: "0 0 0.75rem" }}>
              Try one of these as <strong style={{ color: "#9aa4b2" }}>{activeUser?.role}</strong>:
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              {examples.map((ex, i) => (
                <button
                  key={i}
                  onClick={() => handleAsk(ex.question)}
                  disabled={loading}
                  style={{
                    textAlign: "left",
                    padding: "0.6rem 0.8rem",
                    borderRadius: 8,
                    border: "1px solid #2a2f3a",
                    background: "#12161f",
                    color: "#e6e6e6",
                    cursor: loading ? "default" : "pointer",
                    fontSize: "0.85rem",
                    fontFamily: "inherit",
                    lineHeight: 1.4,
                  }}
                >
                  {ex.question}
                  <span style={{ display: "block", color: "#6b7280", fontSize: "0.75rem", marginTop: "0.2rem" }}>
                    {ex.hint}
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} style={{ marginBottom: "1rem" }}>
            <div style={{ fontSize: "0.75rem", color: "#6b7280", marginBottom: "0.2rem" }}>
              {m.role === "user" ? "You" : "Copilot"}
            </div>
            <div
              style={{
                whiteSpace: "pre-wrap",
                background: m.role === "user" ? "#161a22" : "#141b2c",
                padding: "0.7rem 0.9rem",
                borderRadius: 8,
                fontSize: "0.92rem",
              }}
            >
              {m.text}
            </div>
            {m.data && m.data.citations.length > 0 && (
              <details style={{ marginTop: "0.4rem" }}>
                <summary style={{ fontSize: "0.78rem", color: "#6ea8fe", cursor: "pointer" }}>
                  Sources ({m.data.citations.length})
                  {m.data.has_version_conflict && !m.data.abstained
                    ? " — version conflict resolved"
                    : ""}
                </summary>
                <div style={{ marginTop: "0.4rem", display: "flex", flexDirection: "column", gap: "0.4rem" }}>
                  {m.data.citations.map((c, j) => (
                    <div
                      key={j}
                      style={{
                        border: "1px solid #2a2f3a",
                        borderRadius: 6,
                        padding: "0.5rem 0.7rem",
                        fontSize: "0.78rem",
                      }}
                    >
                      <div style={{ color: c.is_current_version ? "#8fd19e" : "#e0b34d", marginBottom: "0.2rem" }}>
                        {c.document_title} {c.is_current_version ? "(current)" : "(superseded)"}
                      </div>
                      <div style={{ color: "#9aa4b2" }}>{c.text}</div>
                    </div>
                  ))}
                </div>
              </details>
            )}
            {m.data?.abstained && (
              <div style={{ fontSize: "0.75rem", color: "#e0b34d", marginTop: "0.3rem" }}>
                (abstained — no verified answer available)
              </div>
            )}
          </div>
        ))}
        {loading && <div style={{ color: "#6b7280", fontSize: "0.85rem" }}>Thinking…</div>}
      </div>

      <div style={{ display: "flex", gap: "0.5rem" }}>
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleAsk()}
          placeholder="Ask a policy question…"
          style={{
            flex: 1,
            padding: "0.6rem 0.8rem",
            borderRadius: 8,
            border: "1px solid #2a2f3a",
            background: "#161a22",
            color: "#e6e6e6",
          }}
        />
        <button
          onClick={handleAsk}
          disabled={loading}
          style={{
            padding: "0.6rem 1.1rem",
            borderRadius: 8,
            border: "none",
            background: "#6ea8fe",
            color: "#0b0e13",
            fontWeight: 600,
            cursor: "pointer",
          }}
        >
          Ask
        </button>
      </div>
    </main>
  );
}
