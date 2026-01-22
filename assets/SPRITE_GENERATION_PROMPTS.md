# Sprite Generation Prompts for Atlas Town

Prompts for generating pixel art sprites using AI image generators (Google Imagen, Gemini, etc.)

## Style Guidelines

Add these modifiers to all prompts for consistency:

```
16-bit pixel art style, top-down RPG view, 64x64 pixels,
transparent background, clean edges, limited color palette,
game sprite sheet, retro SNES style
```

---

## Character Sprites

### Sarah Chen - The Accountant (Main Character)

```
Pixel art character sprite sheet, professional Asian woman accountant,
neat black hair in bun, glasses, blue blazer, white blouse,
holding clipboard, friendly expression, walking animation 4 directions,
16-bit RPG style, top-down view, 64x64 pixels, transparent background
```

**Idle pose:**
```
Single pixel art sprite, professional woman accountant standing,
glasses, blue business attire, clipboard in hand,
16-bit style, top-down RPG view, 64x64, transparent background
```

### Craig Miller - Landscaping Owner

```
Pixel art character sprite sheet, middle-aged Caucasian man,
tan/weathered skin, baseball cap, green work shirt, jeans,
friendly smile, work gloves, walking animation 4 directions,
16-bit RPG style, top-down view, 64x64 pixels, transparent background
```

### Tony Romano - Pizzeria Owner

```
Pixel art character sprite sheet, Italian-American man,
mustache, white chef coat, red apron, chef hat,
warm friendly expression, holding pizza paddle,
16-bit RPG style, top-down view, 64x64 pixels, transparent background
```

### Maya Patel - Tech Consulting Founder

```
Pixel art character sprite sheet, South Asian woman,
modern professional, blazer over casual shirt, laptop bag,
confident expression, dark hair, stylish glasses,
16-bit RPG style, top-down view, 64x64 pixels, transparent background
```

### Dr. David Chen - Dental Practice Owner

```
Pixel art character sprite sheet, Asian-American man,
white dental coat, stethoscope, neat short hair,
kind professional expression, clipboard,
16-bit RPG style, top-down view, 64x64 pixels, transparent background
```

### Marcus Thompson - Real Estate Broker

```
Pixel art character sprite sheet, African-American man,
sharp navy suit, red tie, confident posture,
holding house keys or folder, professional smile,
16-bit RPG style, top-down view, 64x64 pixels, transparent background
```

---

## Building Sprites

### Craig's Landscaping Shop

```
Pixel art building sprite, small landscaping business storefront,
green awning, "Landscaping" sign, plants and flowers outside,
wheelbarrow, garden tools visible, warm welcoming,
16-bit RPG style, top-down view, 128x128 pixels, transparent background
```

### Tony's Pizzeria

```
Pixel art building sprite, cozy Italian pizzeria restaurant,
red and white striped awning, "Pizzeria" neon sign,
outdoor tables, pizza oven visible through window,
brick facade, warm lighting,
16-bit RPG style, top-down view, 128x128 pixels, transparent background
```

### Nexus Tech Office

```
Pixel art building sprite, modern tech startup office,
glass windows, minimalist design, "Tech" sign,
sleek gray and blue colors, potted plants,
16-bit RPG style, top-down view, 128x128 pixels, transparent background
```

### Main Street Dental

```
Pixel art building sprite, friendly dental clinic,
clean white exterior, blue "Dental" sign with tooth logo,
large windows, professional medical building,
16-bit RPG style, top-down view, 128x128 pixels, transparent background
```

### Harbor Realty Office

```
Pixel art building sprite, real estate office storefront,
"Realty" sign, house logos in window, professional look,
warm brown and gold colors, welcoming entrance,
16-bit RPG style, top-down view, 128x128 pixels, transparent background
```

### Town Hall / Central Building

```
Pixel art building sprite, small town hall or civic center,
clock tower, columns at entrance, flags,
classic brick architecture, central plaza feel,
16-bit RPG style, top-down view, 192x192 pixels, transparent background
```

---

## Town Environment

### Street Tiles

```
Pixel art tileset, town street tiles, cobblestone road,
sidewalk, crosswalk, street corners, manhole covers,
16-bit RPG style, top-down view, 32x32 tile size, seamless
```

