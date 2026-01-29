/**
 * Tile asset loading for the terrain system.
 * Loads tile sprite textures and provides access to cached textures.
 */

import { Assets, Texture } from "pixi.js";
import { TileType } from "./tileConfig";

// Bundle name for tile assets
const TILES_BUNDLE = "tiles";

// Track loading state
let tilesLoaded = false;
let tilesLoadingPromise: Promise<void> | null = null;

// Texture cache
const tileTextureCache = new Map<TileType, Texture>();

/**
 * Sprite paths for tile assets (relative to public/).
 */
const TILE_SPRITE_PATHS: Partial<Record<TileType, string>> = {
  grass: "/sprites/tiles/grass.png",
  road: "/sprites/tiles/road.png",
  sidewalk: "/sprites/tiles/sidewalk.png",
  road_marking: "/sprites/tiles/road_marking.png",
};

/**
 * Register tile assets with the PixiJS Assets system.
 */
function registerTileAssets(): void {
  const assets: Record<string, string> = {};

  for (const [tileType, path] of Object.entries(TILE_SPRITE_PATHS)) {
    const alias = `tile_${tileType}`;
    assets[alias] = path;
  }

  if (Object.keys(assets).length > 0) {
    Assets.addBundle(TILES_BUNDLE, assets);
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

      // Only load if we have sprite paths defined
      if (Object.keys(TILE_SPRITE_PATHS).length > 0) {
        await Assets.loadBundle(TILES_BUNDLE, (progress) => {
          onProgress?.(progress);
        });

        // Cache loaded textures
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
 * @param type - The tile type
 * @returns The texture if loaded, undefined otherwise
 */
export function getTileTexture(type: TileType): Texture | undefined {
  return tileTextureCache.get(type);
}
