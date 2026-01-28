"use client";

import { useEffect, useRef, useCallback, useState } from "react";
import * as PIXI from "pixi.js";
import {
  BUILDINGS,
  ROADS,
  CANVAS_WIDTH,
  CANVAS_HEIGHT,
  BuildingConfig,
  getBuildingByName,
  getBuildingEntrance,
} from "@/lib/pixi/townConfig";
import {
  loadBuildingAssets,
  loadCharacterAssets,
  loadCharacterSheetAssets,
  getBuildingTexture,
  areBuildingAssetsLoaded,
  createScaledBuildingSprite,
} from "@/lib/pixi/spriteLoader";
import { AnimatedCharacter } from "@/lib/pixi/AnimatedCharacter";
import { CHARACTER_DEFINITIONS } from "@/lib/pixi/characterConfig";
import { useSimulationStore } from "@/lib/state/simulationStore";

interface CharacterWithBubble {
  character: AnimatedCharacter;
  bubble: PIXI.Container | null;
}

export function TownCanvas() {
  const canvasRef = useRef<HTMLDivElement>(null);
  const appRef = useRef<PIXI.Application | null>(null);
  const charactersRef = useRef<Map<string, CharacterWithBubble>>(new Map());
  const buildingsRef = useRef<Map<string, PIXI.Container>>(new Map());

  // Loading state for sprite assets
  const [isLoading, setIsLoading] = useState(true);
  const [loadingProgress, setLoadingProgress] = useState(0);

  // Get state from store
  const agents = useSimulationStore((state) => state.agents);
  const currentPhase = useSimulationStore((state) => state.currentPhase);

  // Initialize PixiJS
  useEffect(() => {
    if (!canvasRef.current || appRef.current) return;

    const initPixi = async () => {
      const app = new PIXI.Application();
      await app.init({
        width: CANVAS_WIDTH,
        height: CANVAS_HEIGHT,
        backgroundColor: 0x87ceeb, // Sky blue
        antialias: true,
        resolution: window.devicePixelRatio || 1,
        autoDensity: true,
      });

      canvasRef.current?.appendChild(app.canvas);
      appRef.current = app;

      // Load all sprite assets
      try {
        // Load buildings (30% of progress)
        await loadBuildingAssets((progress) => {
          setLoadingProgress(progress * 0.3);
        });

        // Load character sprite sheets - 4-directional animations (50% of progress)
        await loadCharacterSheetAssets((progress) => {
          setLoadingProgress(0.3 + progress * 0.5);
        });

        // Load legacy character portraits as fallback (20% of progress)
        await loadCharacterAssets((progress) => {
          setLoadingProgress(0.8 + progress * 0.2);
        });
      } catch (error) {
        console.error("Failed to load assets, using fallback:", error);
      }

      // Draw the town (uses sprites if loaded, fallback otherwise)
      drawTown(app);

      // Create all 6 characters at their starting positions
      createAllCharacters(app);

      // Done loading
      setIsLoading(false);
    };

    initPixi();

    return () => {
      appRef.current?.destroy(true);
      appRef.current = null;
    };
  }, []);

  // Draw the town layout
  const drawTown = useCallback((app: PIXI.Application) => {
    // Ground (grass)
    const grass = new PIXI.Graphics();
    grass.rect(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT);
    grass.fill(0x90ee90);
    app.stage.addChild(grass);

    // Main street
    const road = new PIXI.Graphics();
    road.rect(0, ROADS.mainStreet.y, CANVAS_WIDTH, ROADS.mainStreet.height);
    road.fill(0x696969);
    app.stage.addChild(road);

    // Road markings
    const markings = new PIXI.Graphics();
    markings.rect(0, ROADS.mainStreet.y + ROADS.mainStreet.height / 2 - 2, CANVAS_WIDTH, 4);
    markings.fill(0xffff00);
    app.stage.addChild(markings);

    // Cross street to Sarah's office
    const crossRoad = new PIXI.Graphics();
    crossRoad.rect(
      ROADS.crossStreet.x - ROADS.crossStreet.width / 2,
      ROADS.mainStreet.y + ROADS.mainStreet.height,
      ROADS.crossStreet.width,
      200
    );
    crossRoad.fill(0x696969);
    app.stage.addChild(crossRoad);

    // Draw buildings
    BUILDINGS.forEach((building) => {
      const container = drawBuilding(app, building);
      buildingsRef.current.set(building.id, container);
    });
  }, []);

  // Draw a single building (sprite or procedural fallback)
  const drawBuilding = (app: PIXI.Application, config: BuildingConfig): PIXI.Container => {
    const container = new PIXI.Container();
    container.position.set(config.x, config.y);

    // Try to use sprite if available
    const texture = getBuildingTexture(config.id);
    if (texture && areBuildingAssetsLoaded()) {
      // Render as sprite
      const sprite = createScaledBuildingSprite(texture, config.width, config.height);
      container.addChild(sprite);
    } else {
      // Fallback to procedural rendering
      drawProceduralBuilding(container, config);
    }

    // Label (always add below building)
    const label = new PIXI.Text({
      text: config.label,
      style: {
        fontFamily: "Arial",
        fontSize: 12,
        fill: 0xffffff,
        align: "center",
        fontWeight: "bold",
        dropShadow: {
          color: 0x000000,
          blur: 2,
          distance: 1,
        },
      },
    });
    label.anchor.set(0.5, 0);
    label.position.set(config.width / 2, config.height + 5);
    container.addChild(label);

    app.stage.addChild(container);
    return container;
  };

  // Procedural building rendering (fallback)
  const drawProceduralBuilding = (container: PIXI.Container, config: BuildingConfig): void => {
    // Building body
    const body = new PIXI.Graphics();
    body.roundRect(0, 0, config.width, config.height, 8);
    body.fill(config.color);
    body.stroke({ width: 2, color: 0x333333 });
    container.addChild(body);

    // Roof (simple triangle)
    const roof = new PIXI.Graphics();
    roof.moveTo(config.width / 2, -20);
    roof.lineTo(-10, 0);
    roof.lineTo(config.width + 10, 0);
    roof.closePath();
    roof.fill(darkenColor(config.color, 0.3));
    container.addChild(roof);

    // Door
    const door = new PIXI.Graphics();
    door.roundRect(config.width / 2 - 15, config.height - 40, 30, 40, 4);
    door.fill(0x8b4513);
    container.addChild(door);

    // Windows
    const windowWidth = 25;
    const windowHeight = 30;
    const windowY = 30;

    for (let i = 0; i < 2; i++) {
      const win = new PIXI.Graphics();
      const winX = i === 0 ? 20 : config.width - 45;
      win.roundRect(winX, windowY, windowWidth, windowHeight, 2);
      win.fill(0xadd8e6);
      win.stroke({ width: 1, color: 0x333333 });
      container.addChild(win);
    }
  };

  // Create all characters using AnimatedCharacter class
  const createAllCharacters = (app: PIXI.Application): void => {
    for (const definition of CHARACTER_DEFINITIONS) {
      // Create animated character
      const character = new AnimatedCharacter(definition, app.ticker);

      // Position at starting building
      const building = BUILDINGS.find((b) => b.id === definition.startingBuilding);
      if (building) {
        const entrance = getBuildingEntrance(building);
        character.teleportTo(entrance.x, entrance.y + 20);
      }

      // Add to stage
      app.stage.addChild(character.container);

      // Store reference with bubble tracking
      const charWithBubble: CharacterWithBubble = {
        character,
        bubble: null,
      };

      charactersRef.current.set(definition.id, charWithBubble);
    }
  };

  // Show thought/speech bubble
  const showBubble = (characterId: string, message: string) => {
    const charData = charactersRef.current.get(characterId);
    if (!charData || !appRef.current) return;

    // Remove existing bubble
    if (charData.bubble) {
      charData.character.container.removeChild(charData.bubble);
    }

    const bubble = new PIXI.Container();

    // Truncate message
    const displayMessage = message.length > 60 ? message.substring(0, 57) + "..." : message;

    // Bubble text
    const text = new PIXI.Text({
      text: displayMessage,
      style: {
        fontFamily: "Arial",
        fontSize: 10,
        fill: 0x333333,
        wordWrap: true,
        wordWrapWidth: 150,
      },
    });
    text.anchor.set(0.5, 0.5);

    // Bubble background
    const padding = 8;
    const bg = new PIXI.Graphics();
    bg.roundRect(
      -text.width / 2 - padding,
      -text.height / 2 - padding,
      text.width + padding * 2,
      text.height + padding * 2,
      8
    );
    bg.fill(0xffffff);
    bg.stroke({ width: 1, color: 0x333333 });

    // Pointer
    bg.moveTo(-5, text.height / 2 + padding);
    bg.lineTo(0, text.height / 2 + padding + 10);
    bg.lineTo(5, text.height / 2 + padding);
    bg.fill(0xffffff);

    bubble.addChild(bg);
    bubble.addChild(text);
    bubble.position.set(0, -60);

    charData.character.container.addChild(bubble);
    charData.bubble = bubble;
  };

  // Hide bubble
  const hideBubble = (characterId: string) => {
    const charData = charactersRef.current.get(characterId);
    if (charData?.bubble) {
      charData.character.container.removeChild(charData.bubble);
      charData.bubble = null;
    }
  };

  // Move character to building using AnimatedCharacter's moveTo
  const moveCharacterTo = (characterId: string, buildingName: string) => {
    const charData = charactersRef.current.get(characterId);
    const building = getBuildingByName(buildingName);

    if (!charData || !building || !appRef.current) return;

    const entrance = getBuildingEntrance(building);
    const targetY = entrance.y + 20;

    // Use AnimatedCharacter's built-in movement animation
    charData.character.moveTo(entrance.x, targetY);
  };

  // Update phase background color
  useEffect(() => {
    if (!appRef.current) return;

    // Update sky color based on phase
    const stage = appRef.current.stage;
    const grass = stage.children[0] as PIXI.Graphics;
    if (grass) {
      // Adjust grass color based on time of day
      const isNight = currentPhase === "night" || currentPhase === "evening";
      grass.clear();
      grass.rect(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT);
      grass.fill(isNight ? 0x2d5a27 : 0x90ee90);
    }
  }, [currentPhase]);

  // Update character positions, animations, and bubbles based on agent state
  useEffect(() => {
    agents.forEach((agent, id) => {
      const charData = charactersRef.current.get(id);
      if (!charData) return;

      // Map agent status to animation state
      if (agent.status === "moving" && agent.targetLocation) {
        moveCharacterTo(id, agent.targetLocation);
        // Animation state is set by moveTo automatically
      } else if (agent.status === "thinking") {
        charData.character.state = "thinking";
      } else if (agent.status === "speaking") {
        charData.character.state = "speaking";
      } else {
        charData.character.state = "idle";
      }

      // Handle messages (speech/thought bubbles)
      if (agent.currentMessage) {
        showBubble(id, agent.currentMessage);
      } else {
        hideBubble(id);
      }
    });
  }, [agents]);

  return (
    <div className="relative">
      <div
        ref={canvasRef}
        className="rounded-lg overflow-hidden shadow-2xl border border-slate-700"
        style={{ width: CANVAS_WIDTH, height: CANVAS_HEIGHT }}
      />
      {/* Loading overlay */}
      {isLoading && (
        <div
          className="absolute inset-0 flex flex-col items-center justify-center bg-slate-900/80 rounded-lg"
          style={{ width: CANVAS_WIDTH, height: CANVAS_HEIGHT }}
        >
          <div className="text-white text-lg mb-4">Loading Atlas Town...</div>
          <div className="w-64 h-2 bg-slate-700 rounded-full overflow-hidden">
            <div
              className="h-full bg-blue-500 transition-all duration-200"
              style={{ width: `${loadingProgress * 100}%` }}
            />
          </div>
          <div className="text-slate-400 text-sm mt-2">
            {Math.round(loadingProgress * 100)}%
          </div>
        </div>
      )}
    </div>
  );
}

// Helper function to darken a color
function darkenColor(color: number, factor: number): number {
  const r = ((color >> 16) & 0xff) * (1 - factor);
  const g = ((color >> 8) & 0xff) * (1 - factor);
  const b = (color & 0xff) * (1 - factor);
  return (Math.floor(r) << 16) | (Math.floor(g) << 8) | Math.floor(b);
}
