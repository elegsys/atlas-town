/**
 * EntityManager - Manages all dynamic entities (buildings, characters) with depth sorting.
 *
 * Responsibilities:
 * - Maintains sortableChildren container for proper depth ordering
 * - Provides add/remove/get operations for entities
 * - Updates depth sorting when entities move
 */

import { Container } from "pixi.js";
import { IsometricCamera } from "./IsometricCamera";
import { IsometricEntity } from "./IsometricEntity";

export class EntityManager {
  /** The PixiJS container for all entities (sortableChildren = true) */
  public readonly container: Container;

  /** Reference to the camera (stored for future use) */
  public readonly camera: IsometricCamera;

  /** Map of entity ID to entity instance */
  private entities: Map<string, IsometricEntity> = new Map();

  constructor(camera: IsometricCamera) {
    this.camera = camera;

    // Create sortable container for depth-sorted rendering
    this.container = new Container();
    this.container.label = "entities";
    this.container.sortableChildren = true;
  }

  // ============================================
  // ENTITY MANAGEMENT
  // ============================================

  /**
   * Add an entity to the manager.
   * The entity's container will be added to the entity container.
   */
  add(entity: IsometricEntity): void {
    if (this.entities.has(entity.id)) {
      console.warn(`Entity with id "${entity.id}" already exists, replacing.`);
      this.remove(entity.id);
    }

    this.entities.set(entity.id, entity);
    this.container.addChild(entity.container);
  }

  /**
   * Remove an entity from the manager.
   * Returns the removed entity, or undefined if not found.
   */
  remove(id: string): IsometricEntity | undefined {
    const entity = this.entities.get(id);
    if (entity) {
      this.container.removeChild(entity.container);
      this.entities.delete(id);
    }
    return entity;
  }

  /**
   * Get an entity by ID.
   */
  get(id: string): IsometricEntity | undefined {
    return this.entities.get(id);
  }

  /**
   * Check if an entity exists.
   */
  has(id: string): boolean {
    return this.entities.has(id);
  }

  /**
   * Get all entities.
   */
  getAll(): IsometricEntity[] {
    return Array.from(this.entities.values());
  }

  /**
   * Get all entity IDs.
   */
  getAllIds(): string[] {
    return Array.from(this.entities.keys());
  }

  /**
   * Get the number of entities.
   */
  get count(): number {
    return this.entities.size;
  }

  // ============================================
  // QUERIES
  // ============================================

  /**
   * Get all entities at a specific grid position.
   */
  getAt(gridX: number, gridY: number): IsometricEntity[] {
    return this.getAll().filter(
      (entity) => entity.gridX === gridX && entity.gridY === gridY
    );
  }

  /**
   * Get all entities within a grid rectangle.
   */
  getInRect(
    minX: number,
    minY: number,
    maxX: number,
    maxY: number
  ): IsometricEntity[] {
    return this.getAll().filter(
      (entity) =>
        entity.gridX >= minX &&
        entity.gridX <= maxX &&
        entity.gridY >= minY &&
        entity.gridY <= maxY
    );
  }

  /**
   * Get the nearest entity to a grid position.
   */
  getNearest(gridX: number, gridY: number): IsometricEntity | undefined {
    let nearest: IsometricEntity | undefined;
    let nearestDistance = Infinity;

    this.entities.forEach((entity) => {
      const dx = entity.gridX - gridX;
      const dy = entity.gridY - gridY;
      const distance = Math.sqrt(dx * dx + dy * dy);

      if (distance < nearestDistance) {
        nearestDistance = distance;
        nearest = entity;
      }
    });

    return nearest;
  }

  // ============================================
  // DEPTH SORTING
  // ============================================

  /**
   * Update depth (zIndex) for all entities.
   * Call this after batch position updates.
   */
  updateAllDepths(): void {
    this.entities.forEach((entity) => {
      entity.updateDepth();
    });
  }

  /**
   * Force re-sort the container.
   * Usually not needed as PixiJS auto-sorts when zIndex changes.
   */
  sortChildren(): void {
    this.container.sortChildren();
  }

  // ============================================
  // ITERATION
  // ============================================

  /**
   * Iterate over all entities.
   */
  forEach(callback: (entity: IsometricEntity, id: string) => void): void {
    this.entities.forEach(callback);
  }

  /**
   * Map over all entities.
   */
  map<T>(callback: (entity: IsometricEntity, id: string) => T): T[] {
    const results: T[] = [];
    this.entities.forEach((entity, id) => {
      results.push(callback(entity, id));
    });
    return results;
  }

  /**
   * Filter entities.
   */
  filter(
    predicate: (entity: IsometricEntity, id: string) => boolean
  ): IsometricEntity[] {
    const results: IsometricEntity[] = [];
    this.entities.forEach((entity, id) => {
      if (predicate(entity, id)) {
        results.push(entity);
      }
    });
    return results;
  }

  // ============================================
  // CLEANUP
  // ============================================

  /**
   * Remove all entities.
   */
  clear(): void {
    this.entities.forEach((entity) => {
      this.container.removeChild(entity.container);
    });
    this.entities.clear();
  }

  /**
   * Destroy the manager and all entities.
   */
  destroy(): void {
    this.entities.forEach((entity) => {
      entity.destroy();
    });
    this.entities.clear();
    this.container.destroy({ children: true });
  }
}
