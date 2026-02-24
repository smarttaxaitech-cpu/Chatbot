"use client"; 


import React, { useMemo, useState, useRef, useEffect } from "react";

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

export default function SmartTaxChat({
  firstName,
  onReset,
}: {
  firstName: string;
  onReset: () => void;
}) {
  const quickPills = useMemo(() => ["Freelancers", "Creators", "Self-employed"], []);
  const TYPING_TEXT = "...";

  const [input, setInput] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);

  // For optional comment UI on thumbs down
  const [commentBoxFor, setCommentBoxFor] = useState<string | null>(null);
  const [commentText, setCommentText] = useState("");
  const [lastIncome, setLastIncome] = useState<number | null>(null);

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

  const [activeTab, setActiveTab] = useState<"chat" | "expenses" | "summary">("chat");

  const [income, setIncome] = useState("");
  const [expenses, setExpenses] = useState<any[]>([]);
  const totalExpenses = uploadResult?.total_uploaded ?? 0;
  const cleanName = firstName?.trim() || "";

  // -------------------------
  // Helpers
  // -------------------------
  async function ensureConversationId(): Promise<string> {
    if (conversationId) return conversationId;

    const resp = await fetch("http://127.0.0.1:8000/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: "start",
        history: [],
      }),
    });

    const raw = await resp.text();
    if (!resp.ok) throw new Error(`HTTP ${resp.status}: ${raw}`);

    const data = JSON.parse(raw);
    const convId = data.conversation_id as string;
    setConversationId(convId);
    return convId;
  }

  function parseIncome(raw: string): number {
    // allow "60,000" too
    const cleaned = (raw || "").replace(/,/g, "").trim();
    const n = Number(cleaned);
    if (!Number.isFinite(n) || n < 0) return NaN;
    return n;
  }

function looksNumericHeavy(text: string, hasLastIncome: boolean) {
  const numbers = text.match(/\d[\d,]*/g) || [];
  const hasDollar = text.includes("$");
  const lower = text.toLowerCase();

  const incomeKw = ["made", "income", "earned"].some(k => lower.includes(k));
  const expenseKw = ["expense", "expenses", "spent", "cost", "paid"].some(k => lower.includes(k));

  // 2+ numbers → likely "income + expenses" style
  if (numbers.length >= 2 && (hasDollar || incomeKw || expenseKw)) return true;

  // 1 number + income keyword → income-only message
  if (numbers.length >= 1 && incomeKw) return true;

  // 1 number + expense keyword → only if we have last income to apply it to
  if (numbers.length >= 1 && expenseKw && hasLastIncome) return true;

  return false;
}

