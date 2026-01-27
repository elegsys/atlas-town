# Atlas Town Frontend Enhancement Guide

## Overview

This guide outlines the implementation order for transforming the Atlas Town frontend from procedural graphics to a pixel-art simulation. The plan includes **28 issues across 9 epics**.

**Goal**: Create a therapeutic, visually rich experience where users watch AI agents manage accounting workflows in a living, breathing pixel-art town.

**User Priority**: Completeness first - show all 6 agents before polishing visuals.

---

## Issue Dependency Graph

```
                    ┌─────────────────────────────────────────────────────────┐
                    │                    FOUNDATION                           │
                    │                                                         │
                    │  #37 Building Sprites ──────┬──────► #43 Decorations   │
                    │          │                  │              │            │
                    │          │                  │              ▼            │
                    │          │                  └──────► #44 Day/Night     │
                    │          │                               │              │
                    │          ▼                               ▼              │
                    │  #39 Tile Terrain ─────────────────► #45 Weather       │
                    │                                                         │
                    │  #38 Character Sprites ────┬──────► #49 Idle Anims    │
                    │          │                 │              │            │
                    │          │                 │              ▼            │
                    │          │                 └──────► #50 Thought Bubbles│
                    │          │                               │              │
                    │          ▼                               ▼              │
                    │  #40 All 6 Agents ─────────────────► #51 Interactions  │
                    │          │                                              │
                    │          ▼                                              │
                    │  #41 Customer/Vendor NPCs                               │
                    │          │                                              │
                    │          ▼                                              │
                    │  #42 Vehicle Traffic                                    │
                    └─────────────────────────────────────────────────────────┘

                    ┌─────────────────────────────────────────────────────────┐
                    │                 TRANSACTION VISUALIZATION               │
                    │                                                         │
                    │  #46 Transaction Indicators ───────► #47 Money Flow    │
                    │          │                                │             │
                    │          └────────────────┬───────────────┘             │
                    │                           ▼                             │
                    │                    #48 Status Indicators                │
                    └─────────────────────────────────────────────────────────┘

                    ┌─────────────────────────────────────────────────────────┐
                    │                     INTERACTIVITY                       │
                    │                                                         │
                    │  #52 Click-to-Inspect ─────────────► #64 Agent Memory  │
                    │          │                                              │
                    │          ▼                                              │
                    │  #53 Camera Pan/Zoom ──────────────► #54 Minimap       │
                    │                                                         │
                    │  #62 Auto-Pause (independent)                           │
                    └─────────────────────────────────────────────────────────┘

                    ┌─────────────────────────────────────────────────────────┐
                    │                        AUDIO                            │
                    │                                                         │
                    │  #55 Audio Settings ───┬───────────► #56 Ambient Sound │
                    │          │             │                                │
                    │          │             └───────────► #57 Transaction SFX│
                    │          │                                              │
                    │          └─────────────────────────► #58 Lofi Music    │
                    └─────────────────────────────────────────────────────────┘

                    ┌─────────────────────────────────────────────────────────┐
                    │                      DASHBOARD                          │
                    │                                                         │
                    │  #59 Financial Icons (independent)                      │
                    │  #60 Financial Charts (independent)                     │
                    │  #61 Focus Mode (independent)                           │
                    │  #63 Tiled Map Support (requires #39)                   │
                    └─────────────────────────────────────────────────────────┘
```

---

## Implementation Phases

### Phase 1: Core Sprite Foundation (Week 1)
**Goal**: Replace shapes with sprites, show all agents

| Order | Issue | Title | Depends On | Effort |
|-------|-------|-------|------------|--------|
| 1.1 | #37 | Replace procedural buildings with sprite assets | - | Medium |
| 1.2 | #38 | Implement character sprite system with animations | - | Large |
| 1.3 | #40 | Render all 6 business owner agents | #38 | Small |

**Milestone**: All 6 agents visible with walking animations, buildings are sprites.

```typescript
// Key file: packages/frontend/src/lib/pixi/spriteLoader.ts
// Creates foundation used by all subsequent sprite work
```

---

### Phase 2: Town Environment (Week 2)
**Goal**: Complete the visual environment

| Order | Issue | Title | Depends On | Effort |
|-------|-------|-------|------------|--------|
| 2.1 | #39 | Add tile-based terrain system | #37 | Medium |
| 2.2 | #43 | Add decorations and street props | #37 | Small |
| 2.3 | #41 | Add customer/vendor NPC sprites | #38, #40 | Medium |

**Milestone**: Town looks complete with terrain, decorations, and NPCs appearing during transactions.

---

### Phase 3: Transaction Visualization (Week 3)
**Goal**: Make money flow visible

