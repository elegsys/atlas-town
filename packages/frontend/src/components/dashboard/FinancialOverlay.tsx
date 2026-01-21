"use client";

import { useSimulationStore } from "@/lib/state/simulationStore";
import { INDUSTRY_ICONS } from "@/lib/pixi/townConfig";

const INDUSTRY_MAP: Record<string, string> = {
  craig: "landscaping",
  tony: "restaurant",
  maya: "technology",
  chen: "healthcare",
  marcus: "real_estate",
};

export function FinancialOverlay() {
  const financialSummary = useSimulationStore((state) => state.financialSummary);
  const currentDay = useSimulationStore((state) => state.currentDay);

  const formatCurrency = (amount: number) =>
    new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(amount);

  const orgsArray = Array.from(financialSummary.byOrg.values());

  return (
    <div className="bg-slate-800 rounded-lg p-4 shadow-lg">
      <h2 className="text-lg font-bold mb-3 text-slate-100 flex items-center gap-2">
        <span>📊</span>
        Financial Overview
      </h2>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 gap-3 mb-4">
        <MetricCard
          label="Accounts Receivable"
          value={formatCurrency(financialSummary.totalAR)}
          trend="up"
          color="text-green-400"
        />
        <MetricCard
          label="Accounts Payable"
          value={formatCurrency(financialSummary.totalAP)}
          trend="down"
          color="text-red-400"
        />
        <MetricCard
          label="Total Cash"
          value={formatCurrency(financialSummary.totalCash)}
          trend="neutral"
          color="text-blue-400"
        />
        <MetricCard
          label="Day {day} Transactions"
          value={financialSummary.dailyTransactionCount.toString()}
          trend="neutral"
          color="text-purple-400"
          day={currentDay}
        />
      </div>

      {/* Per-Organization Breakdown */}
      {orgsArray.length > 0 && (
        <div className="border-t border-slate-700 pt-3">
          <h3 className="text-sm font-medium text-slate-400 mb-2">By Business</h3>
          <div className="space-y-2 max-h-48 overflow-y-auto custom-scrollbar">
            {orgsArray.map((org) => (
              <OrgFinancialRow key={org.orgId} org={org} formatCurrency={formatCurrency} />
            ))}
          </div>
        </div>
      )}

      {/* Empty State */}
      {orgsArray.length === 0 && (
        <div className="text-center py-6 text-slate-500">
          <p className="text-sm">No financial data yet.</p>
          <p className="text-xs mt-1">Data will appear as transactions occur.</p>
        </div>
      )}
    </div>
  );
}

function MetricCard({
  label,
  value,
  trend,
  color,
  day,
}: {
  label: string;
  value: string;
  trend: "up" | "down" | "neutral";
  color: string;
  day?: number;
}) {
  const displayLabel = day !== undefined ? label.replace("{day}", day.toString()) : label;

  return (
    <div className="bg-slate-700/50 rounded-lg p-3">
      <p className="text-xs text-slate-400 mb-1">{displayLabel}</p>
      <p className={`text-lg font-bold ${color}`}>
        {trend === "up" && "↑ "}
        {trend === "down" && "↓ "}
        {value}
      </p>
    </div>
  );
}

function OrgFinancialRow({
  org,
  formatCurrency,
}: {
  org: { orgId: string; orgName: string; industry: string; ar: number; ap: number; cash: number; transactions: number };
  formatCurrency: (amount: number) => string;
}) {
  // Try to determine industry from orgId
  const industryKey = Object.keys(INDUSTRY_MAP).find((key) => org.orgId.toLowerCase().includes(key));
  const industry = industryKey ? INDUSTRY_MAP[industryKey] : "default";
  const icon = INDUSTRY_ICONS[industry as keyof typeof INDUSTRY_ICONS] || "🏢";

  const netPosition = org.ar - org.ap;
  const netColor = netPosition >= 0 ? "text-green-400" : "text-red-400";

  return (
    <div className="bg-slate-700/30 rounded-lg p-2 hover:bg-slate-700/50 transition-colors">
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2">
          <span className="text-sm">{icon}</span>
          <span className="text-sm text-white font-medium truncate max-w-[120px]">
            {org.orgName || org.orgId}
          </span>
        </div>
        <span className="text-xs text-slate-500">{org.transactions} txns</span>
      </div>
      <div className="flex items-center justify-between text-xs">
        <div className="flex gap-3">
          <span className="text-green-400">AR: {formatCurrency(org.ar)}</span>
          <span className="text-red-400">AP: {formatCurrency(org.ap)}</span>
        </div>
        <span className={`font-medium ${netColor}`}>
          Net: {formatCurrency(netPosition)}
        </span>
      </div>
    </div>
  );
}
