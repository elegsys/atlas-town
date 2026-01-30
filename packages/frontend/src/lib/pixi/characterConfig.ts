/**
 * Character configuration for all 6 agents in Atlas Town.
 * Defines sprite paths, theme colors, starting locations, and animation settings.
 *
 * Supports both 4-direction (legacy top-down) and 8-direction (isometric) modes.
 */

import { ISOMETRIC_MODE } from "./isometric";

export type CharacterAnimationState = "idle" | "walking" | "thinking" | "speaking";

/** 4-direction facing (legacy top-down view) */
export type FacingDirection4 = "south" | "north" | "east" | "west";

/** 8-direction facing (isometric view) */
export type FacingDirection8 =
  | "south"
  | "south-west"
  | "west"
  | "north-west"
  | "north"
  | "north-east"
  | "east"
  | "south-east";

/** Unified facing direction type - 8 directions in isometric mode, 4 in legacy */
export type FacingDirection = FacingDirection4 | FacingDirection8;

/** Sprite sheet paths for a character with directional animations */
export interface CharacterSpritePaths {
  /** Base folder for this character's sprites (relative to public/) */
  sheetBase: string;
  /** Folder name for the character (e.g., "sarah_chen") */
  folderName: string;
  /** Optional isometric folder override (e.g., "sarah_chen_iso") */
  isoFolderName?: string;
}

export interface CharacterDefinition {
  id: string;
  name: string;
  /** Legacy single portrait path (kept for fallback) */
  spritePath: string;
  /** New sprite sheet paths for 4-directional animations */
  spriteSheet: CharacterSpritePaths;
  themeColor: number;
  startingBuilding: string;
}

export interface AnimationConfig {
  /** Idle bobbing amplitude in pixels */
  idleBobAmplitude: number;
  /** Idle bobbing frequency in Hz */
  idleBobFrequency: number;
  /** Breathing scale variation (e.g., 0.02 = 2%) */
  breathingScale: number;
  /** Walking bob amplitude in pixels */
  walkingBobAmplitude: number;
  /** Walking bob frequency in Hz */
  walkingBobFrequency: number;
}

/** Base path for character sprite sheets */
export const SPRITE_SHEET_BASE = "/sprites/characters/sheets";

/** Number of frames in walking animation */
export const WALKING_FRAME_COUNT = 4;

/** 4 cardinal directions (legacy top-down) */
export const DIRECTIONS_4: FacingDirection4[] = ["south", "north", "east", "west"];

/** 8 directions including diagonals (isometric) */
export const DIRECTIONS_8: FacingDirection8[] = [
  "south",
  "south-west",
  "west",
  "north-west",
  "north",
  "north-east",
  "east",
  "south-east",
];

/** All directions - 8 in isometric mode, 4 in legacy */
export const ALL_DIRECTIONS: FacingDirection[] = ISOMETRIC_MODE ? DIRECTIONS_8 : DIRECTIONS_4;

/**
 * Map 8-direction to nearest 4-direction (fallback for missing assets).
 */
export const DIRECTION_8_TO_4: Record<FacingDirection8, FacingDirection4> = {
  "south": "south",
  "south-west": "west",
  "west": "west",
  "north-west": "north",
  "north": "north",
  "north-east": "east",
  "east": "east",
  "south-east": "south",
};

// All 6 character definitions
export const CHARACTER_DEFINITIONS: CharacterDefinition[] = [
  {
    id: "sarah",
    name: "Sarah Chen",
    spritePath: "/sprites/characters/sarah_chen.png",
    spriteSheet: {
      sheetBase: SPRITE_SHEET_BASE,
      folderName: "sarah_chen",
      isoFolderName: "sarah_chen_iso",
    },
    themeColor: 0x9370db, // Purple
    startingBuilding: "office",
  },
  {
    id: "craig",
    name: "Craig Miller",
    spritePath: "/sprites/characters/craig_miller.png",
    spriteSheet: {
      sheetBase: SPRITE_SHEET_BASE,
      folderName: "craig_miller",
      isoFolderName: "craig_miller_iso",
    },
    themeColor: 0x228b22, // Forest green
    startingBuilding: "craigs_landscaping",
  },
  {
    id: "tony",
    name: "Tony Romano",
    spritePath: "/sprites/characters/tony_romano.png",
    spriteSheet: {
      sheetBase: SPRITE_SHEET_BASE,
      folderName: "tony_romano",
      isoFolderName: "tony_romano_iso",
    },
    themeColor: 0xdc143c, // Crimson
    startingBuilding: "tonys_pizzeria",
  },
  {
    id: "maya",
    name: "Maya Patel",
    spritePath: "/sprites/characters/maya_patel.png",
    spriteSheet: {
      sheetBase: SPRITE_SHEET_BASE,
      folderName: "maya_patel",
      isoFolderName: "maya_patel_iso",
    },
    themeColor: 0x4169e1, // Royal blue
    startingBuilding: "nexus_tech",
  },
  {
    id: "chen",
    name: "Dr. David Chen",
    spritePath: "/sprites/characters/david_chen.png",
    spriteSheet: {
      sheetBase: SPRITE_SHEET_BASE,
      folderName: "david_chen",
      isoFolderName: "david_chen_iso",
    },
    themeColor: 0x87ceeb, // Sky blue
    startingBuilding: "main_street_dental",
  },
  {
    id: "marcus",
    name: "Marcus Thompson",
    spritePath: "/sprites/characters/marcus_thompson.png",
    spriteSheet: {
      sheetBase: SPRITE_SHEET_BASE,
      folderName: "marcus_thompson",
      isoFolderName: "marcus_thompson_iso",
    },
    themeColor: 0xdaa520, // Goldenrod
    startingBuilding: "harbor_realty",
  },
];

