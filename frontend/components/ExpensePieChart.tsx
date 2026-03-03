"use client";

import { Chart as ChartJS, ArcElement, Tooltip, Legend } from "chart.js";
import { Pie } from "react-chartjs-2";

ChartJS.register(ArcElement, Tooltip, Legend);

type Props = {
  data: { category: string; amount: number }[];
};

export default function ExpensePieChart({ data }: Props) {
  if (!data || data.length === 0) return null;

  // Normalize data into array format
const normalizedData = Array.isArray(data)
  ? data
  : Object.entries(data || {}).map(([category, amount]) => ({
      category,
      amount,
    }));

const chartData = {
  labels: normalizedData.map((d) =>
    d.category.replaceAll("_", " ").toUpperCase()
  ),
  datasets: [
    {
      label: "Expenses",
      data: normalizedData.map((d) => d.amount),
      backgroundColor: [
        "#7C3AED",
        "#A78BFA",
        "#C4B5FD",
        "#DDD6FE",
        "#5B21B6",
        "#8B5CF6",
      ],
      borderWidth: 1,
    },
  ],
};

  const options = {
    responsive: true,
    maintainAspectRatio: false as const,
    plugins: {
      legend: { position: "top" as const },
    },
  };

  return (
    <div className="rounded-2xl border border-white/10 bg-white/5 p-6">
      <h3 className="text-sm font-semibold mb-4">Expense Breakdown</h3>
      <div className="h-80">
        <Pie data={chartData} options={options as any} />
      </div>
    </div>
  );
}