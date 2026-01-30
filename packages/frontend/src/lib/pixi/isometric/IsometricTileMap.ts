/**
 * IsometricTileMap - Handles static terrain rendering for the isometric grid.
 *
 * Responsible for:
 * - Rendering tile sprites in correct isometric positions
 * - Managing the terrain container
 * - Tile queries (getTileAt)
 * - Future: visibility culling for optimization
 */

import { Container, Sprite, Graphics, Texture } from "pixi.js";
import { IsometricCamera } from "./IsometricCamera";
import {
  GRID_WIDTH,
  GRID_HEIGHT,
  ISO_TILE_WIDTH,
  ISO_TILE_HEIGHT,
  ISOMETRIC_MODE,
  LEGACY_TILE_SIZE,
} from "./constants";

// ============================================
// TILE TYPE DEFINITIONS
// ============================================

export type TileType = "grass" | "road" | "sidewalk" | "road_marking";

export interface TileDefinition {
  type: TileType;
  color: number;
  nightColor: number;
  spritePath?: string;
  isoSpritePath?: string;
}

export const TILE_DEFINITIONS: Record<TileType, TileDefinition> = {
  grass: {
    type: "grass",
    color: 0x90ee90,
    nightColor: 0x2d5a27,
    spritePath: "/sprites/tiles/grass.png",
    isoSpritePath: "/sprites/tiles/isometric/grass.png",
  },
  road: {
    type: "road",
    color: 0x696969,
    nightColor: 0x3d3d3d,
    spritePath: "/sprites/tiles/road.png",
    isoSpritePath: "/sprites/tiles/isometric/road.png",
  },
  sidewalk: {
    type: "sidewalk",
    color: 0xc0c0c0,
    nightColor: 0x808080,
    spritePath: "/sprites/tiles/sidewalk.png",
    isoSpritePath: "/sprites/tiles/isometric/sidewalk.png",
  },
  road_marking: {
    type: "road_marking",
    color: 0xffff00,
    nightColor: 0xb0b000,
    spritePath: "/sprites/tiles/road_marking.png",
    isoSpritePath: "/sprites/tiles/isometric/road.png", // Use road tile for markings in isometric
  },
};

export class IsometricTileMap {
  /** The PixiJS container for all tile sprites */
  public readonly container: Container;

  /** Reference to the camera for coordinate transforms */
  private readonly camera: IsometricCamera;

  /** Grid dimensions */
  private readonly gridWidth: number;
  private readonly gridHeight: number;

  /** Tile data (2D array of tile types) */
  private tileData: TileType[][];

  /** Texture cache for tiles */
  private textureCache: Map<TileType, Texture> = new Map();

  /** Whether tile assets have been loaded */
  private assetsLoaded = false;

  constructor(
    camera: IsometricCamera,
    options?: {
      gridWidth?: number;
      gridHeight?: number;
    }
  ) {
    this.camera = camera;
    this.gridWidth = options?.gridWidth ?? GRID_WIDTH;
    this.gridHeight = options?.gridHeight ?? GRID_HEIGHT;

    // Create container
    this.container = new Container();
    this.container.label = "terrain";

    // Generate initial tile data
    this.tileData = this.generateTownLayout();
  }

  // ============================================
  // ASSET LOADING
  // ============================================

  /**
   * Set a texture for a tile type (called after assets load).
   */
  setTileTexture(tileType: TileType, texture: Texture): void {
    this.textureCache.set(tileType, texture);
  }

  /**
   * Mark assets as loaded.
   */
  setAssetsLoaded(loaded: boolean): void {
    this.assetsLoaded = loaded;
  }

  /**
   * Get texture for a tile type.
   */
  getTileTexture(tileType: TileType): Texture | undefined {
    return this.textureCache.get(tileType);
  }

  // ============================================
  // LAYOUT GENERATION
  // ============================================

  /**
   * Generate the town layout as a 2D grid of tile types.
   *
   * For STAGGERED mode:
   * - Grid is rectangular, rows alternate offset
   * - Road runs horizontally along constant gridY
   * - North = lower gridY (above on screen)
   *
   * For DIAMOND mode:
   * - Road at constant gridY appears diagonal on screen
   */
  private generateTownLayout(): TileType[][] {
    const layout: TileType[][] = [];

    // Initialize all tiles as grass
    for (let y = 0; y < this.gridHeight; y++) {
      layout[y] = [];
      for (let x = 0; x < this.gridWidth; x++) {
        layout[y][x] = "grass";
      }
    }

    if (ISOMETRIC_MODE) {
      // Road runs along constant gridY
      // Center Y = gridHeight / 2 = 9 for 18-height grid
      const roadCenterY = Math.floor(this.gridHeight / 2);
      const roadHalfWidth = 1; // Road spans 3 rows

      for (let y = 0; y < this.gridHeight; y++) {
        for (let x = 0; x < this.gridWidth; x++) {
          // Main street band
          if (y >= roadCenterY - roadHalfWidth && y <= roadCenterY + roadHalfWidth) {
            layout[y][x] = "road";
          }

          // Center marking
          if (y === roadCenterY) {
            layout[y][x] = "road_marking";
          }

          // North sidewalk (lower gridY = above road on screen)
          if (y === roadCenterY - roadHalfWidth - 1) {
            layout[y][x] = "sidewalk";
          }

          // South sidewalk (higher gridY = below road on screen)
          if (y === roadCenterY + roadHalfWidth + 1) {
            layout[y][x] = "sidewalk";
          }
        }
      }
    }

    return layout;
  }

