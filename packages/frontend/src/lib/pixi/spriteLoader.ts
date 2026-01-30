/**
 * Sprite asset management for PixiJS v8.
 * Handles loading, caching, and retrieval of building and character textures.
 */

import { Assets, Texture, Sprite } from "pixi.js";
import {
  CHARACTER_SPRITE_PATHS,
  CHARACTER_DEFINITIONS,
  DIRECTIONS_4,
  DIRECTIONS_8,
  WALKING_FRAME_COUNT,
  FacingDirection,
  FacingDirection8,
  DIRECTION_8_TO_4,
  SPRITE_SHEET_BASE,
} from "./characterConfig";
import { ISOMETRIC_MODE } from "./isometric";

// Sprite paths for each building (relative to public/)
const BUILDING_SPRITE_PATHS: Record<string, string> = {
  craigs_landscaping: "/sprites/buildings/craigs_landscaping.png",
  tonys_pizzeria: "/sprites/buildings/tonys_pizzeria.png",
  nexus_tech: "/sprites/buildings/nexus_tech.png",
  main_street_dental: "/sprites/buildings/main_street_dental.png",
  harbor_realty: "/sprites/buildings/harbor_realty.png",
  office: "/sprites/buildings/sarahs_office.png",
};

// Bundle names
const BUILDINGS_BUNDLE = "buildings";
const CHARACTERS_BUNDLE = "characters";
const CHARACTER_SHEETS_BUNDLE = "character_sheets";

// Track whether assets have been loaded
let buildingAssetsLoaded = false;
let characterAssetsLoaded = false;
let characterSheetsLoaded = false;
let buildingLoadingPromise: Promise<void> | null = null;
let characterLoadingPromise: Promise<void> | null = null;
let characterSheetsLoadingPromise: Promise<void> | null = null;

/**
 * Characters missing specific walking directions.
 * Maps characterId -> direction -> fallback direction
 */
const MISSING_WALKING_FALLBACKS: Record<string, Record<string, FacingDirection>> = {
  marcus: { south: "north" },  // Marcus missing south, use north
  maya: { west: "east" },      // Maya missing west, use east
};

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
 * Register character assets with the PixiJS Assets system.
 * Must be called before loadCharacterAssets().
 */
function registerCharacterAssets(): void {
  // Add character alias prefix to avoid collision with buildings
  for (const [id, path] of Object.entries(CHARACTER_SPRITE_PATHS)) {
    Assets.add({ alias: `char_${id}`, src: path });
  }

  // Create prefixed paths for the bundle
  const prefixedPaths = Object.fromEntries(
    Object.entries(CHARACTER_SPRITE_PATHS).map(([id, path]) => [`char_${id}`, path])
  );
  Assets.addBundle(CHARACTERS_BUNDLE, prefixedPaths);
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
  if (buildingLoadingPromise) {
    return buildingLoadingPromise;
  }

  // Return immediately if already loaded
  if (buildingAssetsLoaded) {
    onProgress?.(1);
    return;
  }

  buildingLoadingPromise = (async () => {
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
      buildingLoadingPromise = null;
    }
  })();

  return buildingLoadingPromise;
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
  buildingLoadingPromise = null;
}

// ============================================
// CHARACTER ASSET LOADING
// ============================================

/**
 * Load all character sprite assets.
 * @param onProgress - Optional callback for loading progress (0-1)
 * @returns Promise that resolves when all assets are loaded
 */
export async function loadCharacterAssets(
  onProgress?: (progress: number) => void
): Promise<void> {
  // Return existing promise if already loading
  if (characterLoadingPromise) {
    return characterLoadingPromise;
  }

  // Return immediately if already loaded
  if (characterAssetsLoaded) {
    onProgress?.(1);
    return;
  }

  characterLoadingPromise = (async () => {
    try {
      // Register assets first
      registerCharacterAssets();

      // Load the bundle with progress callback
      await Assets.loadBundle(CHARACTERS_BUNDLE, (progress) => {
        onProgress?.(progress);
      });

      characterAssetsLoaded = true;
    } catch (error) {
      console.error("Failed to load character assets:", error);
      // Don't throw - allow fallback to procedural rendering
      characterAssetsLoaded = false;
    } finally {
      characterLoadingPromise = null;
    }
  })();

  return characterLoadingPromise;
}

/**
 * Check if character assets have been loaded successfully.
 */
export function areCharacterAssetsLoaded(): boolean {
  return characterAssetsLoaded;
}

/**
 * Get the texture for a character by its ID.
 * @param characterId - The character ID (e.g., "sarah", "craig")
 * @returns The texture if loaded, undefined otherwise
 */
export function getCharacterTexture(characterId: string): Texture | undefined {
  if (!characterAssetsLoaded) {
    return undefined;
  }

  try {
    const texture = Assets.get<Texture>(`char_${characterId}`);
    return texture;
  } catch {
    return undefined;
  }
}

/**
 * Reset the character asset loader state.
 * Useful for testing or when re-initializing the application.
 */
export function resetCharacterAssets(): void {
  characterAssetsLoaded = false;
  characterLoadingPromise = null;
}

// ============================================
// CHARACTER SPRITE SHEET LOADING
// ============================================

/**
 * Generate asset alias for a rotation sprite.
 */
function rotationAlias(characterId: string, direction: FacingDirection): string {
  return `char_${characterId}_rot_${direction}`;
}

/**
 * Generate asset alias for a walking frame.
 */
function walkingFrameAlias(characterId: string, direction: FacingDirection, frameIndex: number): string {
  return `char_${characterId}_walk_${direction}_${frameIndex}`;
}

/**
 * Register all character sprite sheet assets with the PixiJS Assets system.
 * Uses legacy 4-dir sprites as the primary source since isometric walking animations are incomplete.
 */