| Order | Issue | Title | Depends On | Effort |
|-------|-------|-------|------------|--------|
| 3.1 | #46 | Visual transaction indicators on buildings | #37 | Small |
| 3.2 | #47 | Money flow animation between buildings | #46 | Medium |
| 3.3 | #59 | Use financial icons in transaction feed | - | Small |

**Milestone**: Can "see" accounting happening - transactions appear on buildings, money flows visually.

---

### Phase 4: Atmosphere & Lighting (Week 4)
**Goal**: Add time-of-day atmosphere

| Order | Issue | Title | Depends On | Effort |
|-------|-------|-------|------------|--------|
| 4.1 | #44 | Implement day/night lighting cycle | #37, #43 | Medium |
| 4.2 | #55 | Implement audio settings system | - | Small |
| 4.3 | #57 | Add transaction sound effects | #55 | Small |

**Milestone**: Town changes with time of day, audio provides feedback.

---

### Phase 5: Character Personality (Week 5)
**Goal**: Make characters feel alive

| Order | Issue | Title | Depends On | Effort |
|-------|-------|-------|------------|--------|
| 5.1 | #49 | Implement idle animations | #38 | Medium |
| 5.2 | #50 | Add thought bubble enhancements | #40 | Small |
| 5.3 | #56 | Add ambient town soundscape | #55 | Medium |

**Milestone**: Characters have personality, ambient sounds create atmosphere.

---

### Phase 6: Interactivity (Week 6)
**Goal**: Enable user exploration

| Order | Issue | Title | Depends On | Effort |
|-------|-------|-------|------------|--------|
| 6.1 | #52 | Add click-to-inspect | #37, #40 | Medium |
| 6.2 | #62 | Implement auto-pause after inactivity | - | Small |
| 6.3 | #53 | Implement camera pan and zoom | - | Medium |

**Milestone**: Users can click to inspect, camera moves, simulation auto-pauses.

---

### Phase 7: Polish & Extras (Week 7-8)
**Goal**: Complete the experience

| Order | Issue | Title | Depends On | Effort |
|-------|-------|-------|------------|--------|
| 7.1 | #48 | Financial status indicators | #46 | Small |
| 7.2 | #42 | Add vehicle traffic system | #38 | Medium |
| 7.3 | #51 | Character interaction animations | #49 | Medium |
| 7.4 | #54 | Add minimap | #53 | Small |
| 7.5 | #60 | Add real-time financial charts | - | Medium |
| 7.6 | #64 | Agent memory visualization | #52 | Medium |
| 7.7 | #58 | Add lofi background music | #55 | Small |
| 7.8 | #61 | Add focus mode | - | Small |

---

### Phase 8: Advanced Features (Future)
**Goal**: Extensibility and polish

| Order | Issue | Title | Depends On | Effort |
|-------|-------|-------|------------|--------|
| 8.1 | #45 | Weather and seasonal effects | #39, #44 | Large |
| 8.2 | #63 | Tiled map editor support | #39 | Large |

---

## Dependency Matrix

| Issue | Hard Dependencies | Soft Dependencies |
|-------|------------------|-------------------|
| #37 Building Sprites | - | - |
| #38 Character Sprites | - | - |
| #39 Tile Terrain | #37 | - |
| #40 All Agents | #38 | - |
| #41 NPCs | #38, #40 | - |
| #42 Vehicles | #38 | #39 |
| #43 Decorations | #37 | - |
| #44 Day/Night | #37 | #43 |
| #45 Weather | #39 | #44 |
| #46 Transaction Indicators | #37 | - |
| #47 Money Flow | #46 | - |
| #48 Status Indicators | #46 | #47 |
| #49 Idle Animations | #38 | #40 |
| #50 Thought Bubbles | #40 | - |
| #51 Interactions | #49 | - |
| #52 Click-to-Inspect | #37, #40 | - |
| #53 Camera | - | - |
| #54 Minimap | #53 | - |
| #55 Audio Settings | - | - |
| #56 Ambient Sound | #55 | #44 |
| #57 Transaction SFX | #55 | #46 |
| #58 Lofi Music | #55 | - |
| #59 Financial Icons | - | - |
| #60 Financial Charts | - | - |
| #61 Focus Mode | - | - |
| #62 Auto-Pause | - | - |
| #63 Tiled Support | #39 | - |
| #64 Agent Memory | #52 | - |

---

## Quick Start: Minimum Viable Enhancement

For the fastest path to visible improvement, implement in this order:

```
#38 → #40 → #37 → #46 → #59
```

This gives you:
1. Character sprite system
2. All 6 agents visible
3. Buildings as sprites
4. Transaction indicators
5. Consistent icons in dashboard

