# Local LLM Setup for Atlas Town

This guide covers running the Atlas Town simulation with local LLMs instead of cloud APIs.

## Cost Comparison

| Approach | 3-Year Simulation Cost |
|----------|------------------------|
| Cloud APIs (Budget) | $600-800 |
| Cloud APIs (Standard) | $1,800 |
| **Local LLM** | **~$3** (electricity only) |

## Hardware Requirements

### Minimum (8B models only)
- 16GB RAM
- Any Apple Silicon Mac or RTX 3060+

### Recommended (70B models)
- 48GB+ unified memory (Mac) or 48GB+ VRAM
- Apple M2 Pro/Max or better
- RTX 4090, A6000, or multi-GPU setup

### Optimal (all models)
- 128GB+ unified memory
- Apple M4 Max/Ultra
- Can run 70B+ models at full speed

## Model Recommendations

| Agent Role | Recommended Model | VRAM Needed | Quality |
|------------|-------------------|-------------|---------|
| Sarah (Accountant) | Llama 3.3 70B | ~40 GB | Excellent |
| Business Owners | Llama 3.3 70B | ~40 GB | Excellent |
| Customers/Vendors | Llama 3.1 8B | ~6 GB | Good |

For simpler setups, use one 70B model for all agents.

## Quick Setup with Ollama

### 1. Install Ollama

```bash
# macOS
brew install ollama

# Linux
curl -fsSL https://ollama.com/install.sh | sh
```

### 2. Pull Models

```bash
# Best quality (needs 48GB+ RAM)
ollama pull llama3.3:70b

# Fast/lightweight option
ollama pull llama3.1:8b

# Alternative high-quality
ollama pull qwen2.5:72b
```

### 3. Start Server

```bash
ollama serve
# Runs on http://localhost:11434
```

## Performance Expectations

### Apple Silicon (M4 Max 128GB)

| Model | Tokens/sec | 1 Sim Day | 3-Year Sim |
|-------|------------|-----------|------------|
| Llama 3.1 8B | 80-100 t/s | ~2-3 min | ~2-3 hours |
| Llama 3.3 70B | 15-25 t/s | ~15-20 min | ~12-18 hours |

### NVIDIA GPUs

| GPU | Model | Tokens/sec |
|-----|-------|------------|
| RTX 4090 | Llama 3.1 8B | 100+ t/s |
| RTX 4090 | Llama 70B (Q4) | 20-30 t/s |
| 2x RTX 4090 | Llama 70B | 40-50 t/s |

## Token Usage Per Simulated Day

| Agent Type | Input Tokens | Output Tokens |
|------------|--------------|---------------|
| Sarah (Accountant) | ~75,000 | ~17,500 |
| 5 Business Owners | ~20,000 | ~5,000 |
| Customers/Vendors | ~15,000 | ~3,000 |
| **Daily Total** | **~110,000** | **~26,000** |

## Configuration

Set environment variables in `.env`:

```bash
# Use Ollama instead of cloud APIs
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434

# Model selection
OLLAMA_MODEL_LARGE=llama3.3:70b    # For Sarah
OLLAMA_MODEL_SMALL=llama3.1:8b     # For simple agents
```

## Hybrid Approach

Use local LLMs for most calls, cloud for complex reasoning:

```bash
# 90% local, 10% cloud
ACCOUNTANT_LLM=claude-sonnet      # Cloud for complex accounting
OWNER_LLM=ollama:llama3.3:70b     # Local for owners
CUSTOMER_LLM=ollama:llama3.1:8b   # Local for simple agents
```

Estimated cost: $50-100 for 3-year simulation.

## Troubleshooting

### Out of Memory
- Use quantized models (Q4_K_M)
- Reduce context length
- Use smaller model for simple agents

### Slow Performance
- Ensure GPU/Metal acceleration is enabled
- Check `ollama ps` for running models
- Consider batching requests

### Tool Calling Issues
- Some local models have weaker tool calling
- Use structured output prompts as fallback
- Consider cloud API for complex tool use
