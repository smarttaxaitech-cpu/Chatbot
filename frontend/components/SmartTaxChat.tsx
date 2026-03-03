"use client";

import React, { useMemo, useState, useRef, useEffect } from "react";
import TaxSummaryDashboard from "./TaxSummaryDashboard";
import ExpensePieChart from "./ExpensePieChart";

function cx(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}

type UIMessage = {
  id: string; // UI id
  role: "bot" | "user";
  text: string;
  conversationId?: string; // from backend
  backendMessageId?: string; // assistant_message_id
};

const BACKEND = "http://127.0.0.1:8000";

function makeId() {
  // crypto.randomUUID() exists in modern browsers, but keep a fallback
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const c: any = globalThis.crypto;
  return typeof c?.randomUUID === "function"
    ? c.randomUUID()
    : `${Date.now()}-${Math.random()}`;
}

export default function SmartTaxChat({
  firstName,
  onReset,
}: {
  firstName: string;
  onReset: () => void;
}) {
  const quickPills = useMemo(
    () => ["Freelancers", "Creators", "Self-employed"],
    [],
  );
  const TYPING_TEXT = "...";

  const [input, setInput] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);

  // For optional comment UI on thumbs down
  const [commentBoxFor, setCommentBoxFor] = useState<string | null>(null);
  const [commentText, setCommentText] = useState("");
  const [lastIncome, setLastIncome] = useState<number | null>(null);
  const [lastExpenses, setLastExpenses] = useState<number>(0);

  // Track feedback state per backend message id (disable after voting)
  const [feedbackByMsg, setFeedbackByMsg] = useState<
    Record<string, { rating: "up" | "down" | null; submitting: boolean }>
  >({});

  const [messages, setMessages] = useState<UIMessage[]>([
    {
      id: "welcome",
      role: "bot",
      text: `Hi ${firstName}! 👋 Ask me anything about deductions, filing, or expenses.`,
    },
  ]);

  const messagesContainerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (messagesContainerRef.current) {
      messagesContainerRef.current.scrollTop =
        messagesContainerRef.current.scrollHeight;
    }
  }, [messages]);

  const [file, setFile] = useState<File | null>(null);
  const [uploadResult, setUploadResult] = useState<any>(null);
  const [calcResult, setCalcResult] = useState<any>(null);

  const [activeTab, setActiveTab] = useState<"chat" | "expenses" | "summary">(
    "chat",
  );

  const [income, setIncome] = useState("");
  const [expenses, setExpenses] = useState<any[]>([]);
  const totalExpenses = uploadResult?.total_uploaded ?? 0;

  const cleanName = firstName?.trim() || "";

  // -------------------------
  // Helpers
  // -------------------------
  async function ensureConversationId(): Promise<string> {
    if (conversationId) return conversationId;

    const newId = crypto.randomUUID();
    setConversationId(newId);
    return newId;
  }

  function parseIncome(raw: string): number {
    const cleaned = (raw || "").replace(/,/g, "").trim();
    const n = Number(cleaned);
    if (!Number.isFinite(n) || n < 0) return NaN;
    return n;
  }

  function parseAmountToken(token: string): number {
    // Handles: 90k, 1.5m, $5,000, 5000
    const t = token.trim().toLowerCase().replace(/\$/g, "").replace(/,/g, "");
    const m = t.match(/^(\d+(\.\d+)?)(k|m)?$/i);
    if (!m) return NaN;

    let n = Number(m[1]);
    const suffix = m[3];
    if (suffix === "k") n *= 1000;
    if (suffix === "m") n *= 1000000;

    return n;
  }

  function looksNumericHeavy(text: string, hasLastIncome: boolean) {
    const lower = text.toLowerCase();
    const tokens = lower.match(/\$?\d[\d,]*(?:\.\d+)?[km]?/g) || [];

    // ---- hard exclusions: NOT tax estimate requests ----
    if (
      /(break[-\s]?even|subscribers?|customers?|pricing|margin)/.test(lower) ||
      /(1099|w-9|w9|1099-nec|issue a 1099|send a 1099)/.test(lower) ||
      /(deductible\?|is .* deductible|can i deduct)/.test(lower)
    ) {
      return false;
    }

    const hasIncomeSignal =
      /(made|income|earned|revenue|1099|freelancing|profit)/.test(lower);
    const hasTaxSignal =
      /(rough tax|estimate|how much tax|tax estimate|total tax|self employment tax|income tax)/.test(
        lower,
      );
    const hasExpenseSignal = /(spent|expenses?|cost|paid|charged)/.test(lower);

    // Must have numbers
    if (tokens.length === 0) return false;

    // Tax-estimate intent: income + optionally expenses
    if (hasIncomeSignal) return true;

    // Additive expenses only if user already gave income earlier
    if (hasLastIncome && hasExpenseSignal) return true;

    // If they explicitly ask for tax estimate, allow
    if (hasTaxSignal) return true;

    return false;
  }

  function extractFinanceData(text: string) {
    const lower = text.toLowerCase();

    const rawTokens = lower.match(/\$?\d[\d,]*(?:\.\d+)?[km]?/g) || [];
    const values = rawTokens
      .map(parseAmountToken)
      .filter((n) => Number.isFinite(n));

    const incomeKw = /(made|income|earned)/;
    const expenseKw = /(expense|expenses|spent|cost|paid|deduct)/;

    const mentionsIncome = incomeKw.test(lower);
    const mentionsExpense = expenseKw.test(lower);

    const spentMatch = lower.match(
      /(?:spent|expenses?|cost|paid)\s*\$?\s*(\d[\d,]*(?:\.\d+)?[km]?)/,
    );
    const madeMatch = lower.match(
      /(?:made|earned|income)\s*\$?\s*(\d[\d,]*(?:\.\d+)?[km]?)/,
    );

    const incomeVal = madeMatch
      ? parseAmountToken(madeMatch[1])
      : mentionsIncome
        ? (values[0] ?? 0)
        : 0;

    const expenseVal = spentMatch
      ? parseAmountToken(spentMatch[1])
      : mentionsExpense
        ? // If user mentioned income AND expenses but provided only ONE number
          // (ex: "I made 60000. No expenses.") → expenses must be 0 unless explicitly given.
          madeMatch && !spentMatch && values.length === 1
          ? 0
          : values.length >= 2
            ? (values[1] ?? 0)
            : (values[0] ?? 0)
        : 0;

    const isAdditiveExpense =
      /add( another)?/.test(lower) &&
      /(expense|expenses|spent|cost|paid|deduct)/.test(lower);

    return {
      income: Number.isFinite(incomeVal) ? incomeVal : 0,
      expenses: Number.isFinite(expenseVal) ? expenseVal : 0,
      mentionsIncome,
      mentionsExpense,
      isAdditiveExpense,
    };
  }

  async function upsertIncome(convId: string, amount: number) {
    const resp = await fetch(`${BACKEND}/income/add`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        conversation_id: convId,
        income_sources: [{ type: "1099", amount, description: "Freelance" }],
      }),
    });

    const txt = await resp.text();
    if (!resp.ok)
      throw new Error(`Income save failed (${resp.status}): ${txt}`);
  }

  // -------------------------
  // Feedback
  // -------------------------
  async function sendFeedback(params: {
    conversationId: string;
    messageId: string;
    rating: "up" | "down";
    comment?: string;
  }) {
    const resp = await fetch(`${BACKEND}/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        conversation_id: params.conversationId,
        message_id: params.messageId,
        rating: params.rating,
        comment: params.comment ?? null,
      }),
    });

    if (!resp.ok) throw new Error(await resp.text());
  }

  async function handleFeedback(
    m: UIMessage,
    rating: "up" | "down",
    comment?: string,
  ) {
    const msgId = m.backendMessageId;
    const convId = m.conversationId;

    if (!msgId || !convId) return;

    const current = feedbackByMsg[msgId];
    if (current?.submitting) return;
    if (current?.rating) return;

    setFeedbackByMsg((prev) => ({
      ...prev,
      [msgId]: { rating, submitting: true },
    }));

    try {
      await sendFeedback({
        conversationId: convId,
        messageId: msgId,
        rating,
        comment,
      });

      setFeedbackByMsg((prev) => ({
        ...prev,
        [msgId]: { rating, submitting: false },
      }));

      setCommentBoxFor(null);
      setCommentText("");
    } catch (e: any) {
      setFeedbackByMsg((prev) => ({
        ...prev,
        [msgId]: { rating: null, submitting: false },
      }));
      alert(e?.message ?? "Feedback failed");
    }
  }

  // -------------------------
  // RAG answer call (Layer 4)
  // -------------------------
  async function askRag(question: string, convId: string) {
    const resp = await fetch(`${BACKEND}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        conversation_id: convId,
        message: question,
        history: [],
      }),
    });

    const raw = await resp.text();
    if (!resp.ok) throw new Error(`HTTP ${resp.status}: ${raw}`);

    return JSON.parse(raw);
  }

  function formatCitations(cites: any[] | undefined) {
    if (!cites || !Array.isArray(cites) || cites.length === 0) return "";
    const lines = cites.slice(0, 2).map((c) => {
      const pages =
        c.page_start != null
          ? ` (p. ${c.page_start}${c.page_end ? `–${c.page_end}` : ""})`
          : "";
      return `- ${c.source}${pages}`;
    });
    return `\n\nSources:\n${lines.join("\n")}`;
  }

  // -------------------------
  // Chat
  // -------------------------
  async function send() {
    const t = input.trim();
    if (!t) return;

    const userText = t;
    setInput("");

    const typingId = makeId();
    const userMsgId = makeId();

    setMessages((prev) => [
      ...prev,
      { id: userMsgId, role: "user", text: userText },
      { id: typingId, role: "bot", text: TYPING_TEXT },
    ]);

    try {
      // Keep conversation id for other features (calc/upload/report). For pure RAG answer, not required,
      // but calling it is safe and keeps your app consistent.
      const convId = await ensureConversationId();

      // If numeric-heavy -> use your deterministic calc flow (unchanged)
      if (looksNumericHeavy(userText, lastIncome !== null)) {
        const parsed = extractFinanceData(userText);

        const incomeToUse = parsed.mentionsIncome
          ? parsed.income
          : (lastIncome ?? 0);

        let expensesToUse = parsed.expenses;

        if (parsed.mentionsExpense) {
          if (parsed.isAdditiveExpense) {
            expensesToUse = lastExpenses + parsed.expenses;
            setLastExpenses(expensesToUse);
          } else {
            setLastExpenses(parsed.expenses);
            expensesToUse = parsed.expenses;
          }
        } else {
          expensesToUse = 0;
        }

        if (parsed.mentionsIncome) setLastIncome(parsed.income);

        const res = await fetch(`${BACKEND}/calc/estimate`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            conversation_id: convId,
            income_sources: [
              {
                type: "1099",
                amount: incomeToUse,
                description: "Detected income",
              },
            ],
            expenses: expensesToUse
              ? [{ category: "general", amount: expensesToUse }]
              : [],
            assumptions: { assumed_marginal_rate: 0.22 },
          }),
        });

        const raw = await res.text();
        if (!res.ok) throw new Error(raw);

        const data = JSON.parse(raw);

        const formatted =
          `Net Business Income: $${data.net_business_income}\n\n` +
          `Self-Employment Tax: $${data.self_employment_tax}\n\n` +
          `Income Tax Estimate: $${data.income_tax}\n\n` +
          `Total Estimated Tax: $${data.total_tax}`;

        setMessages((prev) =>
          prev.map((m) =>
            m.id === typingId
              ? {
                  ...m,
                  text: formatted,
                  conversationId: convId,
                  backendMessageId: `calc_${typingId}`, // dummy id for UI
                }
              : m,
          ),
        );

        return;
      }

      // ✅ Normal questions -> Layer 4 RAG
      const rag = await askRag(userText, convId);

      const answerText =
        (rag.answer_text ?? "No answer received.") +
        formatCitations(rag.citations);

      setMessages((prev) =>
        prev.map((m) =>
          m.id === typingId
            ? {
                ...m,
                text: answerText,
                conversationId: convId, // keep for consistency
                // backendMessageId is not returned by /rag/answer, so feedback UI won't show for this
              }
            : m,
        ),
      );
    } catch (error: any) {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === typingId
            ? {
                ...m,
                text: `⚠️ Could not reach backend: ${error?.message ?? ""}`,
              }
            : m,
        ),
      );
    }
  }

  // -------------------------
  // Expenses Upload
  // -------------------------
  async function uploadExpenses() {
    if (!file) {
      alert("Please choose a CSV file.");
      return;
    }

    try {
      const convId = await ensureConversationId();

      const formData = new FormData();
      formData.append("file", file);

      const res = await fetch(
        `${BACKEND}/expenses/upload?conversation_id=${convId}`,
        { method: "POST", body: formData },
      );

      const raw = await res.text();
      if (!res.ok) {
        alert(`Upload failed (${res.status}): ${raw}`);
        return;
      }

      const data = JSON.parse(raw);
      setUploadResult(data);
      setExpenses(data.expenses ?? data.items ?? []);
    } catch (e: any) {
      alert(e?.message ?? "Upload failed");
    }
  }

  // -------------------------
  // Tax Estimate
  // -------------------------
  async function calculateTaxes() {
    try {
      const convId = await ensureConversationId();

      const incomeAmount = parseIncome(income);
      if (!Number.isFinite(incomeAmount)) {
        alert("Please enter a valid income number (example: 60000).");
        return;
      }

      await upsertIncome(convId, incomeAmount);

      const res = await fetch(`${BACKEND}/calc/estimate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          conversation_id: convId,
          income: Number(income),
          expenses: [],
          home_office_sqft: null,
          vehicle_business_use_percent: null,
          assumptions: { assumed_marginal_rate: 0.22 },
        }),
      });

      const raw = await res.text();
      if (!res.ok) {
        alert(`Calc failed (${res.status}): ${raw}`);
        return;
      }

      const data = JSON.parse(raw);
      setCalcResult(data);
    } catch (e: any) {
      alert(e?.message ?? "Calc error");
    }
  }

  // -------------------------
  // Download Report
  // -------------------------
  async function downloadReport() {
    if (!conversationId) {
      alert("Start a conversation first.");
      return;
    }

    const res = await fetch(`${BACKEND}/generate-report/${conversationId}`, {
      method: "POST",
    });

    if (!res.ok) {
      const errText = await res.text();
      alert(`Report failed (${res.status}): ${errText}`);
      return;
    }

    const ct = res.headers.get("content-type") || "";
    if (!ct.includes("application/pdf")) {
      const bad = await res.text();
      alert(`Not a PDF. content-type=${ct}\n\n${bad}`);
      return;
    }

    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);

    const a = document.createElement("a");
    a.href = url;
    a.download = "SmartTax_Report.pdf";
    a.click();

    window.URL.revokeObjectURL(url);
  }

  // -------------------------
  // UI
  // -------------------------
  return (
    <div className="min-h-screen w-full bg-black text-white overflow-hidden">
      {/* Header */}
      <div className="h-16 flex items-center justify-between px-6 border-b border-white/10 bg-black/60 backdrop-blur">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-xl bg-white/5 border border-white/10 flex items-center justify-center overflow-hidden">
            <img
              src="/logo.png"
              alt="SmartTax AI Logo"
              className="h-7 w-7 object-contain"
            />
          </div>

          <div className="leading-tight">
            <div className="text-sm font-semibold">SmartTax AI ✨</div>
            <div className="text-xs text-white/60">
              AI-Powered Tax Intelligence
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={onReset}
            className="text-xs text-white/60 hover:text-white/85 transition"
            title="Reset onboarding"
          >
            Reset
          </button>

          <a
            href="https://smarttaxai-waitlist.com/waitlist"
            target="_blank"
            rel="noopener noreferrer"
            className="h-10 px-4 rounded-full bg-violet-600 hover:bg-violet-500 transition font-semibold flex items-center justify-center"
          >
            Early Access
          </a>
        </div>
      </div>

      {/* Background */}
      <div className="relative h-[calc(100vh-64px)] overflow-hidden">
        <div className="absolute inset-0 pointer-events-none z-0">
          <div className="absolute inset-0 opacity-[0.08] bg-[linear-gradient(to_right,#ffffff_1px,transparent_1px),linear-gradient(to_bottom,#ffffff_1px,transparent_1px)] bg-size-[80px_80px]" />
          <div className="absolute inset-0 opacity-30 bg-[radial-gradient(#ffffff_1px,transparent_1px)] bg-size-[70px_70px]" />
        </div>

        {/* Main layout */}
        <div className="relative z-10 h-full flex flex-col">
          <div className="flex-1 overflow-y-auto">
            <div className="max-w-6xl mx-auto px-6 pt-16 pb-10">
              <div className="flex flex-col items-center text-center">
                <div className="h-16 w-16 rounded-2xl bg-violet-600/15 border border-violet-400/20 flex items-center justify-center shadow-[0_20px_60px_rgba(124,58,237,0.12)]">
                  <img
                    src="/logo.png"
                    alt="SmartTax AI Logo"
                    className="h-9 w-9 object-contain"
                  />
                </div>

                {activeTab === "expenses" && (
                  <h1 className="mt-6 text-3xl md:text-4xl font-bold text-center text-purple-400">
                    Expenses
                  </h1>
                )}

                {activeTab === "summary" && (
                  <h1 className="mt-6 text-3xl md:text-4xl font-bold text-center text-purple-400">
                    Summary
                  </h1>
                )}

                {/* Tabs */}
                <div className="mt-6 flex items-center justify-center gap-2 text-xs">
                  {[
                    { key: "chat", label: "Chat" },
                    { key: "expenses", label: "Expenses" },
                    { key: "summary", label: "Summary" },
                  ].map((t) => (
                    <button
                      key={t.key}
                      onClick={() => setActiveTab(t.key as any)}
                      className={cx(
                        "px-4 py-2 rounded-full border transition",
                        activeTab === t.key
                          ? "bg-violet-600 border-violet-400 text-white"
                          : "bg-white/5 border-white/10 text-white/60 hover:bg-white/10",
                      )}
                    >
                      {t.label}
                    </button>
                  ))}
                </div>

                {/* CHAT */}
                {activeTab === "chat" && (
                  <div className="mt-10 w-full max-w-3xl">
                    <div className="relative z-10 pointer-events-auto rounded-3xl border border-white/10 bg-black/30 backdrop-blur-xl overflow-hidden">
                      <div
                        ref={messagesContainerRef}
                        className="max-h-80 overflow-y-auto px-5 py-5 space-y-3"
                      >
                        {messages.map((m) => {
                          const st = m.backendMessageId
                            ? feedbackByMsg[m.backendMessageId]
                            : undefined;
                          const alreadyVoted = !!st?.rating;
                          const submitting = !!st?.submitting;
                          const disabled = alreadyVoted || submitting;

                          return (
                            <div
                              key={m.id}
                              className={cx(
                                "w-full flex",
                                m.role === "user"
                                  ? "justify-end"
                                  : "justify-start",
                              )}
                            >
                              <div
                                className={cx(
                                  "max-w-[85%] rounded-2xl px-4 py-3 text-sm",
                                  m.role === "user"
                                    ? "bg-violet-600 text-white"
                                    : "bg-white/5 border border-white/10 text-white/85",
                                )}
                              >
                                <div className="whitespace-pre-wrap leading-relaxed">
                                  {m.text}
                                </div>

                                {/* feedback only works if backend gives ids */}
                                {m.role === "bot" &&
                                  m.backendMessageId &&
                                  m.conversationId && (
                                    <div className="mt-2">
                                      <div className="flex gap-2 text-xs items-center">
                                        <button
                                          type="button"
                                          disabled={disabled}
                                          className={cx(
                                            "px-2 py-1 rounded bg-white/10 hover:bg-white/20 cursor-pointer",
                                            disabled &&
                                              "opacity-40 cursor-not-allowed hover:bg-white/10",
                                            st?.rating === "up" &&
                                              "ring-2 ring-violet-400/60",
                                          )}
                                          onClick={() =>
                                            handleFeedback(m, "up")
                                          }
                                        >
                                          👍
                                        </button>

                                        <button
                                          type="button"
                                          disabled={disabled}
                                          className={cx(
                                            "px-2 py-1 rounded bg-white/10 hover:bg-white/20 cursor-pointer",
                                            disabled &&
                                              "opacity-40 cursor-not-allowed hover:bg-white/10",
                                            st?.rating === "down" &&
                                              "ring-2 ring-violet-400/60",
                                          )}
                                          onClick={() => {
                                            if (disabled) return;
                                            setCommentBoxFor(
                                              m.backendMessageId!,
                                            );
                                            setCommentText("");
                                          }}
                                        >
                                          👎
                                        </button>

                                        {submitting && (
                                          <span className="text-white/50">
                                            Saving…
                                          </span>
                                        )}
                                      </div>

                                      {commentBoxFor === m.backendMessageId &&
                                        !alreadyVoted && (
                                          <div className="mt-3 space-y-2 text-left">
                                            <textarea
                                              value={commentText}
                                              onChange={(e) =>
                                                setCommentText(e.target.value)
                                              }
                                              placeholder="Optional: tell us what was wrong..."
                                              className="w-full rounded-lg bg-black/40 border border-white/10 p-2 text-xs outline-none focus:ring-2 focus:ring-violet-500/30"
                                              rows={3}
                                              autoFocus
                                            />

                                            <div className="flex gap-2">
                                              <button
                                                type="button"
                                                className="px-3 py-1 text-xs rounded bg-violet-600 hover:bg-violet-500"
                                                onClick={() =>
                                                  handleFeedback(
                                                    m,
                                                    "down",
                                                    commentText,
                                                  )
                                                }
                                              >
                                                Submit
                                              </button>

                                              <button
                                                type="button"
                                                className="px-3 py-1 text-xs rounded bg-white/10 hover:bg-white/20"
                                                onClick={() => {
                                                  setCommentBoxFor(null);
                                                  setCommentText("");
                                                }}
                                              >
                                                Cancel
                                              </button>
                                            </div>
                                          </div>
                                        )}
                                    </div>
                                  )}
                              </div>
                            </div>
                          );
                        })}
                      </div>

                      {/* Input */}
                      <div className="border-t border-white/10 px-4 py-3">
                        <div className="flex items-center gap-3">
                          <input
                            value={input}
                            onChange={(e) => setInput(e.target.value)}
                            placeholder="Ask about deductions, filing, deadlines..."
                            className="flex-1 h-11 rounded-2xl bg-white/5 border border-white/10 px-4 text-sm text-white placeholder:text-white/35 outline-none focus:ring-2 focus:ring-violet-500/30"
                            onKeyDown={(e) => {
                              if (e.key === "Enter") send();
                            }}
                          />

                          <button
                            type="button"
                            onClick={send}
                            className="h-11 w-11 rounded-2xl bg-violet-600 hover:bg-violet-500 transition flex items-center justify-center"
                            title="Send"
                          >
                            ➤
                          </button>
                        </div>

                        <div className="mt-2 text-center text-xs text-white/45">
                          🔒 End-to-end encrypted · Your data stays private
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {/* EXPENSES */}
                {activeTab === "expenses" && (
                  <div className="mt-10 w-full max-w-3xl p-5 rounded-3xl bg-white/5 border border-white/10">
                    <div className="text-sm font-semibold mb-3">
                      Upload Expense CSV
                    </div>

                    <label className="mt-3 inline-flex items-center gap-2 cursor-pointer px-4 py-2 rounded-xl bg-white/10 hover:bg-white/20 transition text-xs">
                      📄 Choose CSV File
                      <input
                        type="file"
                        accept=".csv"
                        onChange={(e) => setFile(e.target.files?.[0] || null)}
                        className="hidden"
                      />
                    </label>

                    <div className="mt-2 text-xs text-white/60">
                      {file ? `Selected: ${file.name}` : "No file selected"}
                    </div>

                    <button
                      onClick={uploadExpenses}
                      className="mt-4 px-4 py-2 bg-violet-600 rounded-xl text-sm"
                    >
                      Upload
                    </button>

                    {uploadResult && (
                      <div className="mt-4 text-xs space-y-1">
                        <div>
                          Total Uploaded: ${uploadResult.total_uploaded}
                        </div>
                        {Object.entries(
                          uploadResult.category_breakdown ?? {},
                        ).map(([cat, amt]: any) => (
                          <div key={cat}>
                            {cat}: ${amt}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {/* SUMMARY */}
                {activeTab === "summary" && (
                  <div className="mt-12 w-full max-w-6xl mx-auto grid gap-6 lg:grid-cols-2 items-start">
                    <div className="p-5 rounded-3xl bg-white/5 border border-white/10 space-y-3">
                      <div className="text-xs text-white/60">Annual Income</div>

                      <input
                        value={income}
                        onChange={(e) => setIncome(e.target.value)}
                        placeholder="Enter income (example: 60000)"
                        className="w-full h-11 px-4 rounded-xl bg-black/40 border border-white/10 text-sm outline-none focus:ring-2 focus:ring-violet-500/30"
                      />

                      <div className="text-xs text-white/50">
                        Uploaded expenses total: ${totalExpenses}
                      </div>

                      <button
                        onClick={calculateTaxes}
                        className="px-4 py-2 bg-violet-600 rounded-xl text-sm hover:bg-violet-500 transition"
                      >
                        Calculate Estimate
                      </button>

                      {calcResult && (
                        <div className="text-xs space-y-1 pt-2">
                          <div>Total Income: ${calcResult.total_income}</div>
                          <div>
                            Total Expenses: ${calcResult.total_expenses}
                          </div>
                          <div>
                            Net Business Income: $
                            {calcResult.net_business_income}
                          </div>
                          <div>
                            Self Employment Tax: $
                            {calcResult.self_employment_tax}
                          </div>
                          <div>Income Tax: ${calcResult.income_tax}</div>
                          <div className="pt-1 font-semibold">
                            Total Estimated Tax: ${calcResult.total_tax}
                          </div>

                          <div className="pt-4">
                            <ExpensePieChart
                              data={calcResult.deductions_by_category || []}
                            />
                          </div>
                        </div>
                      )}

                      <button
                        onClick={downloadReport}
                        className="mt-2 px-4 py-2 bg-white/10 rounded-xl text-sm hover:bg-white/20 transition"
                      >
                        Download PDF Report
                      </button>
                    </div>

                    <div className="rounded-3xl bg-white/5 border border-white/10 overflow-hidden">
                      {calcResult ? (
                        <TaxSummaryDashboard data={calcResult} />
                      ) : null}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
