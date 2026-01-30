/**
 * Tile asset loading for the terrain system.
 * Loads tile sprite textures and provides access to cached textures.
 * Supports both legacy (orthogonal) and isometric tile sprites.
 */

import { Assets, Texture } from "pixi.js";
import { TileType } from "./tileConfig";
import { ISOMETRIC_MODE } from "./isometric";

// Bundle names for tile assets
const TILES_BUNDLE = "tiles";
const ISO_TILES_BUNDLE = "iso_tiles";

// Track loading state
let tilesLoaded = false;
let tilesLoadingPromise: Promise<void> | null = null;

// Texture caches
const tileTextureCache = new Map<TileType, Texture>();
const isoTileTextureCache = new Map<TileType, Texture>();

/**
 * Sprite paths for legacy (orthogonal) tile assets.
 */
const TILE_SPRITE_PATHS: Partial<Record<TileType, string>> = {
  grass: "/sprites/tiles/grass.png",
  road: "/sprites/tiles/road.png",
  sidewalk: "/sprites/tiles/sidewalk.png",
  road_marking: "/sprites/tiles/road_marking.png",
};

/**
 * Sprite paths for isometric tile assets.
 */
const ISO_TILE_SPRITE_PATHS: Partial<Record<TileType, string>> = {
  grass: "/sprites/tiles/isometric/grass.png",
  road: "/sprites/tiles/isometric/road.png",
  sidewalk: "/sprites/tiles/isometric/sidewalk.png",
  road_marking: "/sprites/tiles/isometric/road.png", // Use road for markings in iso
};

/**
 * Register tile assets with the PixiJS Assets system.
 */
function registerTileAssets(): void {
  // Register legacy tile assets
  const legacyAssets: Record<string, string> = {};
  for (const [tileType, path] of Object.entries(TILE_SPRITE_PATHS)) {
    const alias = `tile_${tileType}`;
    legacyAssets[alias] = path;
  }
  if (Object.keys(legacyAssets).length > 0) {
    Assets.addBundle(TILES_BUNDLE, legacyAssets);
  }

  // Register isometric tile assets
  if (ISOMETRIC_MODE) {
    const isoAssets: Record<string, string> = {};
    for (const [tileType, path] of Object.entries(ISO_TILE_SPRITE_PATHS)) {
      const alias = `iso_tile_${tileType}`;
      isoAssets[alias] = path;
    }
    if (Object.keys(isoAssets).length > 0) {
      Assets.addBundle(ISO_TILES_BUNDLE, isoAssets);
    }
  }
}

/**
 * Load all tile sprite assets.
 * @param onProgress - Optional callback for loading progress (0-1)
 */
export async function loadTileAssets(
  onProgress?: (progress: number) => void
): Promise<void> {
  // Return existing promise if already loading
  if (tilesLoadingPromise) {
    return tilesLoadingPromise;
  }

  // Return immediately if already loaded
  if (tilesLoaded) {
    onProgress?.(1);
    return;
  }

  tilesLoadingPromise = (async () => {
    try {
      // Register assets
      registerTileAssets();

      // Load legacy tiles
      if (Object.keys(TILE_SPRITE_PATHS).length > 0) {
        await Assets.loadBundle(TILES_BUNDLE, (progress) => {
          onProgress?.(ISOMETRIC_MODE ? progress * 0.5 : progress);
        });

        // Cache loaded legacy textures
        for (const tileType of Object.keys(TILE_SPRITE_PATHS) as TileType[]) {
          const alias = `tile_${tileType}`;
          try {
            const texture = Assets.get<Texture>(alias);
            if (texture) {
              tileTextureCache.set(tileType, texture);
            }
          } catch {
            // Texture not found, will use procedural fallback
          }
        }
      }

      // Load isometric tiles if in isometric mode
      if (ISOMETRIC_MODE && Object.keys(ISO_TILE_SPRITE_PATHS).length > 0) {
        await Assets.loadBundle(ISO_TILES_BUNDLE, (progress) => {
          onProgress?.(0.5 + progress * 0.5);
        });

        // Cache loaded isometric textures
        for (const tileType of Object.keys(ISO_TILE_SPRITE_PATHS) as TileType[]) {
          const alias = `iso_tile_${tileType}`;
          try {
            const texture = Assets.get<Texture>(alias);
            if (texture) {
              isoTileTextureCache.set(tileType, texture);
            }
          } catch {
            // Texture not found, will use fallback
          }
        }
      }

      tilesLoaded = true;
      onProgress?.(1);
    } catch (error) {
      console.error("Failed to load tile assets:", error);
      // Don't throw - allow fallback to procedural rendering
      tilesLoaded = true;
    } finally {
      tilesLoadingPromise = null;
    }
  })();

  return tilesLoadingPromise;
}

/**
 * Check if tile assets have been loaded.
 */
export function areTileAssetsLoaded(): boolean {
  return tilesLoaded;
}

/**
 * Get the texture for a tile type, if available.
 * In isometric mode, prefers isometric textures with fallback to legacy.
 * @param type - The tile type
 * @returns The texture if loaded, undefined otherwise
 */
export function getTileTexture(type: TileType): Texture | undefined {
  if (ISOMETRIC_MODE) {
    // Prefer isometric texture, fallback to legacy
    return isoTileTextureCache.get(type) ?? tileTextureCache.get(type);
  }
  return tileTextureCache.get(type);
}

/**
 * Get the isometric texture specifically (for rendering).
 */
export function getIsoTileTexture(type: TileType): Texture | undefined {
  return isoTileTextureCache.get(type);
}
