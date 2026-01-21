"use client";

import { memo, useState, useMemo } from "react";
import { useSimulationStore, Transaction } from "@/lib/state/simulationStore";

const TYPE_COLORS: Record<string, string> = {
  invoice: "text-green-400",
  invoice_created: "text-green-400",
  bill: "text-red-400",
  bill_created: "text-red-400",
  payment_received: "text-emerald-400",
  payment_sent: "text-orange-400",
};

const TYPE_ICONS: Record<string, string> = {
  invoice: "📄",
  invoice_created: "📄",
  bill: "📋",
  bill_created: "📋",
  payment_received: "💰",
  payment_sent: "💸",
};

type FilterType = "all" | "invoices" | "bills" | "payments";

export function TransactionFeed() {
  const transactions = useSimulationStore((state) => state.transactions);
  const [filter, setFilter] = useState<FilterType>("all");

  const filteredTransactions = useMemo(() => {
    if (filter === "all") return transactions;
    return transactions.filter((tx) => {
      switch (filter) {
        case "invoices":
          return tx.type === "invoice" || tx.type === "invoice_created";
        case "bills":
          return tx.type === "bill" || tx.type === "bill_created";
        case "payments":
          return tx.type === "payment_received" || tx.type === "payment_sent";
        default:
          return true;
      }
    });
  }, [transactions, filter]);

  return (
    <div className="bg-slate-800 rounded-lg p-4 shadow-lg h-full flex flex-col">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-bold text-slate-100">Transaction Feed</h2>
        <span className="text-xs text-slate-500 bg-slate-700 px-2 py-1 rounded">
          {transactions.length} total
        </span>
      </div>

      {/* Filter buttons */}
      <div className="flex gap-1 mb-3">
        {(["all", "invoices", "bills", "payments"] as FilterType[]).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-2 py-1 text-xs rounded transition-colors ${
              filter === f
                ? "bg-blue-600 text-white"
                : "bg-slate-700 text-slate-300 hover:bg-slate-600"
            }`}
          >
            {f.charAt(0).toUpperCase() + f.slice(1)}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto custom-scrollbar space-y-2">
        {filteredTransactions.length === 0 ? (
          <p className="text-slate-500 text-sm text-center py-8">
            {transactions.length === 0 ? (
              <>
                No transactions yet.
                <br />
                <span className="text-xs">
                  Transactions will appear here as the simulation runs.
                </span>
              </>
            ) : (
              <>No {filter} found.</>
            )}
          </p>
        ) : (
          filteredTransactions.map((tx, index) => (
            <TransactionItem
              key={tx.id}
              transaction={tx}
              isNew={index === 0}
            />
          ))
        )}
      </div>
    </div>
  );
}

const TransactionItem = memo(function TransactionItem({
  transaction,
  isNew,
}: {
  transaction: Transaction;
  isNew?: boolean;
}) {
  const typeColor = TYPE_COLORS[transaction.type] || "text-slate-300";
  const typeIcon = TYPE_ICONS[transaction.type] || "📝";

  const formattedAmount = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
  }).format(transaction.amount);

  const time = new Date(transaction.timestamp).toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
  });

  return (
    <div
      className={`bg-slate-700/50 rounded-lg p-3 hover:bg-slate-700 transition-all ${
        isNew ? "animate-pulse ring-2 ring-blue-500/50" : ""
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="text-lg">{typeIcon}</span>
          <div>
            <p className={`text-sm font-medium ${typeColor}`}>
              {transaction.type.replace(/_/g, " ").toUpperCase()}
            </p>
            <p className="text-xs text-slate-400">{transaction.orgName}</p>
          </div>
        </div>
        <div className="text-right">
          <p className="text-sm font-bold text-white">{formattedAmount}</p>
          <p className="text-xs text-slate-500">{time}</p>
        </div>
      </div>

      {transaction.counterparty && (
        <p className="text-xs text-slate-400 mt-2">
          {transaction.type.includes("invoice") || transaction.type.includes("received")
            ? "From"
            : "To"}
          : {transaction.counterparty}
        </p>
      )}

      {transaction.description && (
        <p className="text-xs text-slate-500 mt-1 truncate">
          {transaction.description}
        </p>
      )}
    </div>
  );
});
