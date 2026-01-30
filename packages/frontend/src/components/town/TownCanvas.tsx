"use client";

/**
 * TownCanvas - Main orchestrator for the Atlas Town isometric view.
 *
 * This component has been refactored to use the new modular architecture:
 * - IsometricCamera: Handles all coordinate transforms and offsets
 * - IsometricTileMap: Renders static terrain
 * - EntityManager: Manages buildings and characters with depth sorting
 * - Building/Character: Entity classes for game objects
 *
 * The previous 500+ line monolith is now a ~200 line orchestrator.
 */

import { useEffect, useRef, useCallback, useState } from "react";
import * as PIXI from "pixi.js";

// New modular architecture imports
import {
  IsometricCamera,
  IsometricTileMap,
  EntityManager,
  TileType,
  CANVAS_WIDTH,
  CANVAS_HEIGHT,
} from "@/lib/pixi/isometric/index";
import { Building, BuildingConfig, Character, CharacterConfig, setCharacterTextureLoader } from "@/lib/pixi/entities/index";

// Existing config and loaders
import { BUILDINGS, getBuildingByName } from "@/lib/pixi/townConfig";
import { CHARACTER_DEFINITIONS } from "@/lib/pixi/characterConfig";
import {
  loadBuildingAssets,
  loadCharacterAssets,
  loadCharacterSheetAssets,
  getBuildingTexture,
  areBuildingAssetsLoaded,
  areCharacterSheetsLoaded,
  getCharacterRotationTexture,
  getCharacterWalkingFrames,
} from "@/lib/pixi/spriteLoader";
import { loadTileAssets, getTileTexture } from "@/lib/pixi/TileMap";
import { useSimulationStore } from "@/lib/state/simulationStore";

// ============================================
// TYPES
// ============================================

interface CharacterWithBubble {
  character: Character;
  bubble: PIXI.Container | null;
}

// ============================================
// COMPONENT
// ============================================

