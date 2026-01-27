#!/usr/bin/env bash
# convert-building-sprites.sh
# Converts source sprites from 1024x1024 JPEG (mislabeled as .png) to properly-sized PNG
# Preserves full image content by resizing to FIT (not crop) within target dimensions
# Requires: ImageMagick (brew install imagemagick)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

INPUT_DIR="$PROJECT_ROOT/assets/sprites"
OUTPUT_DIR="$PROJECT_ROOT/packages/frontend/public/sprites/buildings"

# Create output directory
mkdir -p "$OUTPUT_DIR"

SCALE=2  # 2x resolution for retina

echo "Converting building sprites..."
echo "Output directory: $OUTPUT_DIR"
echo ""

# Process each building with explicit parameters
process_sprite() {
  local id="$1"
  local src="$2"
  local out_name="$3"
  local width="$4"
  local height="$5"

  local target_w=$((width * SCALE))
  local target_h=$((height * SCALE))
  local out="$OUTPUT_DIR/$out_name"

  if [ ! -f "$src" ]; then
    echo "WARNING: Source file not found: $src"
    return
  fi

  echo "Processing $id..."
  echo "  Source: $src"
  echo "  Target: ${target_w}x${target_h} (2x of ${width}x${height})"

  # Convert using ImageMagick:
  # 1. Resize to FIT within target dimensions (no cropping, preserves full image)
  # 2. Use high-quality resampling
  # 3. Strip metadata
  # 4. Output as actual PNG
  magick "$src" \
    -resize "${target_w}x${target_h}" \
    -strip \
    "$out"

  # Verify output
  local actual_dims
  actual_dims=$(magick identify -format "%wx%h" "$out")
  echo "  Output: $out ($actual_dims)"
  echo ""
}

# Building conversions: id, source, output, width, height
process_sprite "craigs_landscaping" \
  "$INPUT_DIR/buildings/craigs_landscaping.png" \
  "craigs_landscaping.png" 180 140

process_sprite "tonys_pizzeria" \
  "$INPUT_DIR/buildings/tonys_pizzeria.png" \
  "tonys_pizzeria.png" 180 140

process_sprite "nexus_tech" \
  "$INPUT_DIR/buildings/nexus_tech.png" \
  "nexus_tech.png" 180 140

process_sprite "main_street_dental" \
  "$INPUT_DIR/buildings/main_street_dental.png" \
  "main_street_dental.png" 180 140

process_sprite "harbor_realty" \
  "$INPUT_DIR/buildings/harbor_realty.png" \
  "harbor_realty.png" 180 140

process_sprite "office" \
  "$INPUT_DIR/extra_buildings/sarahs_office.png" \
  "sarahs_office.png" 200 120

echo "Done! Converted sprites are in $OUTPUT_DIR"
echo ""
echo "Files created:"
ls -la "$OUTPUT_DIR"
