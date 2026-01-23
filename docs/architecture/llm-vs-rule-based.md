# LLM vs Rule-Based Accounting: Architecture Decision

## Overview

Atlas Town simulation supports two modes for accounting operations:

1. **LLM-Based (AccountantAgent)** - Uses Claude/GPT/Gemini for decision-making
2. **Rule-Based (AccountingWorkflow)** - Uses deterministic code paths

This document explains when to use each approach and how they work together.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         ATLAS TOWN SIMULATION                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                 TRANSACTION GENERATION LAYER                  │   │
│  │                    (Always Probabilistic)                     │   │
│  │                                                               │   │
│  │  • Day-of-week multipliers    • Seasonal patterns            │   │
│  │  • Time-of-day phases         • Business-specific rules      │   │
│  │  • Random amount generation   • Customer/vendor selection    │   │
│  │                                                               │   │
│  │  Output: List[GeneratedTransaction]                          │   │
│  └──────────────────────────┬───────────────────────────────────┘   │
│                             │                                        │
│                             ▼                                        │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                   ACCOUNTING LAYER                            │   │
│  │              (Choose: LLM or Rule-Based)                      │   │
│  │                                                               │   │
│  │  ┌─────────────────────┐    ┌─────────────────────────────┐  │   │
│  │  │   AccountantAgent   │    │    AccountingWorkflow       │  │   │
│  │  │     (LLM-Based)     │    │      (Rule-Based)           │  │   │
│  │  ├─────────────────────┤    ├─────────────────────────────┤  │   │
│  │  │ • Think-Act-Observe │    │ • Direct API calls          │  │   │
│  │  │ • Natural language  │    │ • Template summaries        │  │   │
│  │  │ • Tool calling      │    │ • Deterministic logic       │  │   │
│  │  │ • ~30 sec/day       │    │ • ~2 sec/day                │  │   │
│  │  │ • ~$0.05/day        │    │ • $0/day                    │  │   │
│  │  └─────────────────────┘    └─────────────────────────────┘  │   │
│  └──────────────────────────┬───────────────────────────────────┘   │
│                             │                                        │
│                             ▼                                        │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                      ATLAS API LAYER                          │   │
│  │                    (Always Deterministic)                     │   │
│  │                                                               │   │
│  │  • Create invoices/bills     • Record payments               │   │
│  │  • Run trial balance         • Generate reports              │   │
│  │  • Manage customers/vendors  • Bank reconciliation           │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## Comparison

### Performance

| Metric | LLM-Based | Rule-Based | Improvement |
|--------|-----------|------------|-------------|
| Daily workflow | ~30 sec | ~2 sec | 15x faster |
| Monthly (30 days) | ~15 min | ~1 min | 15x faster |
| Yearly simulation | ~3 hours | ~12 min | 15x faster |
| API cost per day | ~$0.05 | $0 | 100% savings |
| API cost per year | ~$18 | $0 | 100% savings |

### Capabilities

| Capability | Rule-Based | LLM-Based |
|------------|:----------:|:---------:|
| Create invoices | ✅ | ✅ |
| Record payments | ✅ | ✅ |
| Enter bills | ✅ | ✅ |
| Run trial balance | ✅ | ✅ |
| Generate fixed reports | ✅ | ✅ |
| Handle edge cases | ❌ | ✅ |
| Answer "why" questions | ❌ | ✅ |
| Generate insights | ❌ | ✅ |
| Natural conversation | ❌ | ✅ |
| Adapt to unexpected situations | ❌ | ✅ |

## When to Use Each Mode

### Use Rule-Based Mode (`--mode=fast`) for:

- **Bulk data generation** - Populate a year of realistic accounting data
- **Automated testing** - Deterministic, reproducible results
- **Performance benchmarks** - Measure API throughput
- **CI/CD pipelines** - Fast feedback loops
- **Demo data seeding** - Quick setup for presentations
- **Cost-sensitive environments** - No LLM API costs