export function TownCanvas() {
  const canvasRef = useRef<HTMLDivElement>(null);
  const appRef = useRef<PIXI.Application | null>(null);

  // Core architecture instances
  const cameraRef = useRef<IsometricCamera | null>(null);
  const tileMapRef = useRef<IsometricTileMap | null>(null);
  const entityManagerRef = useRef<EntityManager | null>(null);

  // Entity tracking
  const charactersRef = useRef<Map<string, CharacterWithBubble>>(new Map());
  const buildingsRef = useRef<Map<string, Building>>(new Map());

  // Loading state
  const [isLoading, setIsLoading] = useState(true);
  const [loadingProgress, setLoadingProgress] = useState(0);

  // Store state
  const agents = useSimulationStore((state) => state.agents);

  // ============================================
  // INITIALIZATION
  // ============================================

  useEffect(() => {
    if (!canvasRef.current || appRef.current) return;

    const initPixi = async () => {
      // Create PixiJS application
      const app = new PIXI.Application();
      await app.init({
        width: CANVAS_WIDTH,
        height: CANVAS_HEIGHT,
        backgroundColor: 0x87ceeb,
        antialias: true,
        resolution: window.devicePixelRatio || 1,
        autoDensity: true,
      });

      canvasRef.current?.appendChild(app.canvas);
      appRef.current = app;

      // Create core architecture
      const camera = new IsometricCamera();
      cameraRef.current = camera;

      const tileMap = new IsometricTileMap(camera);
      tileMapRef.current = tileMap;

      const entityManager = new EntityManager(camera);
      entityManagerRef.current = entityManager;

      // Load all assets
      await loadAssets();

      // Build the scene
      buildScene(app, camera, tileMap, entityManager);

      // Done loading
      setIsLoading(false);
    };

    initPixi();

    return () => {
      entityManagerRef.current?.destroy();
      appRef.current?.destroy(true);
      appRef.current = null;
    };
  }, []);

  // ============================================
  // ASSET LOADING
  // ============================================

  const loadAssets = async () => {
    try {
      // Load tile assets (15% of progress)
      await loadTileAssets((progress) => {
        setLoadingProgress(progress * 0.15);
      });

      // Load buildings (25% of progress)
      await loadBuildingAssets((progress) => {
        setLoadingProgress(0.15 + progress * 0.25);
      });

      // Load character sprite sheets (45% of progress)
      await loadCharacterSheetAssets((progress) => {
        setLoadingProgress(0.4 + progress * 0.45);
      });

      // Load legacy character portraits as fallback (15% of progress)
      await loadCharacterAssets((progress) => {
        setLoadingProgress(0.85 + progress * 0.15);
      });

      // Set up character texture loader for the Character entity class
      setCharacterTextureLoader({
        getRotationTexture: getCharacterRotationTexture,
        getWalkingFrames: getCharacterWalkingFrames,
        areAssetsLoaded: () => areBuildingAssetsLoaded(),
        areSheetsLoaded: areCharacterSheetsLoaded,
      });

    } catch (error) {
      console.error("Failed to load assets, using fallback:", error);
    }
  };

  // ============================================
  // SCENE BUILDING
  // ============================================

  const buildScene = useCallback((
    app: PIXI.Application,
    camera: IsometricCamera,
    tileMap: IsometricTileMap,
    entityManager: EntityManager
  ) => {
    // Inject tile textures into tileMap
    const tileTypes: TileType[] = ["grass", "road", "sidewalk", "road_marking"];
    for (const type of tileTypes) {
      const texture = getTileTexture(type);
      if (texture) {
        tileMap.setTileTexture(type, texture);
      }
    }
    tileMap.setAssetsLoaded(true);

    // Build terrain (static layer)
    tileMap.build();
    app.stage.addChild(tileMap.container);

    // Add entity container (sortable layer)
    app.stage.addChild(entityManager.container);

    // Create buildings
    for (const config of BUILDINGS) {
      if (config.gridX === undefined || config.gridY === undefined) continue;

      const buildingConfig: BuildingConfig = {
        id: config.id,
        name: config.name,
        gridX: config.gridX,
        gridY: config.gridY,
        type: config.type,
        industry: config.industry,
        width: config.width,
        height: config.height,
        color: config.color,
        label: config.label,
        spritePath: config.spritePath,
      };

      const building = new Building(camera, buildingConfig);

      // Set texture if available
      const texture = getBuildingTexture(config.id);
      if (texture && areBuildingAssetsLoaded()) {
        building.setTexture(texture);
      }

      building.build();
      entityManager.add(building);
      buildingsRef.current.set(config.id, building);
    }

    // Create characters
    for (const definition of CHARACTER_DEFINITIONS) {
      const building = BUILDINGS.find((b) => b.id === definition.startingBuilding);
      if (!building || building.gridX === undefined || building.gridY === undefined) continue;

      const charConfig: CharacterConfig = {
        id: definition.id,
        name: definition.name,
        gridX: building.gridX,
        gridY: building.gridY + 2, // Position in front of building
        themeColor: definition.themeColor,
        spritePath: definition.spritePath,
      };

      const character = new Character(camera, charConfig, app.ticker);
      character.build();
      entityManager.add(character);

      charactersRef.current.set(definition.id, {
        character,
        bubble: null,
      });
    }
  }, []);

  // ============================================
  // BUBBLE MANAGEMENT
  // ============================================

  const showBubble = useCallback((characterId: string, message: string) => {
    const charData = charactersRef.current.get(characterId);
    if (!charData) return;

    // Remove existing bubble
    if (charData.bubble) {
      charData.character.container.removeChild(charData.bubble);
    }

    const bubble = new PIXI.Container();
    const displayMessage = message.length > 60 ? message.substring(0, 57) + "..." : message;

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
  }, []);

  const hideBubble = useCallback((characterId: string) => {
    const charData = charactersRef.current.get(characterId);
    if (charData?.bubble) {
      charData.character.container.removeChild(charData.bubble);
      charData.bubble = null;
    }
  }, []);

  // ============================================
  // CHARACTER MOVEMENT
  // ============================================

  const moveCharacterTo = useCallback((characterId: string, buildingName: string) => {
    const charData = charactersRef.current.get(characterId);
    const building = getBuildingByName(buildingName);
    const camera = cameraRef.current;

    if (!charData || !building || !camera) return;

    if (building.gridX !== undefined && building.gridY !== undefined) {
      // Move to grid position in front of building
      charData.character.moveToGrid(building.gridX, building.gridY + 2);
    }
  }, []);

  // ============================================
  // AGENT STATE SYNC
  // ============================================

  useEffect(() => {
    agents.forEach((agent, id) => {
      const charData = charactersRef.current.get(id);
      if (!charData) return;

      // Map agent status to animation state
      if (agent.status === "moving" && agent.targetLocation) {
        moveCharacterTo(id, agent.targetLocation);
      } else if (agent.status === "thinking") {
        charData.character.state = "thinking";
      } else if (agent.status === "speaking") {
        charData.character.state = "speaking";
      } else {
        charData.character.state = "idle";
      }

      // Handle messages
      if (agent.currentMessage) {
        showBubble(id, agent.currentMessage);
      } else {
        hideBubble(id);
      }
    });
  }, [agents, moveCharacterTo, showBubble, hideBubble]);

  // ============================================
  // RENDER
  // ============================================

  return (
    <div className="relative">
      <div
        ref={canvasRef}
        className="rounded-lg overflow-hidden shadow-2xl border border-slate-700"
        style={{ width: CANVAS_WIDTH, height: CANVAS_HEIGHT }}
      />
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