  // ============================================
  // RENDERING
  // ============================================

  /**
   * Build/render all tiles. Call after assets are loaded.
   */
  build(): void {
    // Clear existing children
    this.container.removeChildren();

    // Render tiles back-to-front for proper depth
    for (let gridY = 0; gridY < this.gridHeight; gridY++) {
      for (let gridX = 0; gridX < this.gridWidth; gridX++) {
        this.renderTile(gridX, gridY);
      }
    }
  }

  /**
   * Render a single tile at the given grid position.
   */
  private renderTile(gridX: number, gridY: number): void {
    const tileType = this.tileData[gridY]?.[gridX] ?? "grass";
    const tileDef = TILE_DEFINITIONS[tileType];
    const screenPos = this.camera.gridToScreen(gridX, gridY);

    // Try to use sprite texture if loaded
    const texture = this.textureCache.get(tileType);

    if (texture && this.assetsLoaded) {
      const sprite = new Sprite(texture);

      if (ISOMETRIC_MODE) {
        // Isometric positioning: anchor at center-bottom of diamond
        sprite.anchor.set(0.5, 1);
        sprite.position.set(screenPos.x, screenPos.y + ISO_TILE_HEIGHT);
        // Scale to match tile dimensions
        sprite.width = ISO_TILE_WIDTH;
        sprite.height = texture.height * (ISO_TILE_WIDTH / texture.width);
      } else {
        sprite.position.set(screenPos.x, screenPos.y);
        sprite.width = LEGACY_TILE_SIZE;
        sprite.height = LEGACY_TILE_SIZE;
      }

      this.container.addChild(sprite);
    } else {
      // Fallback to colored shape
      const graphics = new Graphics();

      if (ISOMETRIC_MODE) {
        // Draw isometric diamond
        graphics.moveTo(0, -ISO_TILE_HEIGHT / 2);
        graphics.lineTo(ISO_TILE_WIDTH / 2, 0);
        graphics.lineTo(0, ISO_TILE_HEIGHT / 2);
        graphics.lineTo(-ISO_TILE_WIDTH / 2, 0);
        graphics.closePath();
        graphics.fill(tileDef.color);
        graphics.position.set(screenPos.x, screenPos.y);
      } else {
        graphics.rect(0, 0, LEGACY_TILE_SIZE, LEGACY_TILE_SIZE);
        graphics.fill(tileDef.color);
        graphics.position.set(screenPos.x, screenPos.y);
      }

      this.container.addChild(graphics);
    }
  }

  // ============================================
  // TILE QUERIES
  // ============================================

  /**
   * Get the tile type at a grid position.
   */
  getTileAt(gridX: number, gridY: number): TileType {
    if (gridX < 0 || gridX >= this.gridWidth || gridY < 0 || gridY >= this.gridHeight) {
      return "grass";
    }
    return this.tileData[gridY][gridX];
  }

  /**
   * Get the tile definition at a grid position.
   */
  getTileDefinitionAt(gridX: number, gridY: number): TileDefinition {
    const tileType = this.getTileAt(gridX, gridY);
    return TILE_DEFINITIONS[tileType];
  }

  /**
   * Check if a tile is walkable (for pathfinding).
   */
  isWalkable(_gridX: number, _gridY: number): boolean {
    // All current tile types are walkable
    // Future: check tileType for obstacles
    return true;
  }

  /**
   * Set a tile type at a grid position.
   */
  setTileAt(gridX: number, gridY: number, tileType: TileType): void {
    if (gridX >= 0 && gridX < this.gridWidth && gridY >= 0 && gridY < this.gridHeight) {
      this.tileData[gridY][gridX] = tileType;
    }
  }

  // ============================================
  // VISIBILITY CULLING (Future optimization)
  // ============================================

  /**
   * Update visible tiles based on camera position.
   * Call this when camera moves for culling optimization.
   */
  updateVisible(): void {
    // Future: implement tile visibility culling
    // For now, all tiles are rendered
  }
}
