"use client";

import { useSimulationStore, Transaction } from "@/lib/state/simulationStore";

const TYPE_COLORS: Record<string, string> = {
  invoice: "text-green-400",
  bill: "text-red-400",
  payment_received: "text-emerald-400",
  payment_sent: "text-orange-400",
};

const TYPE_ICONS: Record<string, string> = {
  invoice: "📄",
  bill: "📋",
  payment_received: "💰",
  payment_sent: "💸",
};

export function TransactionFeed() {
  const transactions = useSimulationStore((state) => state.transactions);

  return (
    <div className="bg-slate-800 rounded-lg p-4 shadow-lg h-full flex flex-col">
      <h2 className="text-lg font-bold mb-3 text-slate-100">
        Transaction Feed
      </h2>

      <div className="flex-1 overflow-y-auto custom-scrollbar space-y-2">
        {transactions.length === 0 ? (
          <p className="text-slate-500 text-sm text-center py-8">
            No transactions yet.
            <br />
            <span className="text-xs">
              Transactions will appear here as the simulation runs.
            </span>
          </p>
        ) : (
          transactions.map((tx) => (
            <TransactionItem key={tx.id} transaction={tx} />
          ))
        )}
      </div>
    </div>
  );
}

function TransactionItem({ transaction }: { transaction: Transaction }) {
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
    <div className="bg-slate-700/50 rounded-lg p-3 hover:bg-slate-700 transition-colors">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="text-lg">{typeIcon}</span>
          <div>
            <p className={`text-sm font-medium ${typeColor}`}>
              {transaction.type.replace("_", " ").toUpperCase()}
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
}
