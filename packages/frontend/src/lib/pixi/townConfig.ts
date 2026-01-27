/**
 * Town layout configuration for the PixiJS canvas.
 */

// Building definitions
export interface BuildingConfig {
  id: string;
  name: string;
  type: "business" | "office" | "landmark";
  industry?: string;
  x: number;
  y: number;
  width: number;
  height: number;
  color: number;
  label: string;
  spritePath?: string; // Path to sprite asset (relative to public/)
}

// Character definitions
export interface CharacterConfig {
  id: string;
  name: string;
  type: "accountant" | "owner" | "customer" | "vendor";
  color: number;
  startingBuilding: string;
}

// Canvas dimensions
export const CANVAS_WIDTH = 1200;
export const CANVAS_HEIGHT = 700;

// Town layout - buildings positioned along a main street
export const BUILDINGS: BuildingConfig[] = [
  // Main Street businesses (top row)
  {
    id: "craigs_landscaping",
    name: "Craig's Landscaping",
    type: "business",
    industry: "landscaping",
    x: 50,
    y: 80,
    width: 180,
    height: 140,
    color: 0x228b22, // Forest green
    label: "Craig's\nLandscaping",
    spritePath: "/sprites/buildings/craigs_landscaping.png",
  },
  {
    id: "tonys_pizzeria",
    name: "Tony's Pizzeria",
    type: "business",
    industry: "restaurant",
    x: 280,
    y: 80,
    width: 180,
    height: 140,
    color: 0xdc143c, // Crimson
    label: "Tony's\nPizzeria",
    spritePath: "/sprites/buildings/tonys_pizzeria.png",
  },
  {
    id: "nexus_tech",
    name: "Nexus Tech",
    type: "business",
    industry: "technology",
    x: 510,
    y: 80,
    width: 180,
    height: 140,
    color: 0x4169e1, // Royal blue
    label: "Nexus Tech\nConsulting",
    spritePath: "/sprites/buildings/nexus_tech.png",
  },
  {
    id: "main_street_dental",
    name: "Main Street Dental",
    type: "business",
    industry: "healthcare",
    x: 740,
    y: 80,
    width: 180,
    height: 140,
    color: 0x87ceeb, // Sky blue
    label: "Main Street\nDental",
    spritePath: "/sprites/buildings/main_street_dental.png",
  },
  {
    id: "harbor_realty",
    name: "Harbor Realty",
    type: "business",
    industry: "real_estate",
    x: 970,
    y: 80,
    width: 180,
    height: 140,
    color: 0xdaa520, // Goldenrod
    label: "Harbor\nRealty",
    spritePath: "/sprites/buildings/harbor_realty.png",
  },
  // Sarah's office (bottom center)
  {
    id: "office",
    name: "Accounting Office",
    type: "office",
    x: 500,
    y: 480,
    width: 200,
    height: 120,
    color: 0x708090, // Slate gray
    label: "Sarah's\nAccounting",
    spritePath: "/sprites/buildings/sarahs_office.png",
  },
];

// Road configuration
export const ROADS = {
  mainStreet: {
    y: 280,
    height: 60,
  },
  crossStreet: {
    x: 600,
    width: 40,
  },
};

// Characters
export const CHARACTERS: CharacterConfig[] = [
  {
    id: "sarah",
    name: "Sarah Chen",
    type: "accountant",
    color: 0x9370db, // Medium purple
    startingBuilding: "office",
  },
];

// Building name to ID mapping
export const BUILDING_NAME_TO_ID: Record<string, string> = {
  "Craig's Landscaping": "craigs_landscaping",
  "Tony's Pizzeria": "tonys_pizzeria",
  "Nexus Tech": "nexus_tech",
  "Nexus Tech Consulting": "nexus_tech",
  "Main Street Dental": "main_street_dental",
  "Harbor Realty": "harbor_realty",
  "Accounting Office": "office",
  office: "office",
};

// Get building config by name
export function getBuildingByName(name: string): BuildingConfig | undefined {
  const id = BUILDING_NAME_TO_ID[name];
  if (id) {
    return BUILDINGS.find((b) => b.id === id);
  }
  // Try direct ID match
  return BUILDINGS.find((b) => b.id === name || b.name.toLowerCase().includes(name.toLowerCase()));
}

// Get building entrance position (center bottom)
export function getBuildingEntrance(building: BuildingConfig): { x: number; y: number } {
  return {
    x: building.x + building.width / 2,
    y: building.y + building.height + 10,
  };
}

// Phase colors for UI
export const PHASE_COLORS: Record<string, number> = {
  early_morning: 0xffd700, // Gold
  morning: 0x87ceeb, // Light blue
  lunch: 0xffa500, // Orange
  afternoon: 0x87ceeb, // Light blue
  evening: 0xff6b6b, // Coral
  night: 0x191970, // Midnight blue
};

// Industry icons (emoji for simplicity, could be sprite sheets)
export const INDUSTRY_ICONS: Record<string, string> = {
  landscaping: "🌿",
  restaurant: "🍕",
  technology: "💻",
  healthcare: "🦷",
  real_estate: "🏠",
};