function registerCharacterSheetAssets(): void {
  const assets: Record<string, string> = {};

  for (const def of CHARACTER_DEFINITIONS) {
    const characterId = def.id;
    // Use legacy folder for walking animations (more complete)
    const legacyFolder = def.spriteSheet.folderName;
    const isoFolder = def.spriteSheet.isoFolderName;

    // Register rotation sprites from isometric folder (all 8 directions exist)
    if (ISOMETRIC_MODE && isoFolder) {
      for (const direction of DIRECTIONS_8) {
        const path = `${SPRITE_SHEET_BASE}/${isoFolder}/rotations/${direction}.png`;
        const alias = rotationAlias(characterId, direction);
        assets[alias] = path;
      }
    } else {
      // Legacy mode - only 4 directions
      for (const direction of DIRECTIONS_4) {
        const path = `${SPRITE_SHEET_BASE}/${legacyFolder}/rotations/${direction}.png`;
        const alias = rotationAlias(characterId, direction);
        assets[alias] = path;
      }
    }

    // Register walking animations from LEGACY folder (4 directions, more reliable)
    // Handle missing walking directions for some characters
    const fallbacks = MISSING_WALKING_FALLBACKS[characterId];

    for (const direction of DIRECTIONS_4) {
      const actualDirection = fallbacks?.[direction] ?? direction;
      const basePath = `${SPRITE_SHEET_BASE}/${legacyFolder}/animations/walking-4-frames/${actualDirection}`;

      for (let i = 0; i < WALKING_FRAME_COUNT; i++) {
        const alias = walkingFrameAlias(characterId, direction, i);
        assets[alias] = `${basePath}/frame_00${i}.png`;
      }
    }

    // For 8-direction mode, map diagonal directions to nearest cardinal for walking
    if (ISOMETRIC_MODE) {
      for (const direction of DIRECTIONS_8) {
        // Skip cardinal directions (already registered)
        if ((DIRECTIONS_4 as readonly string[]).includes(direction)) continue;

        // Map diagonal to nearest cardinal direction for walking animations
        const fallbackDir = DIRECTION_8_TO_4[direction as FacingDirection8];
        const actualFallback = fallbacks?.[fallbackDir] ?? fallbackDir;
        const basePath = `${SPRITE_SHEET_BASE}/${legacyFolder}/animations/walking-4-frames/${actualFallback}`;

        for (let i = 0; i < WALKING_FRAME_COUNT; i++) {
          const alias = walkingFrameAlias(characterId, direction, i);
          assets[alias] = `${basePath}/frame_00${i}.png`;
        }
      }
    }
  }

  console.log(`Registering ${Object.keys(assets).length} character sprite sheet assets`);
  Assets.addBundle(CHARACTER_SHEETS_BUNDLE, assets);
}

/**
 * Load all character sprite sheet assets.
 * @param onProgress - Optional callback for loading progress (0-1)
 * @returns Promise that resolves when all assets are loaded
 */
export async function loadCharacterSheetAssets(
  onProgress?: (progress: number) => void
): Promise<void> {
  // Return existing promise if already loading
  if (characterSheetsLoadingPromise) {
    return characterSheetsLoadingPromise;
  }

  // Return immediately if already loaded
  if (characterSheetsLoaded) {
    onProgress?.(1);
    return;
  }

  characterSheetsLoadingPromise = (async () => {
    try {
      // Register assets first
      registerCharacterSheetAssets();

      // Load the bundle with progress callback
      console.log("Loading character sprite sheet bundle...");
      await Assets.loadBundle(CHARACTER_SHEETS_BUNDLE, (progress) => {
        onProgress?.(progress);
      });

      characterSheetsLoaded = true;
      console.log("Character sprite sheets loaded successfully!");
    } catch (error) {
      console.error("Failed to load character sprite sheet assets:", error);
      // Don't throw - allow fallback to legacy sprites
      characterSheetsLoaded = false;
    } finally {
      characterSheetsLoadingPromise = null;
    }
  })();

  return characterSheetsLoadingPromise;
}

/**
 * Check if character sprite sheets have been loaded successfully.
 */
export function areCharacterSheetsLoaded(): boolean {
  return characterSheetsLoaded;
}

/**
 * Get the rotation (idle) texture for a character in a given direction.
 * @param characterId - The character ID (e.g., "sarah", "craig")
 * @param direction - The facing direction
 * @returns The texture if loaded, undefined otherwise
 */
export function getCharacterRotationTexture(
  characterId: string,
  direction: FacingDirection
): Texture | undefined {
  if (!characterSheetsLoaded) {
    return undefined;
  }

  try {
    const alias = rotationAlias(characterId, direction);
    return Assets.get<Texture>(alias);
  } catch {
    return undefined;
  }
}

/**
 * Get all walking frame textures for a character in a given direction.
 * @param characterId - The character ID (e.g., "sarah", "craig")
 * @param direction - The facing direction
 * @returns Array of 4 textures if loaded, undefined otherwise
 */
export function getCharacterWalkingFrames(
  characterId: string,
  direction: FacingDirection
): Texture[] | undefined {
  if (!characterSheetsLoaded) {
    return undefined;
  }

  try {
    const frames: Texture[] = [];
    for (let i = 0; i < WALKING_FRAME_COUNT; i++) {
      const alias = walkingFrameAlias(characterId, direction, i);
      const texture = Assets.get<Texture>(alias);
      if (!texture) return undefined;
      frames.push(texture);
    }
    return frames;
  } catch {
    return undefined;
  }
}

/**
 * Reset the character sprite sheet loader state.
 */
export function resetCharacterSheetAssets(): void {
  characterSheetsLoaded = false;
  characterSheetsLoadingPromise = null;
}