function extractFinanceData(text: string) {
  const cleaned = text.replace(/,/g, "");

  const numbers = cleaned.match(/\$?\d+(\.\d+)?/g) || [];

  const values = numbers.map((n) =>
    Number(n.replace("$", ""))
  );

  let income = 0;
  let expenses = 0;

  const lower = text.toLowerCase();

  if (lower.includes("made") || lower.includes("earned") || lower.includes("income")) {
    income = values[0] || 0;
  }

  if (lower.includes("expense") || lower.includes("spent")) {
  expenses = values.length >= 2 ? (values[1] || 0) : (values[0] || 0);
}

  return { income, expenses };
}
  async function upsertIncome(convId: string, amount: number) {
    // Store in DB so report + calc can load it
    const resp = await fetch("http://127.0.0.1:8000/income/add", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        conversation_id: convId,
        income_sources: [
          { type: "1099", amount, description: "Freelance" }, // you can change type later
        ],
      }),
    });

    const txt = await resp.text();
    if (!resp.ok) throw new Error(`Income save failed (${resp.status}): ${txt}`);
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
    const resp = await fetch("http://127.0.0.1:8000/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        conversation_id: params.conversationId,
        message_id: params.messageId,
        rating: params.rating,
        comment: params.comment ?? null,
      }),
    });

    if (!resp.ok) {
      throw new Error(await resp.text());
    }
  }

  async function handleFeedback(
    m: UIMessage,
    rating: "up" | "down",
    comment?: string
  ) {
    const msgId = m.backendMessageId;
    const convId = m.conversationId;

    if (!msgId || !convId) return;

    const current = feedbackByMsg[msgId];
    if (current?.submitting) return; // already sending
    if (current?.rating) return; // already voted

    // Optimistic: disable immediately
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

      // Mark as done (stays disabled)
      setFeedbackByMsg((prev) => ({
        ...prev,
        [msgId]: { rating, submitting: false },
      }));

      // Close comment box after successful submit
      setCommentBoxFor(null);
      setCommentText("");
    } catch (e: any) {
      // Re-enable on error
      setFeedbackByMsg((prev) => ({
        ...prev,
        [msgId]: { rating: null, submitting: false },
      }));
      alert(e?.message ?? "Feedback failed");
    }
  }

  // -------------------------
  // Chat
  // -------------------------
  async function send() {
    const t = input.trim();
    if (!t) return;

    const userText = t;
    setInput("");

    const typingId = crypto.randomUUID?.() ?? String(Date.now());
    const userMsgId = crypto.randomUUID?.() ?? String(Date.now() + 1);

    // 1) Add user message + typing bubble
    setMessages((prev) => [
      ...prev,
      { id: userMsgId, role: "user", text: userText },
      { id: typingId, role: "bot", text: TYPING_TEXT },
    ]);

    try {
      const convId = await ensureConversationId();
      console.log("ROUTE_CHECK", {
  text: userText,
  numericHeavy: looksNumericHeavy(userText, !!lastIncome),
});

            // 🔥 If message looks numeric-heavy, use deterministic calculator
      if (looksNumericHeavy(userText,!!lastIncome)) {
  const { income, expenses } = extractFinanceData(userText);

  const incomeToUse = income > 0 ? income : (lastIncome ?? 0);
  if (income > 0) setLastIncome(income);

  const res = await fetch("http://127.0.0.1:8000/calc/estimate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      conversation_id: convId,
      income_sources: incomeToUse
        ? [{ type: "1099", amount: incomeToUse, description: "Detected income" }]
        : [],
      expenses: expenses ? [{ category: "general", amount: expenses }] : [],
      assumptions: { assumed_marginal_rate: 0.22 },
    }),
  });

  const raw = await res.text();
  if (!res.ok) throw new Error(raw);

  const data = JSON.parse(raw);

  const formatted =
    `Net Business Income: $${data.net_business_income}\n\n` +
    `Self-Employment Tax: $${data.self_employment_tax}\n\n` +
    `Income Tax Estimate: $${data.income_tax_estimate}\n\n` +
    `Total Estimated Tax: $${data.total_estimated_tax}`;

  setMessages((prev) =>
    prev.map((m) =>
      m.id === typingId
        ? { ...m, text: formatted, conversationId: convId,backendMessageId: `calc_${typingId}`,}
        : m
    )
  );

  return;
}
      const resp = await fetch("http://127.0.0.1:8000/chat", {
      // 🔥 Deterministic calculation path

        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          conversation_id: convId,
          message: userText,
          history: [],
        }),
      });

      const raw = await resp.text();
      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}: ${raw}`);
      }

      const data = JSON.parse(raw);

      const answer: string = data.answer_text ?? "No answer received.";
      const newConvId: string | undefined = data.conversation_id;
      const backendMsgId: string | undefined = data.assistant_message_id;

      if (newConvId) setConversationId(newConvId);

      // 2) Replace typing bubble with backend answer + attach IDs for feedback
      setMessages((prev) =>
        prev.map((m) =>
          m.id === typingId
            ? {
                ...m,
                text: answer,
                conversationId: newConvId ?? convId,
                backendMessageId: backendMsgId,
              }
            : m
        )
      );
    } catch (error: any) {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === typingId
            ? {
                ...m,
                text: `⚠️ Could not reach backend: ${error?.message ?? ""}`,
              }
            : m
        )
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
        `http://127.0.0.1:8000/expenses/upload?conversation_id=${convId}`,
        {
          method: "POST",
          body: formData,
        }
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

      // Save income in DB so calc/report can load it
      await upsertIncome(convId, incomeAmount);

      const res = await fetch("http://127.0.0.1:8000/calc/estimate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          conversation_id: convId,
          income_sources: [], // backend will auto-load from DB
          expenses: [], // backend will auto-load from DB
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

    const res = await fetch(
      `http://127.0.0.1:8000/generate-report/${conversationId}`,
      { method: "POST" }
    );

    // ✅ If backend returned error JSON/text, show it
    if (!res.ok) {
      const errText = await res.text();
      alert(`Report failed (${res.status}): ${errText}`);
      return;
    }

    // ✅ Extra safety: confirm it is PDF
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
    
    {/* Grid lines */}
    <div className="absolute inset-0 opacity-[0.08] bg-[linear-gradient(to_right,#ffffff_1px,transparent_1px),linear-gradient(to_bottom,#ffffff_1px,transparent_1px)] bg-size-[80px_80px]" />

    {/* Large right circles */}
    <div className="absolute -right-64 -bottom-64 h-225 w-225 rounded-full border border-white/10" />
    <div className="absolute -right-80 -bottom-80 h-262.5 w-262.5 rounded-full border border-white/5" />

    {/* Dots */}
    <div className="absolute inset-0 opacity-30 bg-[radial-gradient(#ffffff_1px,transparent_1px)] bg-size-[70px_70px]" />

  </div>


        {/* Main layout */}
        <div className="relative z-10 h-full flex flex-col">
          <div className="flex-1 overflow-y-auto">
            <div className="max-w-5xl mx-auto px-6 pt-16 pb-10">
              <div className="flex flex-col items-center text-center">
                <div className="h-20 w-20 rounded-3xl bg-violet-600/25 border border-violet-400/25 flex items-center justify-center shadow-[0_20px_60px_rgba(124,58,237,0.18)]">
                  <div className="mx-auto h-20 w-20 rounded-3xl bg-black border border-violet-500/40 flex items-center justify-center shadow-[0_0_30px_rgba(124,58,237,0.35)]">
  <div className="h-16 w-16 rounded-2xl bg-linear-to-br from-violet-600 to-violet-800 flex items-center justify-center">
    <img
      src="/logo.png"
      alt="SmartTax AI Logo"
      className="h-10 w-10 object-contain"
    />
  </div>
</div>      </div>

                <h1 className="text-4xl md:text-5xl font-bold text-center">
  {cleanName && (
    <>
      {cleanName.charAt(0).toUpperCase() +
        cleanName.slice(1).toLowerCase()}
      {", "}
    </>
  )}
  Welcome to{" "}
  <span className="text-purple-400">SmartTax AI</span>
</h1>

                <p className="mt-4 text-white/70 max-w-2xl">
                  Feeling unsure about your taxes? You&apos;re not alone. Let&apos;s sort it out
                  together.
                </p>

                <div className="mt-6 flex items-center gap-3 flex-wrap justify-center">
                  <span className="text-sm text-white/60">Built for:</span>
                  {quickPills.map((p) => (
                    <span
                      key={p}
                      className="px-4 py-2 rounded-full bg-white/5 border border-white/10 text-sm text-white/80"
                    >
                      {p}
                    </span>
                  ))}
                </div>

                {/* Tabs */}
                <div className="mt-10 flex items-center justify-center gap-2 text-xs">
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
                          : "bg-white/5 border-white/10 text-white/60 hover:bg-white/10"
                      )}
                    >
                      {t.label}
                    </button>
                  ))}
                </div>

                {/* CHAT */}
                {activeTab === "chat" && (
                  <div className="mt-12 w-full max-w-3xl">
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
                                m.role === "user" ? "justify-end" : "justify-start"
                              )}
                            >
                              <div
  className={cx(
    "max-w-[85%] rounded-2xl px-4 py-3 text-sm",
    m.role === "user"
      ? "bg-violet-600 text-white"
      : "bg-white/5 border border-white/10 text-white/85"
  )}
