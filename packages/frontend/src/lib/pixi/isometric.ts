/**
 * Isometric coordinate system utilities for Atlas Town.
 *
 * Handles transformation between grid coordinates (game logic) and screen coordinates (rendering).
 * Uses a 2:1 ratio isometric projection where tiles are diamond-shaped on screen.
 *
 * Grid coordinates: Logical position in the game world (integers)
 * Screen coordinates: Pixel position for rendering (can be floating point)
 */

// ============================================
// FEATURE FLAG
// ============================================

/**
 * Toggle for isometric mode during development.
 * When false, falls back to top-down orthogonal view.
 */
export const ISOMETRIC_MODE = true;

// ============================================
// TILE DIMENSIONS
// ============================================

/**
 * Isometric tile dimensions (2:1 ratio).
 * Width is the full horizontal span of the diamond.
 * Height is the full vertical span of the diamond.
 */
export const ISO_TILE_WIDTH = 64;
export const ISO_TILE_HEIGHT = 32;

/**
 * Half-dimensions for calculations (frequently used).
 */
export const ISO_TILE_HALF_WIDTH = ISO_TILE_WIDTH / 2;
export const ISO_TILE_HALF_HEIGHT = ISO_TILE_HEIGHT / 2;

/**
 * Legacy top-down tile size for fallback mode.
 */
export const LEGACY_TILE_SIZE = 32;

// ============================================
// COORDINATE TRANSFORMATION
// ============================================

export interface Point {
  x: number;
  y: number;
}

export interface GridPosition {
  gridX: number;
  gridY: number;
}

/**
 * Convert grid coordinates to screen coordinates (isometric projection).
 *
 * In isometric view:
 * - Moving +1 in gridX moves the sprite right and down
 * - Moving +1 in gridY moves the sprite left and down
 *
 * @param gridX - X position in grid coordinates
 * @param gridY - Y position in grid coordinates
 * @returns Screen position in pixels
 */
export function gridToScreen(gridX: number, gridY: number): Point {
  if (!ISOMETRIC_MODE) {
    // Fallback to orthogonal projection
    return {
      x: gridX * LEGACY_TILE_SIZE,
      y: gridY * LEGACY_TILE_SIZE,
    };
  }

  return {
    x: (gridX - gridY) * ISO_TILE_HALF_WIDTH,
    y: (gridX + gridY) * ISO_TILE_HALF_HEIGHT,
  };
}

/**
 * Convert screen coordinates to grid coordinates (reverse projection).
 *
 * Useful for:
 * - Mouse picking (clicking on tiles)
 * - Path finding
 * - Collision detection
 *
 * @param screenX - X position in pixels
 * @param screenY - Y position in pixels
 * @returns Grid position (floored to integers)
 */
export function screenToGrid(screenX: number, screenY: number): GridPosition {
  if (!ISOMETRIC_MODE) {
    // Fallback to orthogonal projection
    return {
      gridX: Math.floor(screenX / LEGACY_TILE_SIZE),
      gridY: Math.floor(screenY / LEGACY_TILE_SIZE),
    };
  }

  // Reverse the isometric transformation
  // x = (gx - gy) * halfW  =>  x/halfW = gx - gy
  // y = (gx + gy) * halfH  =>  y/halfH = gx + gy
  //
  // Adding both equations: x/halfW + y/halfH = 2*gx  =>  gx = (x/halfW + y/halfH) / 2
  // Subtracting: y/halfH - x/halfW = 2*gy  =>  gy = (y/halfH - x/halfW) / 2

  const gx = (screenX / ISO_TILE_HALF_WIDTH + screenY / ISO_TILE_HALF_HEIGHT) / 2;
  const gy = (screenY / ISO_TILE_HALF_HEIGHT - screenX / ISO_TILE_HALF_WIDTH) / 2;

  return {
    gridX: Math.floor(gx),
    gridY: Math.floor(gy),
  };
}

/**
 * Get the precise grid position (without flooring) for smooth interpolation.
 *
 * @param screenX - X position in pixels
 * @param screenY - Y position in pixels
 * @returns Precise grid position (floating point)
 */
