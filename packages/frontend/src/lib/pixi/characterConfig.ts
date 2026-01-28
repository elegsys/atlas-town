/**
 * Character configuration for all 6 agents in Atlas Town.
 * Defines sprite paths, theme colors, starting locations, and animation settings.
 */

export type CharacterAnimationState = "idle" | "walking" | "thinking" | "speaking";
export type FacingDirection = "left" | "right";

export interface CharacterDefinition {
  id: string;
  name: string;
  spritePath: string;
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

// All 6 character definitions
export const CHARACTER_DEFINITIONS: CharacterDefinition[] = [
  {
    id: "sarah",
    name: "Sarah Chen",
    spritePath: "/sprites/characters/sarah_chen.png",
    themeColor: 0x9370db, // Purple
    startingBuilding: "office",
  },
  {
    id: "craig",
    name: "Craig Miller",
    spritePath: "/sprites/characters/craig_miller.png",
    themeColor: 0x228b22, // Forest green
    startingBuilding: "craigs_landscaping",
  },
  {
    id: "tony",
    name: "Tony Romano",
    spritePath: "/sprites/characters/tony_romano.png",
    themeColor: 0xdc143c, // Crimson
    startingBuilding: "tonys_pizzeria",
  },
  {
    id: "maya",
    name: "Maya Patel",
    spritePath: "/sprites/characters/maya_patel.png",
    themeColor: 0x4169e1, // Royal blue
    startingBuilding: "nexus_tech",
  },
  {
    id: "chen",
    name: "Dr. David Chen",
    spritePath: "/sprites/characters/david_chen.png",
    themeColor: 0x87ceeb, // Sky blue
    startingBuilding: "main_street_dental",
  },
  {
    id: "marcus",
    name: "Marcus Thompson",
    spritePath: "/sprites/characters/marcus_thompson.png",
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

// Target display size for characters (scaled from 1024x1024 portraits)
export const CHARACTER_DISPLAY_WIDTH = 48;
export const CHARACTER_DISPLAY_HEIGHT = 64;

// Lookup helpers
export function getCharacterDefinition(id: string): CharacterDefinition | undefined {
  return CHARACTER_DEFINITIONS.find((c) => c.id === id);
}

export function getCharacterSpritePath(id: string): string | undefined {
  return getCharacterDefinition(id)?.spritePath;
}

// Map of character ID to sprite asset paths (for sprite loader)
export const CHARACTER_SPRITE_PATHS: Record<string, string> = Object.fromEntries(
  CHARACTER_DEFINITIONS.map((c) => [c.id, c.spritePath])
);
