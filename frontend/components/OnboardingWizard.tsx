"use client";

import React, { useEffect, useMemo, useState } from "react";
import SmartTaxChat from "./SmartTaxChat";

type Answers = {
  firstName: string;
  freelanceType: string | null;
  deductionMethod: string | null;
  toolsUsed: string[];
  overpayIRS: "Yes" | "No" | "Not sure" | null;
  expenseTracking: "Digitally (apps)" | "Manually (spreadsheets)" | "Not at all" | null;
  incomeRange:
    | "Under $25K"
    | "$25K – $50K"
    | "$50K – $100K"
    | "$100K+"
    | "Prefer not to say"
    | null;
  confidence: 1 | 2 | 3 | 4 | 5 | null;
};

const STORAGE_KEY = "smarttax_profile_v1";

const defaultAnswers: Answers = {
  firstName: "",
  freelanceType: null,
  deductionMethod: null,
  toolsUsed: [],
  overpayIRS: null,
  expenseTracking: null,
  incomeRange: null,
  confidence: null,
};

function clampName(s: string) {
  return s.replace(/[^a-zA-Z\s'-]/g, "").slice(0, 24);
}

function cx(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}

export default function OnboardingWizard() {
  const [mode, setMode] = useState<"onboarding" | "chat">("onboarding");

  /**
   * step:
   * 0 = Landing page
   * 1 = Terms of Use
   * 2..9 = steps
   */
  const [step, setStep] = useState<number>(0);
  const [answers, setAnswers] = useState<Answers>(defaultAnswers);

  const canContinue = useMemo(() => {
    switch (step) {
      case 0:
        return true; // landing
      case 1:
        return true; // terms handled internally
      case 2:
        return answers.firstName.trim().length >= 1;
      case 3:
        return !!answers.freelanceType;
      case 4:
        return !!answers.deductionMethod;
      case 5:
        return answers.toolsUsed.length >= 1;
      case 6:
        return !!answers.overpayIRS;
      case 7:
        return !!answers.expenseTracking;
      case 8:
        return !!answers.incomeRange;
      case 9:
        return !!answers.confidence;
      default:
        return false;
    }
  }, [answers, step]);



  const progressPct = useMemo(() => {
    if (step <= 1) return 0; // landing + terms show 0%
    return Math.round(((step - 1) / 8) * 100);
  }, [step]);

  function saveAndGoChat() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(answers));
    } catch {}
    setMode("chat");
  }

  function resetAll() {
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {}
    setAnswers(defaultAnswers);
    setStep(0);
    setMode("onboarding");
  }

  if (mode === "chat") {
    // Pass firstName; SmartTaxChat should handle empty gracefully
    return <SmartTaxChat firstName={answers.firstName} onReset={resetAll} />;
  }

  const showStepUI = step >= 2; // show only after terms
  const stepLabel = step >= 2 ? `Step ${step - 1} of 8` : "";

  return (
    <div className="min-h-screen w-full bg-black text-white overflow-hidden">
      {/* Top bar */}
      <div className="h-16 flex items-center justify-between px-6 border-b border-white/10 bg-black/60 backdrop-blur">
        <div className="flex items-center gap-3">
          <div className="h-9 w-9 rounded-xl bg-white/5 border border-white/10 flex items-center justify-center overflow-hidden">
            <img src="/logo.png" alt="SmartTax AI Logo" className="h-7 w-7 object-contain" />
          </div>

          <div className="leading-tight">
            <div className="text-sm font-semibold">SmartTax AI ✨</div>
            <div className="text-xs text-white/70">
              {step === 0 ? "AI-Powered Tax Intelligence" : `Setting up for ${answers.firstName || "you"}`}
            </div>
          </div>
        </div>

        <button
          type="button"
          className="h-10 px-4 rounded-full bg-violet-600 hover:bg-violet-500 transition font-semibold"
        >
          Early Access
        </button>
      </div>

      {/* Progress line */}
      <div className="h-1 bg-white/10 relative z-50">
        <div className="h-1 bg-violet-500" style={{ width: `${progressPct}%` }} />
      </div>

      {/* Background */}
      <div className="relative min-h-[calc(100vh-68px)] overflow-hidden">
        <div className="absolute inset-0 pointer-events-none">
          <div className="absolute -top-40 left-1/2 -translate-x-1/2 h-130 w-230 rounded-full bg-violet-700/20 blur-3xl" />
          <div className="absolute inset-0 opacity-[0.08] bg-[linear-gradient(to_right,#ffffff_1px,transparent_1px),linear-gradient(to_bottom,#ffffff_1px,transparent_1px)] bg-size-[80px_80px]" />
          <div className="absolute inset-0 opacity-30 bg-[radial-gradient(#ffffff_1px,transparent_1px)] bg-size-[70px_70px]" />
        </div>

        {/* Content */}
        <div className="relative h-full flex items-center justify-center px-6 py-6">
          {/* ✅ KEY CHANGE: remove max-w-3xl wrapper so landing can feel like Image 1 */}
          <div className="w-full">
            {/* Step chip + skip */}
            {showStepUI && (
              <div className="flex items-center justify-between mb-5 max-w-3xl mx-auto">
                <div className="inline-flex items-center rounded-full bg-violet-500/15 border border-violet-400/20 px-3 py-1 text-xs text-violet-200">
                  {stepLabel}
                </div>

                <button
                  type="button"
                  onClick={() => {
                    if (step < 9) setStep((s) => s + 1);
                    else saveAndGoChat();
                  }}
                  className="text-xs text-white/70 hover:text-white/90 transition"
                >
                  Skip →
                </button>
              </div>
            )}

            {/* Card */}
            <div
              className={cx(
                // ✅ KEY CHANGE: landing has no card; steps keep the card look
                step === 0
                  ? "w-full"
                  : "w-full max-w-3xl mx-auto rounded-3xl border border-white/10 bg-black/30 backdrop-blur-xl shadow-[0_30px_90px_rgba(0,0,0,0.45)] p-6 md:p-8",
                // ✅ keep stability only for non-landing
                step === 0 ? "bg-transparent border-none shadow-none" : "max-h-[calc(100vh-64px-4px-28px)] overflow-hidden"
              )}
            >
              {/* Step 0 */}
              {step === 0 && <LandingPage onStart={() => setStep(1)} />}

              {/* Step 1 */}
              {step === 1 && <TermsStep onBack={() => setStep(0)} onAccept={() => setStep(2)} />}

              {/* Step 2 */}
              {step === 2 && (
                <StepName
                  value={answers.firstName}
                  onChange={(v) => setAnswers((p) => ({ ...p, firstName: clampName(v) }))}
                />
              )}

              {/* Step 3 */}
              {step === 3 && (
                <StepSingleChoice
                  title="What kind of freelance work do you do?"
                  subtitle="This helps us suggest the right deductions for your industry."
                  options={[
                    { label: "Writing & Content", icon: "✍️" },
                    { label: "Design & Creative", icon: "🎨" },
                    { label: "Software & Tech", icon: "💻" },
                    { label: "Consulting", icon: "📚" },
                    { label: "Sales & Marketing", icon: "🤝" },
                    { label: "Other", icon: "🔧" },
                  ]}
                  value={answers.freelanceType}
                  onPick={(v) => setAnswers((p) => ({ ...p, freelanceType: v }))}
                />
              )}

              {/* Step 4 */}
              {step === 4 && (
                <StepSingleChoice
                  title="How do you currently calculate your deductions?"
                  subtitle="No judgment — most freelancers aren't sure where to start."
                  options={[
                    { label: "Manually", icon: "📄" },
                    { label: "Excel / Google Sheets", icon: "📊" },
                    { label: "Tax apps", icon: "🧾" },
                    { label: "Accountant / CPA", icon: "🧑‍💼" },
                    { label: "I'm not sure", icon: "🤷" },
                  ]}
                  value={answers.deductionMethod}
                  onPick={(v) => setAnswers((p) => ({ ...p, deductionMethod: v }))}
                />
              )}

              {/* Step 5 */}
              {step === 5 && (
                <StepMultiChoice
                  title="Which tools do you use for taxes today?"
                  subtitle="Select all that apply — this helps us understand your workflow."
                  options={[
                    { label: "FlyFin AI", icon: "🤖" },
                    { label: "TurboTax", icon: "🟢" },
                    { label: "H&R Block", icon: "🟩" },
                    { label: "QuickBooks", icon: "🟨" },
                    { label: "None yet", icon: "🆕" },
                    { label: "Other", icon: "🗂️" },
                  ]}
                  values={answers.toolsUsed}
                  onToggle={(v) =>
                    setAnswers((p) => {
                      const exists = p.toolsUsed.includes(v);
                      return {
                        ...p,
                        toolsUsed: exists ? p.toolsUsed.filter((x) => x !== v) : [...p.toolsUsed, v],
                      };
                    })
                  }
                />
              )}

              {/* Step 6 */}
              {step === 6 && (
                <StepEmojiChoice
                  title="Do you feel like you overpay the IRS?"
                  subtitle="You're definitely not alone if you do."
                  options={[
                    { label: "Yes", emoji: "😮‍💨" },
                    { label: "No", emoji: "😊" },
                    { label: "Not sure", emoji: "🤔" },
                  ]}
                  value={answers.overpayIRS}
                  onPick={(v) => setAnswers((p) => ({ ...p, overpayIRS: v as Answers["overpayIRS"] }))}
                />
              )}

              {/* Step 7 */}
              {step === 7 && (
                <StepSingleChoice
                  title="How do you track your expenses?"
                  subtitle="We'll tailor our tips based on your workflow."
                  options={[
                    { label: "Digitally (apps)", icon: "📱" },
                    { label: "Manually (spreadsheets)", icon: "📄" },
                    { label: "Not at all", icon: "😅" },
                  ]}
                  value={answers.expenseTracking}
                  onPick={(v) => setAnswers((p) => ({ ...p, expenseTracking: v as Answers["expenseTracking"] }))}
                />
              )}

              {/* Step 8 */}
              {step === 8 && (
                <StepSingleChoice
                  title="What's your estimated annual income?"
                  subtitle="This helps us estimate your tax bracket. Totally optional!"
                  options={[
                    { label: "Under $25K", icon: "💵" },
                    { label: "$25K – $50K", icon: "💰" },
                    { label: "$50K – $100K", icon: "💎" },
                    { label: "$100K+", icon: "🚀" },
                    { label: "Prefer not to say", icon: "🔒" },
                  ]}
                  value={answers.incomeRange}
                  onPick={(v) => setAnswers((p) => ({ ...p, incomeRange: v as Answers["incomeRange"] }))}
                />
              )}

              {/* Step 9 */}
              {step === 9 && (
                <StepConfidence
                  value={answers.confidence}
                  onPick={(v) => setAnswers((p) => ({ ...p, confidence: v }))}
                />
              )}

              {/* Footer controls (not landing, not terms) */}
              {step >= 2 && (
                <div className="mt-8 flex items-center justify-between">
                  <button
                    type="button"
                    onClick={() => setStep((s) => Math.max(0, s - 1))}
                    className={cx("text-sm text-white/70 hover:text-white/90 transition")}
                  >
                    ← Back
                  </button>

                  <button
                    type="button"
                    onClick={() => {
                      if (!canContinue) return;
                      if (step < 9) setStep((s) => s + 1);
                      else saveAndGoChat();
                    }}
                    className={cx(
                      "h-12 px-6 rounded-2xl font-semibold",
                      "bg-violet-600 hover:bg-violet-500 transition",
                      "disabled:opacity-40 disabled:cursor-not-allowed"
                    )}
                    disabled={!canContinue}
                  >
                    {step === 9 ? "Finish →" : "Continue →"}
                  </button>
                </div>
              )}
            </div>

            {/* reset */}
            <div className={cx("mt-4 text-center", step === 0 ? "" : "max-w-3xl mx-auto")}>
              <button type="button" onClick={resetAll} className="text-xs text-white/50 hover:text-white/70">
                Reset onboarding
              </button>
            </div>

            <div className="h-10" />
          </div>
        </div>
      </div>
    </div>
  );
}