export function screenToGridPrecise(screenX: number, screenY: number): Point {
  if (!ISOMETRIC_MODE) {
    return {
      x: screenX / LEGACY_TILE_SIZE,
      y: screenY / LEGACY_TILE_SIZE,
    };
  }

  return {
    x: (screenX / ISO_TILE_HALF_WIDTH + screenY / ISO_TILE_HALF_HEIGHT) / 2,
    y: (screenY / ISO_TILE_HALF_HEIGHT - screenX / ISO_TILE_HALF_WIDTH) / 2,
  };
}

// ============================================
// DEPTH SORTING
// ============================================

/**
 * Calculate the depth value for z-sorting (painter's algorithm).
 *
 * In isometric view, objects further down and to the right should render
 * on top of objects to their upper-left. This is achieved by summing
 * the grid coordinates.
 *
 * @param gridX - X position in grid coordinates
 * @param gridY - Y position in grid coordinates
 * @returns Depth value (higher = rendered later / on top)
 */
export function calculateDepth(gridX: number, gridY: number): number {
  if (!ISOMETRIC_MODE) {
    // In orthogonal view, just use Y for depth
    return gridY;
  }

  // In isometric, objects at higher (gridX + gridY) are "in front"
  return gridX + gridY;
}

/**
 * Calculate depth from screen Y position.
 *
 * This is a simpler approach that works well with PixiJS's sortableChildren,
 * since screen Y naturally increases as we go "deeper" into the scene.
 *
 * @param screenY - Y position in pixels
 * @returns Depth value for sorting
 */
export function calculateDepthFromScreenY(screenY: number): number {
  return screenY;
}

// ============================================
// TILE RENDERING HELPERS
// ============================================

/**
 * Get the four corner points of an isometric tile at a grid position.
 * Useful for drawing tile outlines or hit testing.
 *
 * Returns points in clockwise order: top, right, bottom, left
 *
 * @param gridX - X position in grid coordinates
 * @param gridY - Y position in grid coordinates
 * @returns Array of 4 corner points
 */
export function getTileCorners(gridX: number, gridY: number): [Point, Point, Point, Point] {
  const center = gridToScreen(gridX, gridY);

  if (!ISOMETRIC_MODE) {
    // Orthogonal square corners
    return [
      { x: center.x, y: center.y },
      { x: center.x + LEGACY_TILE_SIZE, y: center.y },
      { x: center.x + LEGACY_TILE_SIZE, y: center.y + LEGACY_TILE_SIZE },
      { x: center.x, y: center.y + LEGACY_TILE_SIZE },
    ];
  }

  // Isometric diamond corners (top, right, bottom, left)
  return [
    { x: center.x, y: center.y - ISO_TILE_HALF_HEIGHT }, // Top
    { x: center.x + ISO_TILE_HALF_WIDTH, y: center.y },  // Right
    { x: center.x, y: center.y + ISO_TILE_HALF_HEIGHT }, // Bottom
    { x: center.x - ISO_TILE_HALF_WIDTH, y: center.y },  // Left
  ];
}

/**
 * Get the center point of a tile at a grid position.
 * This is where sprites should be anchored for proper positioning.
 *
 * @param gridX - X position in grid coordinates
 * @param gridY - Y position in grid coordinates
 * @returns Center point of the tile
 */
export function getTileCenter(gridX: number, gridY: number): Point {
  return gridToScreen(gridX, gridY);
}

// ============================================
// GRID BOUNDS & VALIDATION
// ============================================

/**
 * Calculate the screen bounds needed to display a grid of a given size.
 *
 * @param gridWidth - Width of the grid in tiles
 * @param gridHeight - Height of the grid in tiles
 * @returns Object with width, height, and offset for centering
 */
