# PixiJS Sprite & Image Conversion Guide

Practical gotchas and solutions for working with PixiJS v8 and image assets in Atlas Town.

## Image Conversion Gotchas

### 1. File Format vs Extension Mismatch

**Problem**: Source files may have `.png` extension but actually be JPEG data.

```bash
# Check actual format
file assets/sprites/buildings/craigs_landscaping.png
# Output: JPEG image data, JFIF standard 1.01...
```

**Solution**: Always verify with `file` command. ImageMagick handles this automatically during conversion.

### 2. ImageMagick v7 Uses `magick` Not `convert`

**Problem**: The `convert` command is deprecated in ImageMagick v7.

```bash
# Deprecated (shows warning)
convert input.png -resize 360x280 output.png

# Correct for v7+
magick input.png -resize 360x280 output.png
```

### 3. Resize vs Crop Behavior

**Problem**: Using `^` modifier crops images, losing content.

```bash
# CROPS to exact dimensions (loses content on square images)
magick input.png -resize "360x280^" -gravity center -extent 360x280 output.png

# FITS within dimensions (preserves full image)
magick input.png -resize "360x280" output.png
```

**When to use each**:
- Use crop (`^` + `-extent`) when source aspect ratio matches target
- Use fit (no `^`) when you want full image content preserved

### 4. Retina/HiDPI Resolution

**Best Practice**: Generate sprites at 2x resolution for retina displays.

```bash
# For 180x140 display size, generate 360x280 sprites
SCALE=2
target_w=$((180 * SCALE))  # 360
target_h=$((140 * SCALE))  # 280
```

The sprite loader then scales down in code, giving sharp rendering on retina displays.

### 5. Bash Associative Arrays Require Bash 4+

**Problem**: macOS default shell may not support `declare -A`.

```bash
# Fails on older bash
declare -A BUILDINGS=(["key"]="value")

# Solution: Use explicit function calls instead
process_sprite "id" "source" "output" 180 140
```

**Fix**: Use `#!/usr/bin/env bash` shebang and avoid associative arrays for portability.

---

## PixiJS v8 Asset Loading

### 1. Assets API (Not Loader)

PixiJS v8 uses `Assets` class instead of the old `Loader`:

```typescript
import { Assets, Texture, Sprite } from "pixi.js";

// Register assets
Assets.add({ alias: "building_id", src: "/sprites/buildings/file.png" });

// Create bundle
Assets.addBundle("buildings", {
  craigs_landscaping: "/sprites/buildings/craigs_landscaping.png",
  tonys_pizzeria: "/sprites/buildings/tonys_pizzeria.png",
});

// Load with progress
await Assets.loadBundle("buildings", (progress) => {
  console.log(`Loading: ${progress * 100}%`);
});

// Get cached texture
const texture = Assets.get<Texture>("building_id");
```

### 2. Bundle Format for `addBundle`

**Wrong** (TypeScript error):
```typescript
Assets.addBundle("buildings", ["id1", "id2"]);  // Array not allowed
```

**Correct**:
```typescript
Assets.addBundle("buildings", {
  id1: "/path/to/sprite1.png",
  id2: "/path/to/sprite2.png",
});
```

### 3. Sprite Scaling to Fit Dimensions

When source sprites don't match target dimensions:

```typescript
function createScaledBuildingSprite(
  texture: Texture,
  targetWidth: number,
  targetHeight: number
): Sprite {
  const sprite = new Sprite(texture);

  // Scale to FIT within target (preserves aspect ratio)
  const scaleX = targetWidth / texture.width;
  const scaleY = targetHeight / texture.height;
  const scale = Math.min(scaleX, scaleY);
  sprite.scale.set(scale);

  // Center within target area
  const scaledWidth = texture.width * scale;
  const scaledHeight = texture.height * scale;
  sprite.position.set(
    (targetWidth - scaledWidth) / 2,
    (targetHeight - scaledHeight) / 2
  );

  return sprite;
}
```

### 4. Graceful Fallback Pattern

Always provide fallback for failed asset loading:

```typescript
const texture = getBuildingTexture(config.id);
if (texture && areBuildingAssetsLoaded()) {
  // Render sprite
  const sprite = createScaledBuildingSprite(texture, config.width, config.height);
  container.addChild(sprite);
} else {
  // Fallback to procedural rendering
  drawProceduralBuilding(container, config);
}
```

### 5. Loading State in React

Track loading progress for UI feedback:

```typescript
const [isLoading, setIsLoading] = useState(true);
const [loadingProgress, setLoadingProgress] = useState(0);

// In initPixi
try {
  await loadBuildingAssets((progress) => {
    setLoadingProgress(progress);
  });
} catch (error) {
  console.error("Asset load failed, using fallback:", error);
}
setIsLoading(false);
```

---

## Project File Structure

```
packages/frontend/
├── public/
│   └── sprites/
│       └── buildings/           # Processed sprites (2x resolution)
│           ├── craigs_landscaping.png
│           ├── tonys_pizzeria.png
│           └── ...
└── src/
    └── lib/
        └── pixi/
            ├── spriteLoader.ts  # Asset management
            └── townConfig.ts    # Building configs with spritePath

scripts/
└── convert-building-sprites.sh  # Source → public conversion

assets/
└── sprites/                     # Original source sprites (1024x1024)
    └── buildings/
```

---

## Quick Reference Commands

```bash
# Check image format
file path/to/image.png

# Get image dimensions
magick identify -format "%wx%h" image.png

# Convert and resize (fit within)
magick source.png -resize "360x280" -strip output.png

# Convert and crop (exact dimensions)
magick source.png -resize "360x280^" -gravity center -extent "360x280" -strip output.png

# Verify PNG format after conversion
file output.png
# Should show: PNG image data, 360 x 280, 8-bit/color RGB
```

---

## Common Issues Checklist

- [ ] Source files are actual PNG (not JPEG with .png extension)?
- [ ] Using `magick` instead of `convert` for ImageMagick v7?
- [ ] Sprites at 2x resolution for retina?
- [ ] Using fit resize (no `^`) to preserve full image?
- [ ] Bundle format is object, not array?
- [ ] Fallback rendering implemented?
- [ ] Loading state tracked in React component?