// Default animation settings
export const ANIMATION_CONFIG: AnimationConfig = {
  idleBobAmplitude: 2,
  idleBobFrequency: 0.5,
  breathingScale: 0.02,
  walkingBobAmplitude: 4,
  walkingBobFrequency: 3,
};

// Target display size for characters (sprites are 48x48)
export const CHARACTER_DISPLAY_WIDTH = 48;
export const CHARACTER_DISPLAY_HEIGHT = 48;

// Lookup helpers
export function getCharacterDefinition(id: string): CharacterDefinition | undefined {
  return CHARACTER_DEFINITIONS.find((c) => c.id === id);
}

export function getCharacterSpritePath(id: string): string | undefined {
  return getCharacterDefinition(id)?.spritePath;
}

// Map of character ID to sprite asset paths (for sprite loader - legacy)
export const CHARACTER_SPRITE_PATHS: Record<string, string> = Object.fromEntries(
  CHARACTER_DEFINITIONS.map((c) => [c.id, c.spritePath])
);

/**
 * Get the folder name for a character based on current view mode.
 */
function getCharacterFolderName(def: CharacterDefinition): string {
  if (ISOMETRIC_MODE && def.spriteSheet.isoFolderName) {
    return def.spriteSheet.isoFolderName;
  }
  return def.spriteSheet.folderName;
}

/**
 * Get the rotation (idle) sprite path for a character in a given direction.
 * In isometric mode, attempts to use 8-direction sprites, falls back to 4-direction.
 */
export function getRotationSpritePath(characterId: string, direction: FacingDirection): string | undefined {
  const def = getCharacterDefinition(characterId);
  if (!def) return undefined;
  const folderName = getCharacterFolderName(def);
  return `${def.spriteSheet.sheetBase}/${folderName}/rotations/${direction}.png`;
}

/**
 * Get the fallback rotation sprite path using 4-direction mapping.
 */
export function getRotationSpritePathFallback(characterId: string, direction: FacingDirection8): string | undefined {
  const fallbackDir = DIRECTION_8_TO_4[direction];
  const def = getCharacterDefinition(characterId);
  if (!def) return undefined;
  // Use legacy folder for fallback (4-direction)
  return `${def.spriteSheet.sheetBase}/${def.spriteSheet.folderName}/rotations/${fallbackDir}.png`;
}

/**
 * Get walking animation frame paths for a character in a given direction.
 * Returns array of 4 frame paths.
 */
export function getWalkingFramePaths(characterId: string, direction: FacingDirection): string[] | undefined {
  const def = getCharacterDefinition(characterId);
  if (!def) return undefined;
  const folderName = getCharacterFolderName(def);
  const basePath = `${def.spriteSheet.sheetBase}/${folderName}/animations/walking-4-frames/${direction}`;
  return Array.from({ length: WALKING_FRAME_COUNT }, (_, i) => `${basePath}/frame_00${i}.png`);
}

/**
 * Get walking animation frame paths using 4-direction fallback.
 */
export function getWalkingFramePathsFallback(characterId: string, direction: FacingDirection8): string[] | undefined {
  const fallbackDir = DIRECTION_8_TO_4[direction];
  const def = getCharacterDefinition(characterId);
  if (!def) return undefined;
  // Use legacy folder for fallback (4-direction)
  const basePath = `${def.spriteSheet.sheetBase}/${def.spriteSheet.folderName}/animations/walking-4-frames/${fallbackDir}`;
  return Array.from({ length: WALKING_FRAME_COUNT }, (_, i) => `${basePath}/frame_00${i}.png`);
}