>
  {/* ✅ Message text (keeps newlines + indentation) */}
  <div className="whitespace-pre-wrap leading-relaxed">
    {m.text}
  </div>

  {/* ✅ Feedback only for bot messages */}
  {m.role === "bot" && m.backendMessageId && m.conversationId && (
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
                                              "ring-2 ring-violet-400/60"
                                          )}
                                          onClick={() => handleFeedback(m, "up")}
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
                                              "ring-2 ring-violet-400/60"
                                          )}
                                          onClick={() => {
                                            if (disabled) return;
                                            setCommentBoxFor(m.backendMessageId!);
                                            setCommentText("");
                                          }}
                                        >
                                          👎
                                        </button>

                                        {submitting && (
                                          <span className="text-white/50">Saving…</span>
                                        )}
                                      </div>

                                      {commentBoxFor === m.backendMessageId &&
                                        !alreadyVoted && (
                                          <div className="mt-3 space-y-2 text-left">
                                            <textarea
                                              value={commentText}
                                              onChange={(e) => setCommentText(e.target.value)}
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
                                                  handleFeedback(m, "down", commentText)
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
                  <div className="mt-12 w-full max-w-3xl p-5 rounded-3xl bg-white/5 border border-white/10">
                    <div className="text-sm font-semibold mb-3">Upload Expense CSV</div>

                    <label className="mt-3 inline-flex items-center gap-2 cursor-pointer px-4 py-2 rounded-xl bg-white/10 hover:bg-white/20 transition text-xs">
                      📄 Choose CSV File
                      <input
                        type="file"
                        accept=".csv"
                        onChange={(e) => {
                          const f = e.target.files?.[0] || null;
                          setFile(f);
                        }}
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
                        <div>Total Uploaded: ${uploadResult.total_uploaded}</div>

                        {Object.entries(uploadResult.category_breakdown).map(
                          ([cat, amt]: any) => (
                            <div key={cat}>
                              {cat}: ${amt}
                            </div>
                          )
                        )}
                      </div>
                    )}
                  </div>
                )}

                {/* SUMMARY */}
                {activeTab === "summary" && (
                  <div className="mt-12 w-full max-w-3xl p-5 rounded-3xl bg-white/5 border border-white/10 space-y-3">
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
                        <div>Total Expenses: ${calcResult.total_expenses}</div>
                        <div>Net Business Income: ${calcResult.net_business_income}</div>
                        <div>Self Employment Tax: ${calcResult.self_employment_tax}</div>
                        <div>Income Tax: ${calcResult.income_tax_estimate}</div>
                        <div className="pt-1 font-semibold">
                          Total Estimated Tax: ${calcResult.total_estimated_tax}
                        </div>
                      </div>
                    )}

                    <button
                      onClick={downloadReport}
                      className="px-4 py-2 bg-white/10 rounded-xl text-sm hover:bg-white/20 transition"
                    >
                      Download PDF Report
                    </button>
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