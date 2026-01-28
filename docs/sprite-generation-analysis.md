# Sprite Sheet Generation Analysis

This document analyzes options for generating character sprite sheets with walking animations for the 6 Atlas Town agents.

## Current State

### Existing Assets
- **Location:** `assets/sprites/characters/`
- **Format:** 1024x1024 JPEG images (mislabeled as PNG)
- **Style:** AI-generated realistic portraits
- **Characters:** sarah_chen, craig_miller, tony_romano, maya_patel, david_chen, marcus_thompson

### What We Need
- Pixel art sprite sheets with walking animations
- 4 directions (North, South, East, West)
- Idle animation state
- Consistent style across all 6 characters
- Target size: 32x32 or 64x64 pixels per frame

### Gap Analysis
| Have | Need |
|------|------|
| Realistic portraits | Pixel art sprites |
| Single static images | Multi-frame animations |
| 1024x1024 resolution | 32-64px sprite frames |

---

## Option 1: PixelLab.ai (Cloud Service)

### Overview
PixelLab.ai is a specialized AI tool for generating pixel art game assets, including animated sprite sheets.

### Pricing Tiers

| Tier | Cost | Limits | Max Sprite Size |
|------|------|--------|-----------------|
| Free Trial | $0 | 40 fast gens, then 5/day slow | 200x200 |
| Pixel Apprentice | $12/month | Animation + map tools | 320x320 |
| Hobbyist | ~$20/month | 1,000 gens/month | Higher |
| Pro | Higher | 3,000 gens/month + priority | Higher |

### Credit System
| Model Type | Credits/Request | Output (32x32) | Output (128x128) |
|------------|-----------------|----------------|------------------|
| Basic | 1 credit | 16 frames | 4 frames |
| Advanced | 40 credits | 16 frames | 4 frames |

### Estimated Usage for This Project

#### Base Requirements
| Asset Type | Per Character | x 6 Characters | Total |
|------------|---------------|----------------|-------|
| Walk North | 1 request | 6 | 6 |
| Walk South | 1 request | 6 | 6 |
| Walk East | 1 request | 6 | 6 |
| Walk West | 1 request | 6 | 6 |
| Idle | 1 request | 6 | 6 |
| **Subtotal** | **5 requests** | | **30 requests** |

#### With Iterations and Fine-tuning

```
PHASE 1: Style Discovery
─────────────────────────
Test generations to find style:        10 requests

PHASE 2: First Character (Sarah)
─────────────────────────────────
Base animations (5 directions):         5 requests
Iterations to get it right (x3):       15 requests
                                       ──────────
Subtotal:                              20 requests

PHASE 3: Remaining 5 Characters
───────────────────────────────
Base animations (5 x 5):               25 requests
Iterations for consistency (x2):       50 requests
                                       ──────────
Subtotal:                              75 requests

PHASE 4: Fixes & Polish
───────────────────────
Color corrections:                     10 requests
Bad frame re-generations:              10 requests
Final adjustments:                      5 requests
                                       ──────────
Subtotal:                              25 requests

═══════════════════════════════════════════════════
TOTAL REQUESTS:                       130 requests
═══════════════════════════════════════════════════
```

#### Credit Calculation
| Model Type | Credits/Request | Total Credits |
|------------|-----------------|---------------|
| Basic only | 1 | 130 |
| Advanced only | 40 | 5,200 |
| **Mixed (70% adv, 30% basic)** | ~29 avg | **~3,770** |

### PixelLab.ai Pros & Cons

| Pros | Cons |
|------|------|
| Purpose-built for pixel art | Subscription only (no one-time purchase) |
| Animation tools included | $12-20/month cost |
| No setup required | Dependent on cloud service |
| Fast iteration | Limited control over model |
| Style consistency tools | |

### Recommendation
- **Tier:** Pixel Apprentice ($12/month)
- **Duration:** 1 month should suffice
- **Total Cost:** ~$12

---

## Option 2: Local Stable Diffusion Pipeline

### Hardware Requirements vs Available

| Spec | Minimum | Recommended | Your Machine |
|------|---------|-------------|--------------|
| Chip | M1 | M2+ | M4 Max |
| Memory | 16 GB | 32 GB | 128 GB |
| Storage | 20 GB | 50 GB | - |

**Verdict:** Your M4 Max with 128GB RAM exceeds requirements significantly. You can run models that desktop users with RTX 4090 (24GB VRAM) cannot.

### Technology Stack

#### Option A: Stable Diffusion + LoRA (Recommended)
```
Difficulty: 6/10
Setup time: 2-4 hours
```

**Components:**
- **WebUI:** ComfyUI or Automatic1111
- **Base Model:** SDXL or SD 1.5
- **LoRA:** pixel-art-xl, pixelart-style, or similar

**Installation (ComfyUI):**
```bash
# Clone repository
git clone https://github.com/comfyanonymous/ComfyUI
cd ComfyUI

# Install dependencies
pip install -r requirements.txt

# Download models to models/ directory
# - Base: SDXL or SD 1.5 from HuggingFace
# - LoRA: pixel-art-xl from CivitAI

# Run
python main.py
```

#### Option B: Dedicated Pixel Art Models
```
Difficulty: 4/10
Setup time: 1-2 hours
```

**Options:**
- PixelFusion - Specialized for game sprites
- Retro Diffusion - 8/16-bit style focused

