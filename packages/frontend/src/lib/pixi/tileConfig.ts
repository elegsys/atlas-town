/**
 * Tile configuration for the town terrain system.
 * Defines tile types, visual properties, and the town layout grid.
 *
 * Supports both orthogonal (legacy) and isometric view modes.
 */

import { CANVAS_WIDTH, CANVAS_HEIGHT, ROADS } from "./townConfig";
import {
  ISOMETRIC_MODE,
  ISO_TILE_WIDTH,
  ISO_TILE_HEIGHT,
  LEGACY_TILE_SIZE,
  gridToScreen,
  screenToGrid,
  calculateScreenBounds,
} from "./isometric";

// ============================================
// TILE TYPE DEFINITIONS
// ============================================

export type TileType = "grass" | "road" | "sidewalk" | "road_marking";

export interface TileDefinition {
  type: TileType;
  spritePath?: string;
  /** Path to isometric tile sprite */
  isoSpritePath?: string;
  color: number;
  nightColor: number; // Color when phase is night/evening
}

// Tile size in pixels - depends on view mode
export const TILE_SIZE = ISOMETRIC_MODE ? ISO_TILE_WIDTH : LEGACY_TILE_SIZE;
export const TILE_HEIGHT = ISOMETRIC_MODE ? ISO_TILE_HEIGHT : LEGACY_TILE_SIZE;

// Grid dimensions - in isometric mode use wider grid to fill rectangular canvas
// Canvas: 1200×700 pixels, Tile: 64×32 pixels
// Diamond width = (gridW + gridH) × 32, Diamond height = (gridW + gridH) × 16
// For 1200×700 canvas: use 32×20 grid for better coverage with minimal empty corners
export const GRID_WIDTH = ISOMETRIC_MODE ? 32 : Math.ceil(CANVAS_WIDTH / LEGACY_TILE_SIZE);
export const GRID_HEIGHT = ISOMETRIC_MODE ? 20 : Math.ceil(CANVAS_HEIGHT / LEGACY_TILE_SIZE);

// ============================================
// TILE TYPE PROPERTIES
// ============================================

export const TILE_TYPES: Record<TileType, TileDefinition> = {
  grass: {
    type: "grass",
    color: 0x90ee90, // Light green
    nightColor: 0x2d5a27, // Dark green for night
    spritePath: "/sprites/tiles/grass.png",
    isoSpritePath: "/sprites/tiles/isometric/grass.png",
  },
  road: {
    type: "road",
    color: 0x696969, // Dim gray (asphalt)
    nightColor: 0x3d3d3d, // Darker for night
    spritePath: "/sprites/tiles/road.png",
    isoSpritePath: "/sprites/tiles/isometric/road.png",
  },
  sidewalk: {
    type: "sidewalk",
    color: 0xc0c0c0, // Silver/light gray (concrete)
    nightColor: 0x808080, // Darker for night
    spritePath: "/sprites/tiles/sidewalk.png",
    isoSpritePath: "/sprites/tiles/isometric/sidewalk.png",
  },
  road_marking: {
    type: "road_marking",
    color: 0xffff00, // Yellow center line
    nightColor: 0xb0b000, // Dimmer yellow for night
    spritePath: "/sprites/tiles/road_marking.png",
    // No isometric version - use road tile for markings in isometric
    isoSpritePath: "/sprites/tiles/isometric/road.png",
  },
};

// ============================================
// TOWN LAYOUT GENERATION
// ============================================

