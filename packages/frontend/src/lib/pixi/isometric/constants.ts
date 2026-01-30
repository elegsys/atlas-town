/**
 * Centralized constants for the isometric rendering system.
 *
 * Single source of truth for all dimensions, grid sizes, and configuration.
 * Import from this file instead of duplicating values elsewhere.
 */

// ============================================
// CANVAS DIMENSIONS
// ============================================

export const CANVAS_WIDTH = 1200;
export const CANVAS_HEIGHT = 700;

// ============================================
// TILE DIMENSIONS (2:1 isometric ratio)
// ============================================

export const ISO_TILE_WIDTH = 64;
export const ISO_TILE_HEIGHT = 32;
export const ISO_TILE_HALF_WIDTH = ISO_TILE_WIDTH / 2;
export const ISO_TILE_HALF_HEIGHT = ISO_TILE_HEIGHT / 2;

// Legacy top-down tile size (for fallback mode)
export const LEGACY_TILE_SIZE = 32;

// ============================================
// GRID DIMENSIONS
// ============================================

/**
 * Grid dimensions for optimal canvas coverage.
 *
 * STAGGERED MODE (28×36 grid):
 * - Width: 28 × 64 + 32 = 1824px
 * - Height: 36 × 16 + 16 = 592px (fits 700px canvas)
 * - Road at center gridY = 18
 */
export const GRID_WIDTH = 28;
export const GRID_HEIGHT = 36;

// ============================================
// BUILDING CONFIGURATION
// ============================================

/** Scale factor for building sprites in isometric view */
export const ISO_BUILDING_SCALE = 0.5;

// ============================================
// DEPTH SORTING
// ============================================

/**
 * Base depth offset for entities.
 * Buildings and characters use screen Y position for depth sorting.
 */
export const DEPTH_OFFSET_TILES = 0;
export const DEPTH_OFFSET_ENTITIES = 1000;

// ============================================
// FEATURE FLAGS
// ============================================

/**
 * Toggle for isometric mode during development.
 * When false, falls back to top-down orthogonal view.
 */
export const ISOMETRIC_MODE = true;

/**
 * Isometric projection type:
 * - "diamond": Classic diamond shape (SimCity, Age of Empires)
 * - "staggered": Offset rows fill rectangular canvas (Civilization)
 */
export type IsometricType = "diamond" | "staggered";
export const ISOMETRIC_TYPE: IsometricType = "staggered";