#### Option C: Fine-tune Custom Model
```
Difficulty: 9/10
Setup time: Days to weeks
```

Not recommended unless you have ML experience.

### Local Pipeline Pros & Cons

| Pros | Cons |
|------|------|
| Free (no ongoing cost) | Initial setup time |
| Full control over output | Learning curve |
| No usage limits | Need to find right LoRA |
| Works offline | Troubleshooting may be needed |
| Reusable for future projects | Style consistency requires skill |

---

## Option 3: Free/Open Source Sprite Assets

### Available Resources

| Source | License | Style | Customizable |
|--------|---------|-------|--------------|
| LPC (Liberated Pixel Cup) | CC-BY/GPL | RPG | Yes (modular) |
| OpenGameArt.org | Various | Mixed | Varies |
| Kenney.nl | CC0 | Clean/modern | Recolor only |
| itch.io asset packs | Various | Mixed | Varies |

### Approach
1. Find base sprite sheets that match desired style
2. Recolor to match each character's theme color
3. May need to combine parts from multiple packs

### Pros & Cons

| Pros | Cons |
|------|------|
| Free | May not match project aesthetic |
| Immediate availability | Limited customization |
| Battle-tested in games | Generic look |
| No AI unpredictability | Characters won't match portraits |

---

## Comparison Summary

### Time Investment

| Approach | Setup | Learning | Per-Character | Total Time |
|----------|-------|----------|---------------|------------|
| PixelLab.ai | 0 | 1 hr | 10 min | ~2 hours |
| Local SD | 3 hrs | 4 hrs | 20 min | ~9 hours |
| Custom pipeline | 10+ hrs | 10+ hrs | 15 min | 20+ hours |
| Free assets | 1 hr | 0 | 30 min | ~4 hours |

### Cost Comparison

| Approach | Upfront | Ongoing | For This Project |
|----------|---------|---------|------------------|
| PixelLab.ai | $0 | $12/mo | **$12** |
| Local SD | $0 | $0 | **$0** |
| Free assets | $0 | $0 | **$0** |

### Quality & Control

| Approach | Quality | Style Control | Consistency |
|----------|---------|---------------|-------------|
| PixelLab.ai | High | Medium | High |
| Local SD | Medium-High | High | Medium |
| Free assets | Varies | Low | High |

---

## Decision Matrix

| If you prioritize... | Choose |
|---------------------|--------|
| Speed (done today) | PixelLab.ai |
| Cost ($0) | Local SD or Free assets |
| Quality + Speed | PixelLab.ai |
| Learning + Reusability | Local SD |
| Simplicity | Free assets |
| Full control | Local SD |

---

## Recommended Approach

### For This Project (Immediate Need)

**PixelLab.ai - Pixel Apprentice Tier ($12)**

1. Use free trial to learn the interface
2. Subscribe to Pixel Apprentice for one month
3. Generate all 6 character sprite sheets
4. Cancel before renewal

**Total investment:** $12 + ~2 hours

### For Long-term/Future Projects

**Set up Local Stable Diffusion Pipeline**

1. Install ComfyUI on M4 Max
2. Download SDXL + pixel art LoRAs
3. Create workflow templates for sprite generation
4. Reuse for all future sprite needs

**Total investment:** $0 + ~1 day setup (one-time)

---

## Character Specifications

For reference, here are the 6 characters and their theme colors:

| Agent ID | Name | Theme Color | Hex | Starting Building |
|----------|------|-------------|-----|-------------------|
| sarah | Sarah Chen | Purple | #9370DB | Accounting Office |
| craig | Craig Miller | Forest Green | #228B22 | Craig's Landscaping |
| tony | Tony Romano | Crimson | #DC143C | Tony's Pizzeria |
| maya | Maya Patel | Royal Blue | #4169E1 | Nexus Tech |
| chen | Dr. David Chen | Sky Blue | #87CEEB | Main Street Dental |
| marcus | Marcus Thompson | Goldenrod | #DAA520 | Harbor Realty |

### Sprite Sheet Format (Target)

```
┌────────────────────────────────────────┐
│ Frame 1 │ Frame 2 │ Frame 3 │ Frame 4  │  ← Walk South
├─────────┼─────────┼─────────┼──────────┤
│ Frame 1 │ Frame 2 │ Frame 3 │ Frame 4  │  ← Walk West
├─────────┼─────────┼─────────┼──────────┤
│ Frame 1 │ Frame 2 │ Frame 3 │ Frame 4  │  ← Walk East
├─────────┼─────────┼─────────┼──────────┤
│ Frame 1 │ Frame 2 │ Frame 3 │ Frame 4  │  ← Walk North
├─────────┼─────────┼─────────┼──────────┤
│ Frame 1 │ Frame 2 │         │          │  ← Idle
└────────────────────────────────────────┘

Each frame: 32x32 or 64x64 pixels
Total sheet: 128x160 or 256x320 pixels
```

---

## References

- [PixelLab.ai](https://www.pixellab.ai/)
- [PixelLab FAQ](https://www.pixellab.ai/docs/faq)
- [ComfyUI GitHub](https://github.com/comfyanonymous/ComfyUI)
- [CivitAI - LoRA Models](https://civitai.com/)
- [OpenGameArt](https://opengameart.org/)
- [Liberated Pixel Cup](https://lpc.opengameart.org/)