/* ------------------ Landing ------------------ */

function LandingPage({ onStart }: { onStart: () => void }) {
  return (
    <div className="text-center py-12 md:py-16">
      {/* Logo */}
      <div className="mx-auto h-16 w-16 rounded-3xl bg-violet-600/25 border border-violet-400/25 flex items-center justify-center shadow-[0_20px_60px_rgba(124,58,237,0.18)] overflow-hidden">
        <img src="/logo.png" alt="SmartTax AI Logo" className="h-10 w-10 object-contain" />
      </div>

      <div className="mt-4 text-violet-300 font-semibold">SmartTax AI</div>

      {/* Title */}
      <h1 className="mt-3 text-4xl md:text-6xl lg:text-7xl font-extrabold tracking-tight leading-[1.05]">
        TAKE
        <br />
        CONTROL OF YOUR
        <br />
        <span className="inline-block mt-3 px-5 py-2 rounded-2xl bg-violet-600">
          TAXES.
        </span>
      </h1>

      <p className="mt-4 text-white/70 max-w-xl mx-auto text-sm md:text-base">
        Answer a few quick questions so we can personalize your experience.
      </p>

      {/* Pills */}
      <div className="mt-6 flex items-center justify-center gap-3 flex-wrap text-xs md:text-sm text-white/55">
        <span className="px-3 py-1.5 rounded-full bg-white/5 border border-white/10">🛡️ Private & secure</span>
        <span className="px-3 py-1.5 rounded-full bg-white/5 border border-white/10">🔒 Encrypted</span>
        <span className="px-3 py-1.5 rounded-full bg-white/5 border border-white/10">⚡ Fast answers</span>
      </div>

      {/* Button */}
      <div className="mt-7 flex items-center justify-center">
        <button
          type="button"
          onClick={onStart}
          className="inline-flex items-center justify-center rounded-2xl bg-violet-600 px-7 py-3 text-white font-semibold hover:bg-violet-700 transition"
        >
          Let&apos;s get started <span className="ml-2">→</span>
        </button>
      </div>
    </div>
  );
}

