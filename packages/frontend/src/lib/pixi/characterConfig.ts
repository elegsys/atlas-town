/**
 * Character configuration for all 6 agents in Atlas Town.
 * Defines sprite paths, theme colors, starting locations, and animation settings.
 */

export type CharacterAnimationState = "idle" | "walking" | "thinking" | "speaking";
export type FacingDirection = "south" | "north" | "east" | "west";

/** Sprite sheet paths for a character with 4-directional animations */
export interface CharacterSpritePaths {
  /** Base folder for this character's sprites (relative to public/) */
  sheetBase: string;
  /** Folder name for the character (e.g., "sarah_chen") */
  folderName: string;
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

/** All directions in order (for iteration) */
export const ALL_DIRECTIONS: FacingDirection[] = ["south", "north", "east", "west"];

// All 6 character definitions
export const CHARACTER_DEFINITIONS: CharacterDefinition[] = [
  {
    id: "sarah",
    name: "Sarah Chen",
    spritePath: "/sprites/characters/sarah_chen.png",
    spriteSheet: {
      sheetBase: SPRITE_SHEET_BASE,
      folderName: "sarah_chen",
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
 * Get the rotation (idle) sprite path for a character in a given direction.
 */
export function getRotationSpritePath(characterId: string, direction: FacingDirection): string | undefined {
  const def = getCharacterDefinition(characterId);
  if (!def) return undefined;
  return `${def.spriteSheet.sheetBase}/${def.spriteSheet.folderName}/rotations/${direction}.png`;
}

/**
 * Get walking animation frame paths for a character in a given direction.
 * Returns array of 4 frame paths.
 */
export function getWalkingFramePaths(characterId: string, direction: FacingDirection): string[] | undefined {
  const def = getCharacterDefinition(characterId);
  if (!def) return undefined;
  const basePath = `${def.spriteSheet.sheetBase}/${def.spriteSheet.folderName}/animations/walking-4-frames/${direction}`;
  return Array.from({ length: WALKING_FRAME_COUNT }, (_, i) => `${basePath}/frame_00${i}.png`);
}