**Estimated effort**: 1-2 weeks for a dramatically improved experience.

---

## Files to Create (New)

```
packages/frontend/src/lib/pixi/
├── spriteLoader.ts          # #37 - Asset loading/caching
├── AnimatedCharacter.ts     # #38 - Character sprite class
├── characterConfig.ts       # #38 - Character definitions
├── TileMap.ts               # #39 - Terrain system
├── tileConfig.ts            # #39 - Tile definitions
├── TransactionIndicator.ts  # #46 - Floating indicators
├── MoneyFlowAnimation.ts    # #47 - Money flow particles
├── FinancialStatusIndicator.ts # #48 - Health bars
├── LightingSystem.ts        # #44 - Day/night cycle
├── WeatherSystem.ts         # #45 - Rain/snow particles
├── VehicleSystem.ts         # #42 - Traffic management
├── SpeechBubble.ts          # #50 - Enhanced bubbles
├── CameraController.ts      # #53 - Pan/zoom controls
├── TiledMapLoader.ts        # #63 - Tiled format support

packages/frontend/src/lib/audio/
├── AudioManager.ts          # #55 - Central audio control
├── audioSettings.ts         # #55 - Settings/presets

packages/frontend/src/lib/state/
├── chartDataStore.ts        # #60 - Chart aggregation
├── agentHistoryStore.ts     # #64 - Agent memory

packages/frontend/src/lib/utils/
├── inactivityTracker.ts     # #62 - Auto-pause logic

packages/frontend/src/components/
├── town/
│   ├── InspectorPopup.tsx   # #52 - Click inspection
│   ├── Minimap.tsx          # #54 - Overview map
│   └── TransactionEffects.tsx # #46 - Visual effects
├── panels/
│   └── AgentMemoryPanel.tsx # #64 - History view
├── dashboard/
│   └── FinancialCharts.tsx  # #60 - Charts
├── settings/
│   └── AudioSettings.tsx    # #55 - Audio panel
└── overlays/
    └── PausedOverlay.tsx    # #62 - Pause screen
```

---

## Files to Modify (Existing)

```
packages/frontend/src/components/town/TownCanvas.tsx
  - Almost every issue touches this file
  - Consider refactoring into smaller components as complexity grows

packages/frontend/src/lib/pixi/townConfig.ts
  - #37: Building sprite mappings
  - #43: Decoration positions
  - Vehicle routes, NPC spawn points

packages/frontend/src/lib/state/simulationStore.ts
  - #40: Agent state for all 6 owners
  - #41: NPC state management
  - #64: Agent history tracking

packages/frontend/src/components/dashboard/TransactionFeed.tsx
  - #59: Replace emoji with sprite icons
```

---

## Asset Requirements

### Sprites (Existing - Verify)
- [ ] 6 character sprite sheets (Sarah, Craig, Tony, Maya, Chen, Marcus)
- [ ] 5+ building sprites matching businesses
- [ ] Terrain tiles (road, sidewalk, grass)
- [ ] Decoration sprites (trees, benches, streetlights)
- [ ] Vehicle sprites (cars, trucks)
- [ ] Icon sprites (invoice, payment, bill)

### Audio (Need to Source)
- [ ] Ambient loops: morning, day, evening, night
- [ ] SFX: cash register, paper shuffle, notification
- [ ] Music: 1-3 lofi tracks (royalty-free)

### Additional Sprites (May Need)
- [ ] NPC variations (recolored characters?)
- [ ] Business-specific idle frames (#49)
- [ ] Interaction animations (#51)
- [ ] Weather particles (#45)
- [ ] Window glow overlays (#44)

---

## Testing Checkpoints

After each phase, verify:

1. **Visual**: Does it look correct? No z-order issues?
2. **Animation**: Smooth 60fps? No stuttering?
3. **Events**: WebSocket events trigger correct visuals?
4. **Performance**: FPS stable with all elements?
5. **Experience**: Does it feel therapeutic to watch?

---

## GitHub Project Board Suggested Columns

```
📋 Backlog | 🔜 Ready | 🚧 In Progress | 👀 Review | ✅ Done
```

Filter by priority:
- `label:priority:high` - Must have
- `label:priority:medium` - Should have
- `label:priority:low` - Nice to have

Filter by epic:
- `label:epic:sprite-foundation`
- `label:epic:populate-town`
- etc.

---

## Links

- [All Frontend Issues](https://github.com/elegsys/atlas-town/issues?q=is%3Aissue+label%3Afrontend)
- [High Priority](https://github.com/elegsys/atlas-town/issues?q=is%3Aissue+label%3Apriority%3Ahigh+label%3Afrontend)
- [ai-town Inspiration](https://github.com/a16z-infra/ai-town)