### Use LLM-Based Mode (`--mode=llm`) for:

- **Interactive demos** - Show "thinking" agents with personality
- **User Q&A** - "Why did expenses increase last month?"
- **Edge case handling** - Unusual transactions, errors, exceptions
- **Analysis & insights** - "What trends should I watch?"
- **Training/education** - Explain accounting concepts naturally
- **Narrative simulations** - Story-driven scenarios

### Use Hybrid Mode (`--mode=hybrid`) for:

- **Best of both worlds** - Fast operations + smart analysis
- **Production simulations** - Rule-based core, LLM for exceptions
- **Cost optimization** - LLM only when it adds value

## Usage

### Command Line

```bash
# Fast mode - rule-based, no LLM
uv run python -m atlas_town.orchestrator --mode=fast --days=30

# LLM mode - full agent reasoning (current default)
uv run python -m atlas_town.orchestrator --mode=llm --days=30

# Hybrid mode - rule-based + LLM for analysis
uv run python -m atlas_town.orchestrator --mode=hybrid --days=30

# Single task with LLM (always uses LLM)
uv run python -m atlas_town.orchestrator "Why is revenue down?"
```

### Programmatic

```python
from atlas_town.orchestrator import Orchestrator, SimulationMode

# Fast mode
orchestrator = Orchestrator(mode=SimulationMode.FAST)
await orchestrator.run_simulation(max_days=30)

# LLM mode
orchestrator = Orchestrator(mode=SimulationMode.LLM)
await orchestrator.run_simulation(max_days=30)

# Hybrid - use workflow for operations, agent for analysis
orchestrator = Orchestrator(mode=SimulationMode.HYBRID)
await orchestrator.run_simulation(max_days=30)
```

## Implementation Details

### Rule-Based Flow

```python
# 1. Generate transactions (probabilistic)
transactions = generator.generate_daily_transactions(
    business_key="tony",
    current_date=today,
    customers=customers,
    vendors=vendors,
)

# 2. Process transactions (deterministic)
for tx in transactions:
    if tx.type == TransactionType.INVOICE:
        await api.create_invoice(
            customer_id=tx.customer_id,
            line_items=[{
                "description": tx.description,
                "quantity": 1,
                "unit_price": float(tx.amount),
            }],
        )
    elif tx.type == TransactionType.BILL:
        await api.create_bill(...)
    # ... etc

# 3. Generate summary (template-based)
summary = DailySummary(
    invoices_created=len(invoices),
    invoices_total=sum(i.amount for i in invoices),
    # ...
)
print(summary.to_text())
```

### LLM-Based Flow

```python
# 1. Generate transactions (probabilistic) - same as above
transactions = generator.generate_daily_transactions(...)

# 2. Create task prompt
task = f"""
Process today's transactions for Tony's Pizzeria:
{format_transactions(transactions)}

After processing, run a trial balance and summarize the day.
"""

# 3. Agent thinks and acts (LLM-driven)
response = await agent.run_task(task)
# Agent decides: which tool to call, what parameters, when to stop
# Agent generates: natural language summary with personality
```

### Hybrid Flow

```python
# 1. Use rule-based for fast operations
workflow = AccountingWorkflow(api_client)
summary = await workflow.run_daily_workflow("tony", org_id, today)

# 2. Use LLM only for analysis/issues
if summary.issues or user_has_question:
    agent = AccountantAgent()
    analysis = await agent.run_task(
        f"Analyze these issues:\n{summary.to_text()}"
    )
```

## Files

| File | Purpose |
|------|---------|
| `transactions.py` | Probabilistic transaction generation |
| `accounting_workflow.py` | Rule-based accounting operations |
| `agents/accountant.py` | LLM-based accounting agent |
| `orchestrator.py` | Coordinates both modes |

## Related Issues

- Issue #12: Add rule-based accounting workflow mode
- Issue #9: Time-of-day transaction patterns
- Issue #10: Seasonal multipliers
- Issue #11: Day-of-week patterns
