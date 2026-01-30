/**
 * Isometric module - Core classes for the isometric rendering system.
 *
 * This module provides a clean separation of concerns for isometric game rendering:
 * - IsometricCamera: Coordinate transforms and viewport management
 * - IsometricTileMap: Static terrain rendering
 * - IsometricEntity: Base class for dynamic entities
 * - EntityManager: Entity container with depth sorting
 */

// Constants (re-export all)
export * from "./constants";
export type { IsometricType } from "./constants";

// Core classes
export { IsometricCamera } from "./IsometricCamera";
export type { Point, GridPosition, ScreenBounds } from "./IsometricCamera";

export { IsometricTileMap, TILE_DEFINITIONS } from "./IsometricTileMap";
export type { TileType, TileDefinition } from "./IsometricTileMap";

export { IsometricEntity } from "./IsometricEntity";
export type { EntityConfig } from "./IsometricEntity";

export { EntityManager } from "./EntityManager";
