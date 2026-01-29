/**
 * Tile configuration for the town terrain system.
 * Defines tile types, visual properties, and the town layout grid.
 */

import { CANVAS_WIDTH, CANVAS_HEIGHT, ROADS } from "./townConfig";

// ============================================
// TILE TYPE DEFINITIONS
// ============================================

export type TileType = "grass" | "road" | "sidewalk" | "road_marking";

export interface TileDefinition {
  type: TileType;
  spritePath?: string;
  color: number;
  nightColor: number; // Color when phase is night/evening
}

// Tile size in pixels (32px for classic pixel-art feel)
export const TILE_SIZE = 32;

// Grid dimensions calculated from canvas size
export const GRID_WIDTH = Math.ceil(CANVAS_WIDTH / TILE_SIZE); // 38 tiles
export const GRID_HEIGHT = Math.ceil(CANVAS_HEIGHT / TILE_SIZE); // 22 tiles

// ============================================
// TILE TYPE PROPERTIES
// ============================================

export const TILE_TYPES: Record<TileType, TileDefinition> = {
  grass: {
    type: "grass",
    color: 0x90ee90, // Light green
    nightColor: 0x2d5a27, // Dark green for night
    spritePath: "/sprites/tiles/grass.png",
  },
  road: {
    type: "road",
    color: 0x696969, // Dim gray (asphalt)
    nightColor: 0x3d3d3d, // Darker for night
    spritePath: "/sprites/tiles/road.png",
  },
  sidewalk: {
    type: "sidewalk",
    color: 0xc0c0c0, // Silver/light gray (concrete)
    nightColor: 0x808080, // Darker for night
    spritePath: "/sprites/tiles/sidewalk.png",
  },
  road_marking: {
    type: "road_marking",
    color: 0xffff00, // Yellow center line
    nightColor: 0xb0b000, // Dimmer yellow for night
    spritePath: "/sprites/tiles/road_marking.png",
  },
};

// ============================================
// TOWN LAYOUT GENERATION
// ============================================

/**
 * Generate the town layout as a 2D grid of tile types.
 * Layout is based on current road/building positions from townConfig.
 *
 * Layout concept:
 * - Row 0-7:   Grass (buildings sit on top)
 * - Row 8:    Sidewalk (north side of main street)
 * - Row 9-10:  Road (main street at y=280, height=60)
 * - Row 11:   Sidewalk (south side, includes cross street gap)
 * - Row 12+:  Grass with cross street cutting through
 */
function generateTownLayout(): TileType[][] {
  // Initialize all tiles as grass
  const layout: TileType[][] = [];
  for (let y = 0; y < GRID_HEIGHT; y++) {
    layout[y] = [];
    for (let x = 0; x < GRID_WIDTH; x++) {
      layout[y][x] = "grass";
    }
  }

  // Calculate row ranges for roads based on pixel positions
  // Main street: y=280, height=60 → rows 8-10 (280/32=8.75, (280+60)/32=10.6)
  const mainStreetStartRow = Math.floor(ROADS.mainStreet.y / TILE_SIZE);
  const mainStreetEndRow = Math.ceil(
    (ROADS.mainStreet.y + ROADS.mainStreet.height) / TILE_SIZE
  );
  const mainStreetCenterRow = Math.floor(
    (ROADS.mainStreet.y + ROADS.mainStreet.height / 2) / TILE_SIZE
  );

  // Cross street: x=600, width=40 → columns 18-19 (600/32=18.75)
  const crossStreetCenterCol = Math.floor(ROADS.crossStreet.x / TILE_SIZE);
  const crossStreetStartCol = crossStreetCenterCol - 1;
  const crossStreetEndCol = crossStreetCenterCol + 1;

  // Sidewalk rows (one tile above and below main street)
  const northSidewalkRow = mainStreetStartRow - 1;
  const southSidewalkRow = mainStreetEndRow;

  // Apply main street (horizontal road)
  for (let y = mainStreetStartRow; y < mainStreetEndRow; y++) {
    for (let x = 0; x < GRID_WIDTH; x++) {
      layout[y][x] = "road";
    }
  }

  // Apply road center marking (middle of main street)
  for (let x = 0; x < GRID_WIDTH; x++) {
    // Skip where cross street is (no marking in intersection)
    if (x < crossStreetStartCol || x > crossStreetEndCol) {
      layout[mainStreetCenterRow][x] = "road_marking";
    }
  }

  // Apply cross street (vertical road going south from main street)
  // Goes from main street down to bottom of canvas (toward Sarah's office)
  for (let y = mainStreetEndRow; y < GRID_HEIGHT; y++) {
    for (let x = crossStreetStartCol; x <= crossStreetEndCol; x++) {
      if (x >= 0 && x < GRID_WIDTH) {
        layout[y][x] = "road";
      }
    }
  }

  // Apply north sidewalk (above main street)
  if (northSidewalkRow >= 0) {
    for (let x = 0; x < GRID_WIDTH; x++) {
      layout[northSidewalkRow][x] = "sidewalk";
    }
  }

  // Apply south sidewalk (below main street, with gap for cross street)
  if (southSidewalkRow < GRID_HEIGHT) {
    for (let x = 0; x < GRID_WIDTH; x++) {
      // Skip cross street area
      if (x < crossStreetStartCol || x > crossStreetEndCol) {
        layout[southSidewalkRow][x] = "sidewalk";
      }
    }
  }

  // Apply sidewalks along cross street (east and west sides)
  const crossStreetWestSidewalkCol = crossStreetStartCol - 1;
  const crossStreetEastSidewalkCol = crossStreetEndCol + 1;

  for (let y = southSidewalkRow + 1; y < GRID_HEIGHT; y++) {
    if (crossStreetWestSidewalkCol >= 0) {
      layout[y][crossStreetWestSidewalkCol] = "sidewalk";
    }
    if (crossStreetEastSidewalkCol < GRID_WIDTH) {
      layout[y][crossStreetEastSidewalkCol] = "sidewalk";
    }
  }

  return layout;
}

// The town layout - lazily generated
let _townLayout: TileType[][] | null = null;

/**
 * Get the town layout grid.
 * Layout is generated once and cached.
 */
export function getTownLayout(): TileType[][] {
  if (!_townLayout) {
    _townLayout = generateTownLayout();
  }
  return _townLayout;
}

/**
 * Get the tile definition at a specific grid position.
 * @param gridX - X position in grid coordinates (0 to GRID_WIDTH-1)
 * @param gridY - Y position in grid coordinates (0 to GRID_HEIGHT-1)
 * @returns The tile definition, or grass as fallback for out-of-bounds
 */
export function getTileAt(gridX: number, gridY: number): TileDefinition {
  const layout = getTownLayout();

  // Bounds check
  if (gridX < 0 || gridX >= GRID_WIDTH || gridY < 0 || gridY >= GRID_HEIGHT) {
    return TILE_TYPES.grass;
  }

  const tileType = layout[gridY][gridX];
  return TILE_TYPES[tileType];
}

/**
 * Convert world (pixel) coordinates to grid coordinates.
 */
export function worldToGrid(worldX: number, worldY: number): { x: number; y: number } {
  return {
    x: Math.floor(worldX / TILE_SIZE),
    y: Math.floor(worldY / TILE_SIZE),
  };
}

/**
 * Convert grid coordinates to world (pixel) coordinates.
 * Returns the top-left corner of the tile.
 */
export function gridToWorld(gridX: number, gridY: number): { x: number; y: number } {
  return {
    x: gridX * TILE_SIZE,
    y: gridY * TILE_SIZE,
  };
}
