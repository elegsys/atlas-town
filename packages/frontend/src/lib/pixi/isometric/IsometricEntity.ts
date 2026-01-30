/**
 * IsometricEntity - Base class for all entities in the isometric world.
 *
 * Provides:
 * - Grid-based positioning with automatic screen coordinate updates
 * - Depth calculation for z-sorting
 * - Common interface for buildings and characters
 */

import { Container } from "pixi.js";
import { IsometricCamera } from "./IsometricCamera";
import { ISO_TILE_HEIGHT, ISOMETRIC_MODE } from "./constants";

export interface EntityConfig {
  /** Unique identifier */
  id: string;
  /** Display name */
  name: string;
  /** Initial grid X position */
  gridX: number;
  /** Initial grid Y position */
  gridY: number;
}

export abstract class IsometricEntity {
  /** Unique identifier */
  public readonly id: string;

  /** Display name */
  public readonly name: string;

  /** The PixiJS container for this entity */
  public readonly container: Container;

  /** Reference to the camera for coordinate transforms */
  protected readonly camera: IsometricCamera;

  /** Grid position */
  protected _gridX: number;
  protected _gridY: number;

  constructor(camera: IsometricCamera, config: EntityConfig) {
    this.camera = camera;
    this.id = config.id;
    this.name = config.name;
    this._gridX = config.gridX;
    this._gridY = config.gridY;

    // Create container
    this.container = new Container();
    this.container.label = `entity_${config.id}`;

    // Set initial position
    this.updatePosition();
  }

  // ============================================
  // POSITION MANAGEMENT
  // ============================================

  /** Get grid X position */
  get gridX(): number {
    return this._gridX;
  }

  /** Set grid X position (updates screen position automatically) */
  set gridX(value: number) {
    this._gridX = value;
    this.updatePosition();
  }

  /** Get grid Y position */
  get gridY(): number {
    return this._gridY;
  }

  /** Set grid Y position (updates screen position automatically) */
  set gridY(value: number) {
    this._gridY = value;
    this.updatePosition();
  }

  /** Get screen X position */
  get x(): number {
    return this.container.x;
  }

  /** Get screen Y position */
  get y(): number {
    return this.container.y;
  }

  /**
   * Set grid position (both X and Y at once).
   * More efficient than setting gridX and gridY separately.
   */
  setGridPosition(gridX: number, gridY: number): void {
    this._gridX = gridX;
    this._gridY = gridY;
    this.updatePosition();
  }

  /**
   * Update screen position from current grid position.
   * Called automatically when grid position changes.
   */
  updatePosition(): void {
    const screenPos = this.camera.gridToScreen(this._gridX, this._gridY);
    this.container.x = screenPos.x;
    this.container.y = screenPos.y;
    this.updateDepth();
  }

  /**
   * Set screen position directly (for smooth animations).
   * Does NOT update grid position.
   */
  setScreenPosition(x: number, y: number): void {
    this.container.x = x;
    this.container.y = y;
    this.updateDepth();
  }

  /**
   * Teleport to a grid position instantly.
   */
  teleportToGrid(gridX: number, gridY: number): void {
    this.setGridPosition(gridX, gridY);
  }

  /**
   * Teleport to a screen position instantly.
   * Updates grid position based on screen position.
   */
  teleportToScreen(screenX: number, screenY: number): void {
    this.container.x = screenX;
    this.container.y = screenY;

    // Update grid position from screen position
    const gridPos = this.camera.screenToGrid(screenX, screenY);
    this._gridX = gridPos.gridX;
    this._gridY = gridPos.gridY;

    this.updateDepth();
  }

  // ============================================
  // DEPTH SORTING
  // ============================================

  /**
   * Get the depth value for z-sorting.
   * Higher values render on top.
   */
  get depth(): number {
    return this.camera.calculateDepthFromScreenY(this.container.y);
  }

  /**
   * Update the container's zIndex for proper depth sorting.
   * Called automatically when position changes.
   */
  updateDepth(): void {
    if (ISOMETRIC_MODE) {
      // Use screen Y plus a small offset based on tile height
      // This ensures entities at the same grid position sort correctly
      this.container.zIndex = this.container.y + ISO_TILE_HEIGHT;
    } else {
      this.container.zIndex = this.container.y;
    }
  }

  // ============================================
  // ABSTRACT METHODS
  // ============================================

  /**
   * Build the visual representation of this entity.
   * Called after construction to set up sprites/graphics.
   */
  abstract build(): void;

  /**
   * Clean up resources when destroying the entity.
   */
  destroy(): void {
    this.container.destroy({ children: true });
  }
}