/**
 * Generate the town layout as a 2D grid of tile types.
 *
 * ISOMETRIC COORDINATE SYSTEM (22×22 grid):
 * - gridX increases → moves RIGHT and DOWN on screen
 * - gridY increases → moves LEFT and DOWN on screen
 * - Same (gridX + gridY) value = same screen Y (visual horizontal line)
 *
 * Layout concept:
 * - Main street runs diagonally through center (gridX + gridY ≈ 10-12)
 * - North-side buildings: lower (gridX + gridY) values, above the street
 * - South-side buildings: higher (gridX + gridY) values, below the street
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

  if (ISOMETRIC_MODE) {
    // === ISOMETRIC LAYOUT (32×20) ===
    // Main street: tiles where gridX + gridY is between 12 and 14
    // This creates a diagonal band that appears horizontal on screen
    // Center of grid: (16, 10), so center sum = 26, half = 13

    for (let y = 0; y < GRID_HEIGHT; y++) {
      for (let x = 0; x < GRID_WIDTH; x++) {
        const sum = x + y;

        // Main street band (visual horizontal road)
        if (sum >= 12 && sum <= 14) {
          layout[y][x] = "road";
        }
        // Center marking
        if (sum === 13) {
          layout[y][x] = "road_marking";
        }
        // North sidewalk (above main street)
        if (sum === 11) {
          layout[y][x] = "sidewalk";
        }
        // South sidewalk (below main street)
        if (sum === 15) {
          layout[y][x] = "sidewalk";
        }
      }
    }

    // Cross street running perpendicular (visual vertical)
    // Runs along gridX = 14-16 for visual vertical road
    for (let y = 8; y < GRID_HEIGHT - 2; y++) {
      layout[y][14] = "road";
      layout[y][15] = "road";
      layout[y][16] = "road";
      // Sidewalks along cross street
      if (y > 8) {
        layout[y][13] = "sidewalk";
        layout[y][17] = "sidewalk";
      }
    }

  } else {
    // === LEGACY TOP-DOWN LAYOUT ===
    const mainStreetStartRow = Math.floor(ROADS.mainStreet.y / LEGACY_TILE_SIZE);
    const mainStreetEndRow = Math.ceil(
      (ROADS.mainStreet.y + ROADS.mainStreet.height) / LEGACY_TILE_SIZE
    );
    const mainStreetCenterRow = Math.floor(
      (ROADS.mainStreet.y + ROADS.mainStreet.height / 2) / LEGACY_TILE_SIZE
    );

    const crossStreetCenterCol = Math.floor(ROADS.crossStreet.x / LEGACY_TILE_SIZE);
    const crossStreetStartCol = crossStreetCenterCol - 1;
    const crossStreetEndCol = crossStreetCenterCol + 1;

    for (let y = mainStreetStartRow; y < mainStreetEndRow; y++) {
      for (let x = 0; x < GRID_WIDTH; x++) {
        layout[y][x] = "road";
      }
    }

    for (let x = 0; x < GRID_WIDTH; x++) {
      if (x < crossStreetStartCol || x > crossStreetEndCol) {
        layout[mainStreetCenterRow][x] = "road_marking";
      }
    }

    for (let y = mainStreetEndRow; y < GRID_HEIGHT; y++) {
      for (let x = crossStreetStartCol; x <= crossStreetEndCol; x++) {
        if (x >= 0 && x < GRID_WIDTH) {
          layout[y][x] = "road";
        }
      }
    }

    const northSidewalkRow = mainStreetStartRow - 1;
    const southSidewalkRow = mainStreetEndRow;

    if (northSidewalkRow >= 0) {
      for (let x = 0; x < GRID_WIDTH; x++) {
        layout[northSidewalkRow][x] = "sidewalk";
      }
    }

    if (southSidewalkRow < GRID_HEIGHT) {
      for (let x = 0; x < GRID_WIDTH; x++) {
        if (x < crossStreetStartCol || x > crossStreetEndCol) {
          layout[southSidewalkRow][x] = "sidewalk";
        }
      }
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
  if (ISOMETRIC_MODE) {
    const result = screenToGrid(worldX, worldY);
    return { x: result.gridX, y: result.gridY };
  }
  return {
    x: Math.floor(worldX / LEGACY_TILE_SIZE),
    y: Math.floor(worldY / LEGACY_TILE_SIZE),
  };
}

/**
 * Convert grid coordinates to world (pixel) coordinates.
 * In isometric mode, returns the center of the tile diamond.
 * In legacy mode, returns the top-left corner of the tile.
 */
export function gridToWorld(gridX: number, gridY: number): { x: number; y: number } {
  if (ISOMETRIC_MODE) {
    const result = gridToScreen(gridX, gridY);
    return { x: result.x, y: result.y };
  }
  return {
    x: gridX * LEGACY_TILE_SIZE,
    y: gridY * LEGACY_TILE_SIZE,
  };
}

/**
 * Get the screen bounds for the current grid configuration.
 */
export function getGridScreenBounds(): { width: number; height: number; offsetX: number; offsetY: number } {
  return calculateScreenBounds(GRID_WIDTH, GRID_HEIGHT);
}