/* ------------------ Terms ------------------ */

function TermsStep({ onAccept, onBack }: { onAccept: () => void; onBack: () => void }) {
  const [scrolledToBottom, setScrolledToBottom] = React.useState(false);
  const [agreed, setAgreed] = React.useState(false);

  return (
    <div className="flex flex-col h-full">
      <h1 className="text-3xl md:text-4xl font-semibold tracking-tight">Terms of Use</h1>
      <p className="mt-2 text-white/60">Please read the Terms below. Scroll to the bottom to continue.</p>

      {/* Scroll box */}
      <div
        className="mt-6 h-72 overflow-y-auto rounded-2xl bg-white/5 border border-white/10 p-5 text-sm text-white/70 leading-6"
        onScroll={(e) => {
          const el = e.currentTarget;
          const atBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 12;
          if (atBottom) setScrolledToBottom(true);
        }}
      >
        <div className="space-y-6">
          <div>
            <div className="font-semibold text-white/85">1. ACCEPTANCE OF TERMS</div>
            <p>
              By accessing or using SmartTax AI’s website, chatbot, API, mobile application, or related services
              (collectively, the “Service”), you agree to be legally bound by these Terms of Use (“Terms”).
            </p>
            <p>If you do not agree, do not use the Service.</p>
            <p>You represent that:</p>
            <ul className="list-disc pl-5">
              <li>You are at least 18 years old</li>
              <li>You have legal capacity to enter into this agreement</li>
              <li>You are using the Service for lawful purposes only</li>
            </ul>
          </div>

          <div>
            <div className="font-semibold text-white/85">2. NO PROFESSIONAL ADVICE</div>
            <p>
              SmartTax AI provides general informational tools powered by artificial intelligence. The Service is NOT a
              CPA, law firm, tax preparer, or financial advisor and does NOT provide legal, tax, accounting, investment,
              or financial advice.
            </p>
            <p>
              Outputs are generated automatically based on user inputs and may be incomplete, inaccurate, or outdated.
              You agree not to rely solely on the Service for tax filings, compliance, audits, or legal decisions.
            </p>
            <p>You are solely responsible for verifying information and consulting a licensed professional.</p>
          </div>

          <div>
            <div className="font-semibold text-white/85">3. USER RESPONSIBILITIES</div>
            <ul className="list-disc pl-5">
              <li>You are responsible for the accuracy of information you provide.</li>
              <li>You agree not to upload content you do not have rights to share.</li>
              <li>You agree not to use the Service for fraud, evasion, or illegal purposes.</li>
              <li>You will comply with all applicable laws and regulations.</li>
            </ul>
          </div>

          <div>
            <div className="font-semibold text-white/85">4. PRIVACY</div>
            <p>
              We may process information you provide to deliver and improve the Service. For details, refer to our
              Privacy Policy (if provided on the site). You should avoid entering highly sensitive personal information
              unless necessary.
            </p>
          </div>

          <div>
            <div className="font-semibold text-white/85">5. INTELLECTUAL PROPERTY</div>
            <p>
              The Service, including the UI, branding, text, and software, is owned by SmartTax AI and protected by
              intellectual property laws. You may not copy, resell, or reverse engineer the Service except as permitted
              by law.
            </p>
          </div>

          <div>
            <div className="font-semibold text-white/85">6. LIMITATIONS OF LIABILITY</div>
            <p>
              To the maximum extent permitted by law, SmartTax AI is not liable for any indirect, incidental, special,
              consequential, or punitive damages, or any loss of profits, revenue, data, or goodwill arising from your
              use of the Service.
            </p>
            <p>
              The Service is provided “AS IS” and “AS AVAILABLE” without warranties of any kind, whether express or
              implied.
            </p>
          </div>

          <div>
            <div className="font-semibold text-white/85">7. TERMINATION</div>
            <p>
              We may suspend or terminate access if we believe you have violated these Terms or used the Service in a way
              that could cause harm, legal risk, or abuse.
            </p>
          </div>

          <div>
            <div className="font-semibold text-white/85">8. CHANGES TO TERMS</div>
            <p>
              We may update these Terms from time to time. Continued use of the Service after changes means you accept
              the updated Terms.
            </p>
          </div>

          <div>
            <div className="font-semibold text-white/85">9. CONTACT</div>
            <p>
              If you have questions about these Terms, contact SmartTax AI through the contact method provided on the
              website (if available).
            </p>
          </div>

          <div className="pt-2 text-xs text-white/45">End of Terms.</div>
        </div>
      </div>

      {/* Agree row */}
      <div className="mt-4 flex items-center gap-2">
        <input
          id="agree"
          type="checkbox"
          className="h-4 w-4"
          checked={agreed}
          onChange={(e) => setAgreed(e.target.checked)}
        />
        <label htmlFor="agree" className="text-sm text-white/70">
          I agree to the Terms of Use
        </label>
      </div>

      {/* Buttons */}
      <div className="mt-4 flex items-center justify-between">
        <button type="button" onClick={onBack} className="text-sm text-white/70 hover:text-white/90 transition">
          ← Back
        </button>

        <button
          type="button"
          disabled={!scrolledToBottom || !agreed}
          onClick={onAccept}
          className="h-12 px-6 rounded-2xl font-semibold bg-violet-600 hover:bg-violet-500 transition disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Continue →
        </button>
      </div>

      {!scrolledToBottom && (
        <div className="mt-3 text-xs text-white/50">Scroll to the bottom to enable Continue.</div>
      )}
    </div>
  );
}