### Park/Green Space

```
Pixel art tileset, town park elements, grass tiles,
park bench, fountain, trees, flower beds, lamp post,
16-bit RPG style, top-down view, 32x32 tile size
```

### Town Square

```
Pixel art scene, small town square with fountain,
benches, lamp posts, flower planters, paved area,
surrounded by grass, welcoming community space,
16-bit RPG style, top-down view, 256x256 pixels
```

---

## UI Elements

### Financial Icons

```
Pixel art icon set, accounting and finance icons,
dollar sign, invoice document, calculator, credit card,
bank building, coin stack, chart graph, wallet,
16-bit style, 32x32 pixels each, transparent background
```

### Status Icons

```
Pixel art icon set, status indicators,
green checkmark, red X, yellow warning triangle,
blue info circle, clock/time, calendar,
16-bit style, 24x24 pixels each, transparent background
```

### Transaction Type Icons

```
Pixel art icon set, business transaction types,
invoice (paper with lines), bill (paper with stamp),
payment (hand with money), journal entry (ledger book),
receipt, bank statement,
16-bit style, 32x32 pixels each, transparent background
```

---

## Animation Frames

### Walking Animation (per character)

```
Pixel art sprite sheet, [CHARACTER NAME] walking animation,
4 directions (down, up, left, right), 4 frames each direction,
16 total frames arranged in grid, smooth walk cycle,
16-bit RPG style, 64x64 per frame, transparent background
```

### Idle Animation

```
Pixel art sprite sheet, [CHARACTER NAME] idle animation,
subtle breathing/movement, 4 frames loop,
professional standing pose,
16-bit RPG style, 64x64 per frame, transparent background
```

### Working Animation (Sarah)

```
Pixel art sprite sheet, accountant working animation,
writing on clipboard, typing, reviewing documents,
4-6 frames loop, professional office work,
16-bit RPG style, 64x64 per frame, transparent background
```

---

## Color Palettes

### Suggested Character Palettes

| Character | Primary | Secondary | Accent |
|-----------|---------|-----------|--------|
| Sarah | Navy Blue #2C3E50 | White #ECF0F1 | Gold #F39C12 |
| Craig | Forest Green #27AE60 | Tan #D4A574 | Brown #8B4513 |
| Tony | Chef White #FDFEFE | Red #E74C3C | Cream #FDF5E6 |
| Maya | Purple #9B59B6 | Gray #95A5A6 | Teal #1ABC9C |
| Dr. Chen | Medical White #F8F9FA | Light Blue #3498DB | Green #2ECC71 |
| Marcus | Navy #1A237E | Red #B71C1C | Gold #FFD700 |

### Building Palette

```
Warm browns: #8B4513, #A0522D, #CD853F
Cool grays: #708090, #778899, #B0C4DE
Accent colors: #E74C3C (red), #27AE60 (green), #3498DB (blue)
```

---

## Batch Generation Tips

1. **Generate base poses first**, then request variations
2. **Keep consistent lighting** - top-left light source
3. **Use same background color** (#FF00FF magenta) for easy removal
4. **Request PNG format** with transparency when possible
5. **Generate at 2x size** (128x128) and downscale for cleaner edges

## File Naming Convention

```
characters/
  sarah_walk_down_01.png
  sarah_walk_down_02.png
  sarah_idle_01.png

buildings/
  landscaping_shop.png
  pizzeria.png

tiles/
  street_horizontal.png
  grass_01.png

icons/
  icon_invoice.png
  icon_payment.png
```

---

## Example Full Prompt

Complete prompt for Sarah Chen sprite sheet:

```
Create a 16-bit pixel art sprite sheet for a professional Asian woman
accountant character named Sarah. She has neat black hair in a bun,
wears glasses, a blue blazer over a white blouse, and carries a clipboard.
Her expression is friendly and competent.

The sprite sheet should include:
- Walking animation in 4 directions (down, up, left, right)
- 4 frames per direction
- 64x64 pixels per frame
- Top-down RPG perspective similar to classic SNES games
- Clean pixel edges, limited color palette
- Transparent background (magenta #FF00FF for easy removal)
- Retro 16-bit aesthetic

Style reference: Final Fantasy 6, Chrono Trigger, Stardew Valley
```