export function calculateScreenBounds(gridWidth: number, gridHeight: number): {
  width: number;
  height: number;
  offsetX: number;
  offsetY: number;
} {
  if (!ISOMETRIC_MODE) {
    return {
      width: gridWidth * LEGACY_TILE_SIZE,
      height: gridHeight * LEGACY_TILE_SIZE,
      offsetX: 0,
      offsetY: 0,
    };
  }

  // In isometric, the width spans from the leftmost tile (0, gridHeight-1)
  // to the rightmost tile (gridWidth-1, 0)
  const totalWidth = (gridWidth + gridHeight) * ISO_TILE_HALF_WIDTH;
  const totalHeight = (gridWidth + gridHeight) * ISO_TILE_HALF_HEIGHT;

  // Offset to center the grid (tile 0,0 starts at a specific position)
  const offsetX = gridHeight * ISO_TILE_HALF_WIDTH;
  const offsetY = 0;

  return {
    width: totalWidth,
    height: totalHeight,
    offsetX,
    offsetY,
  };
}

/**
 * Check if a grid position is within valid bounds.
 *
 * @param gridX - X position in grid coordinates
 * @param gridY - Y position in grid coordinates
 * @param gridWidth - Width of the grid
 * @param gridHeight - Height of the grid
 * @returns True if position is valid
 */
export function isValidGridPosition(
  gridX: number,
  gridY: number,
  gridWidth: number,
  gridHeight: number
): boolean {
  return gridX >= 0 && gridX < gridWidth && gridY >= 0 && gridY < gridHeight;
}

// ============================================
// DIRECTION HELPERS
// ============================================

/**
 * 8-directional facing directions for isometric movement.
 */
export type IsoDirection =
  | "south"
  | "south-west"
  | "west"
  | "north-west"
  | "north"
  | "north-east"
  | "east"
  | "south-east";

/**
 * All 8 directions in clockwise order starting from south.
 */
export const ISO_DIRECTIONS: IsoDirection[] = [
  "south",
  "south-west",
  "west",
  "north-west",
  "north",
  "north-east",
  "east",
  "south-east",
];

/**
 * Map 4-direction names to isometric 8-direction equivalents.
 * Useful for legacy compatibility.
 */
export const DIRECTION_4_TO_8: Record<string, IsoDirection> = {
  south: "south",
  west: "west",
  north: "north",
  east: "east",
};

/**
 * Calculate the facing direction from a movement vector.
 * Returns one of 8 directions based on the angle of movement.
 *
 * @param dx - Change in grid X (or screen X)
 * @param dy - Change in grid Y (or screen Y)
 * @returns The closest of 8 directions, or undefined if no movement
 */
export function getDirectionFromDelta(dx: number, dy: number): IsoDirection | undefined {
  if (dx === 0 && dy === 0) {
    return undefined;
  }

  // Calculate angle in radians (-PI to PI)
  const angle = Math.atan2(dy, dx);

  // Convert to degrees (0 to 360)
  let degrees = (angle * 180 / Math.PI + 360) % 360;

  // Map angle to 8 directions
  // East = 0°, South = 90°, West = 180°, North = 270°
  // Each direction spans 45° (360° / 8)

  const directionIndex = Math.round(degrees / 45) % 8;

  // Map index to direction (starting from East = 0)
  const directionMap: IsoDirection[] = [
    "east",
    "south-east",
    "south",
    "south-west",
    "west",
    "north-west",
    "north",
    "north-east",
  ];

  return directionMap[directionIndex];
}

/**
 * Get the unit vector for a direction (for movement calculations).
 *
 * @param direction - The facing direction
 * @returns Unit vector {x, y} for that direction
 */
export function getDirectionVector(direction: IsoDirection): Point {
  const vectors: Record<IsoDirection, Point> = {
    "north": { x: 0, y: -1 },
    "north-east": { x: 0.707, y: -0.707 },
    "east": { x: 1, y: 0 },
    "south-east": { x: 0.707, y: 0.707 },
    "south": { x: 0, y: 1 },
    "south-west": { x: -0.707, y: 0.707 },
    "west": { x: -1, y: 0 },
    "north-west": { x: -0.707, y: -0.707 },
  };

  return vectors[direction];
}