/* ------------------ Steps ------------------ */

function StepName({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <div>
      <h1 className="text-3xl md:text-4xl font-semibold tracking-tight">First, what should we call you?</h1>
      <p className="mt-2 text-white/60">Just a first name is fine — we like to keep things friendly.</p>

      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="e.g. Vaishnavi"
        className="mt-6 w-full h-14 rounded-2xl bg-white/5 border border-white/10 px-4 text-white placeholder:text-white/40 outline-none focus:ring-2 focus:ring-violet-500/30"
      />
    </div>
  );
}

function StepSingleChoice({
  title,
  subtitle,
  options,
  value,
  onPick,
}: {
  title: string;
  subtitle: string;
  options: Array<{ label: string; icon: string }>;
  value: string | null;
  onPick: (v: string) => void;
}) {
  return (
    <div>
      <h1 className="text-3xl md:text-4xl font-semibold tracking-tight">{title}</h1>
      <p className="mt-2 text-white/60">{subtitle}</p>

      <div className="mt-6 grid grid-cols-1 sm:grid-cols-2 gap-3">
        {options.map((o) => (
          <button
            key={o.label}
            type="button"
            onClick={() => onPick(o.label)}
            className={cx(
              "h-14 rounded-2xl px-4 flex items-center gap-3 text-left w-full",
              "bg-white/5 border border-white/10 hover:bg-white/10 transition",
              value === o.label ? "border-violet-400 bg-violet-500/20 ring-2 ring-violet-400/40" : "border-white/10"
            )}
          >
            <span className="text-lg">{o.icon}</span>
            <span className="text-sm font-medium">{o.label}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

function StepMultiChoice({
  title,
  subtitle,
  options,
  values,
  onToggle,
}: {
  title: string;
  subtitle: string;
  options: Array<{ label: string; icon: string }>;
  values: string[];
  onToggle: (v: string) => void;
}) {
  return (
    <div>
      <h1 className="text-3xl md:text-4xl font-semibold tracking-tight">{title}</h1>
      <p className="mt-2 text-white/60">{subtitle}</p>

      <div className="mt-6 grid grid-cols-1 sm:grid-cols-2 gap-3">
        {options.map((o) => {
          const active = values.includes(o.label);
          return (
            <button
              key={o.label}
              type="button"
              onClick={() => onToggle(o.label)}
              className={cx(
                "h-14 rounded-2xl px-4 flex items-center gap-3 text-left w-full",
                "bg-white/5 border hover:bg-white/10 transition",
                active ? "border-violet-400 bg-violet-500/20 ring-2 ring-violet-400/40" : "border-white/10"
              )}
            >
              <span className="text-lg">{o.icon}</span>
              <span className="text-sm font-medium">{o.label}</span>
            </button>
          );
        })}
      </div>

      <p className="mt-4 text-xs text-white/50">Tip: you can select multiple.</p>
    </div>
  );
}

function StepEmojiChoice({
  title,
  subtitle,
  options,
  value,
  onPick,
}: {
  title: string;
  subtitle: string;
  options: Array<{ label: string; emoji: string }>;
  value: string | null;
  onPick: (v: string) => void;
}) {
  return (
    <div>
      <h1 className="text-3xl md:text-4xl font-semibold tracking-tight">{title}</h1>
      <p className="mt-2 text-white/60">{subtitle}</p>

      <div className="mt-10 flex items-center justify-center gap-6 flex-wrap">
        {options.map((o) => (
          <button
            key={o.label}
            type="button"
            onClick={() => onPick(o.label)}
            className={cx(
              "w-28 h-28 rounded-3xl flex flex-col items-center justify-center gap-2",
              "bg-white/5 border border-white/10 hover:bg-white/10 transition",
              value === o.label && "border-violet-400/50 bg-violet-500/10"
            )}
          >
            <div className="text-3xl">{o.emoji}</div>
            <div className="text-sm font-medium">{o.label}</div>
          </button>
        ))}
      </div>
    </div>
  );
}

function StepConfidence({
  value,
  onPick,
}: {
  value: 1 | 2 | 3 | 4 | 5 | null;
  onPick: (v: 1 | 2 | 3 | 4 | 5) => void;
}) {
  const faces = [
    { v: 1 as const, emoji: "😱", label: "Not at all" },
    { v: 2 as const, emoji: "😟", label: "Low" },
    { v: 3 as const, emoji: "😐", label: "Somewhat okay" },
    { v: 4 as const, emoji: "🙂", label: "Good" },
    { v: 5 as const, emoji: "😎", label: "Very confident" },
  ];

  const selected = faces.find((f) => f.v === value)?.label ?? "Select one";

  return (
    <div className="text-center">
      <h1 className="text-3xl md:text-4xl font-semibold tracking-tight">
        How confident are you about doing your taxes?
      </h1>
      <p className="mt-2 text-white/60">Pick a number (1–5).</p>

      <div className="mt-10 flex items-center justify-center gap-4 flex-wrap">
        {faces.map((f) => (
          <button
            key={f.v}
            type="button"
            onClick={() => onPick(f.v)}
            className={cx(
              "w-16 h-16 rounded-2xl flex items-center justify-center text-2xl",
              "bg-white/5 border border-white/10 hover:bg-white/10 transition",
              value === f.v && "border-violet-400/50 bg-violet-500/10"
            )}
          >
            {f.emoji}
          </button>
        ))}
      </div>

      <div className="mt-6 text-sm text-white/60">{selected}</div>
    </div>
  );
}