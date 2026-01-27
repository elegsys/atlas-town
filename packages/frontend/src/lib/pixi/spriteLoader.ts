/**
 * Sprite asset management for PixiJS v8.
 * Handles loading, caching, and retrieval of building textures.
 */

import { Assets, Texture, Sprite } from "pixi.js";

// Sprite paths for each building (relative to public/)
const BUILDING_SPRITE_PATHS: Record<string, string> = {
  craigs_landscaping: "/sprites/buildings/craigs_landscaping.png",
  tonys_pizzeria: "/sprites/buildings/tonys_pizzeria.png",
  nexus_tech: "/sprites/buildings/nexus_tech.png",
  main_street_dental: "/sprites/buildings/main_street_dental.png",
  harbor_realty: "/sprites/buildings/harbor_realty.png",
  office: "/sprites/buildings/sarahs_office.png",
};

// Bundle name for building assets
const BUILDINGS_BUNDLE = "buildings";

// Track whether assets have been loaded
let buildingAssetsLoaded = false;
let loadingPromise: Promise<void> | null = null;

/**
 * Register building assets with the PixiJS Assets system.
 * Must be called before loadBuildingAssets().
 */
function registerBuildingAssets(): void {
  // Add each building sprite to the Assets system
  for (const [id, path] of Object.entries(BUILDING_SPRITE_PATHS)) {
    Assets.add({ alias: id, src: path });
  }

  // Create a bundle containing all building assets
  // PixiJS v8 expects a record of alias -> src for bundles
  Assets.addBundle(BUILDINGS_BUNDLE, BUILDING_SPRITE_PATHS);
}

/**
 * Load all building sprite assets.
 * @param onProgress - Optional callback for loading progress (0-1)
 * @returns Promise that resolves when all assets are loaded
 */
export async function loadBuildingAssets(
  onProgress?: (progress: number) => void
): Promise<void> {
  // Return existing promise if already loading
  if (loadingPromise) {
    return loadingPromise;
  }

  // Return immediately if already loaded
  if (buildingAssetsLoaded) {
    onProgress?.(1);
    return;
  }

  loadingPromise = (async () => {
    try {
      // Register assets first
      registerBuildingAssets();

      // Load the bundle with progress callback
      await Assets.loadBundle(BUILDINGS_BUNDLE, (progress) => {
        onProgress?.(progress);
      });

      buildingAssetsLoaded = true;
    } catch (error) {
      console.error("Failed to load building assets:", error);
      // Don't throw - allow fallback to procedural rendering
      buildingAssetsLoaded = false;
    } finally {
      loadingPromise = null;
    }
  })();

  return loadingPromise;
}

/**
 * Check if building assets have been loaded successfully.
 */
export function areBuildingAssetsLoaded(): boolean {
  return buildingAssetsLoaded;
}

/**
 * Get the texture for a building by its ID.
 * @param buildingId - The building ID (e.g., "craigs_landscaping")
 * @returns The texture if loaded, undefined otherwise
 */
export function getBuildingTexture(buildingId: string): Texture | undefined {
  if (!buildingAssetsLoaded) {
    return undefined;
  }

  try {
    const texture = Assets.get<Texture>(buildingId);
    return texture;
  } catch {
    return undefined;
  }
}

/**
 * Create a sprite scaled to fit within target dimensions.
 * Maintains aspect ratio and centers the sprite.
 * @param texture - The texture to use
 * @param targetWidth - Target width in pixels
 * @param targetHeight - Target height in pixels
 * @returns A Sprite instance positioned at origin, scaled to fit
 */
export function createScaledBuildingSprite(
  texture: Texture,
  targetWidth: number,
  targetHeight: number
): Sprite {
  const sprite = new Sprite(texture);

  // Scale to fit within target dimensions while preserving aspect ratio
  const scaleX = targetWidth / texture.width;
  const scaleY = targetHeight / texture.height;
  const scale = Math.min(scaleX, scaleY);

  sprite.scale.set(scale);

  // Center the sprite within the target area
  const scaledWidth = texture.width * scale;
  const scaledHeight = texture.height * scale;
  sprite.position.set(
    (targetWidth - scaledWidth) / 2,
    (targetHeight - scaledHeight) / 2
  );

  return sprite;
}

/**
 * Get the sprite path for a building ID.
 * Useful for debugging or external access.
 */
export function getBuildingSpritePath(buildingId: string): string | undefined {
  return BUILDING_SPRITE_PATHS[buildingId];
}

/**
 * Reset the asset loader state.
 * Useful for testing or when re-initializing the application.
 */
export function resetBuildingAssets(): void {
  buildingAssetsLoaded = false;
  loadingPromise = null;
}
