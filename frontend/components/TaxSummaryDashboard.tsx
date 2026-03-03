"use client";

import { Doughnut } from "react-chartjs-2";
import { Chart as ChartJS, ArcElement, Tooltip, Legend } from "chart.js";

ChartJS.register(ArcElement, Tooltip, Legend);

type DeductionCategory = {
  category: string;
  amount: number;
};

type TaxSummaryData = {
  total_income: number;
  total_expenses: number;
  net_business_income: number;
  deductions_by_category: DeductionCategory[] | Record<string, number>;
};

function formatCategoryLabel(key: string) {
  return key
    .replaceAll("_", " ")
    .replace(/\b\w/g, (m) => m.toUpperCase());
}

export default function TaxSummaryDashboard({ data }: { data: TaxSummaryData }) {
  if (!data) return null;

  const income = data.total_income || 0;

  // Convert backend array → object
  // Normalize deductions_by_category into consistent array format
const deductionsArray = Array.isArray(data.deductions_by_category)
  ? data.deductions_by_category
  : Object.entries(data.deductions_by_category || {}).map(
      ([category, amount]) => ({
        category,
        amount: Number(amount) || 0,
      })
    );

// Convert normalized array → object
const expenses: Record<string, number> = {};
deductionsArray.forEach((item) => {
  expenses[item.category] = item.amount;
});

  const totalExpenses =
    data.total_expenses || Object.values(expenses).reduce((a, b) => a + b, 0);

  const netIncome = data.net_business_income ?? income - totalExpenses;

  const labels = Object.keys(expenses).map(formatCategoryLabel);
  const values = Object.values(expenses);

  const chartData = {
    labels,
    datasets: [
      {
        data: values,
        backgroundColor: [
          "#C2A878",
          "#9E7B5F",
          "#E4D5B7",
          "#6F4E37",
          "#D8C3A5",
          "#A78B71",
          "#BFA27A",
        ],
        borderWidth: 1,
        borderColor: "#111",
      },
    ],
  };

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false as const, // IMPORTANT: allow it to fit the fixed-height container
    cutout: "65%",
    plugins: {
      legend: {
        position: "top" as const,
        labels: { color: "#D6C7A1" },
      },
      tooltip: {
        callbacks: {
          label: function (context: any) {
            return `${context.label}: $${Number(context.raw).toLocaleString()}`;
          },
        },
      },
    },
  };

  const hasExpenses = Object.keys(expenses).length > 0;

  return (
    <div className="min-h-screen bg-[#0E0A06] text-[#D6C7A1]">
      <div className="mx-auto w-full max-w-6xl px-4 py-10 sm:py-12">
        <div className="space-y-8 sm:space-y-10">
          {/* Header */}
          <div className="text-center">
            <div className="text-xs tracking-widest opacity-60">
              FISCAL YEAR 2024
            </div>
            <h1 className="mt-3 text-3xl sm:text-4xl font-serif">Tax Summary</h1>
            <div className="mt-4 mx-auto h-px w-40 bg-[#3B2F1E]" />
          </div>

          {/* Summary Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-3 rounded-2xl border border-[#3B2F1E] overflow-hidden bg-white/0">
            <SummaryCard title="Gross Income" value={`$${income.toLocaleString()}`} />
            <SummaryCard
              title="Total Expenses"
              value={`$${totalExpenses.toLocaleString()}`}
              bordered
            />
            <SummaryCard
              title="Net Income"
              value={`$${netIncome.toLocaleString()}`}
              highlight
              bordered
            />
          </div>

          {/* Breakdown Section */}
          <div className="grid gap-6 lg:grid-cols-2 lg:items-stretch">
            {/* Chart Card */}
            <div className="rounded-2xl border border-[#3B2F1E] bg-white/5 p-5 sm:p-6">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold tracking-wide">
                  Expense Breakdown
                </h3>
                <div className="text-xs opacity-60">
                  Total: ${totalExpenses.toLocaleString()}
                </div>
              </div>

              <div className="mt-4 h-80 sm:h-90">
                {hasExpenses ? (
                  <Doughnut data={chartData} options={chartOptions as any} />
                ) : (
                  <div className="text-sm opacity-50">No expense data available.</div>
                )}
              </div>
            </div>

            {/* List Card */}
            <div className="rounded-2xl border border-[#3B2F1E] bg-white/5 p-5 sm:p-6">
              <h3 className="text-sm font-semibold tracking-wide">Details</h3>

              <div className="mt-4 space-y-3">
                {Object.entries(expenses).map(([key, value]) => (
                  <div
                    key={key}
                    className="flex justify-between border-b border-[#3B2F1E] pb-2 text-sm"
                  >
                    <span className="opacity-90">{formatCategoryLabel(key)}</span>
                    <span>${value.toLocaleString()}</span>
                  </div>
                ))}

                <div className="pt-4 font-semibold flex justify-between">
                  <span>Total</span>
                  <span>${totalExpenses.toLocaleString()}</span>
                </div>
              </div>
            </div>
          </div>

          {/* Footer */}
          <div className="text-center text-xs opacity-40 pt-4">
            NET BUSINESS INCOME: ${netIncome.toLocaleString()} · TAX YEAR 2024
          </div>
        </div>
      </div>
    </div>
  );
}

function SummaryCard({
  title,
  value,
  highlight = false,
  bordered = false,
}: {
  title: string;
  value: string;
  highlight?: boolean;
  bordered?: boolean;
}) {
  return (
    <div
      className={[
        "p-6 text-center",
        bordered ? "sm:border-l sm:border-[#3B2F1E]" : "",
      ].join(" ")}
    >
      <div className="text-xs tracking-widest opacity-60">{title}</div>
      <div className={`text-2xl mt-3 ${highlight ? "text-[#8BC34A]" : ""}`}>
        {value}
      </div>
    </div>
  );
}