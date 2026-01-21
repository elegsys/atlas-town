"use client";

import { useEffect, useRef, useCallback } from "react";
import * as PIXI from "pixi.js";
import {
  BUILDINGS,
  ROADS,
  CANVAS_WIDTH,
  CANVAS_HEIGHT,
  BuildingConfig,
  getBuildingByName,
  getBuildingEntrance,
  PHASE_COLORS,
} from "@/lib/pixi/townConfig";
import { useSimulationStore } from "@/lib/state/simulationStore";

interface CharacterSprite {
  container: PIXI.Container;
  body: PIXI.Graphics;
  label: PIXI.Text;
  bubble: PIXI.Container | null;
}

export function TownCanvas() {
  const canvasRef = useRef<HTMLDivElement>(null);
  const appRef = useRef<PIXI.Application | null>(null);
  const charactersRef = useRef<Map<string, CharacterSprite>>(new Map());
  const buildingsRef = useRef<Map<string, PIXI.Container>>(new Map());

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

      // Draw the town
      drawTown(app);

      // Create Sarah character
      createCharacter(app, "sarah", "Sarah Chen", 0x9370db);
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

  // Draw a single building
  const drawBuilding = (app: PIXI.Application, config: BuildingConfig): PIXI.Container => {
    const container = new PIXI.Container();
    container.position.set(config.x, config.y);

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

    // Label
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

  // Create a character sprite
  const createCharacter = (
    app: PIXI.Application,
    id: string,
    name: string,
    color: number
  ): CharacterSprite => {
    const container = new PIXI.Container();

    // Character body (simple circle + rectangle)
    const body = new PIXI.Graphics();
    // Head
    body.circle(0, -20, 15);
    body.fill(0xffdab9); // Peach
    // Body
    body.roundRect(-12, -5, 24, 35, 6);
    body.fill(color);
    // Shadow
    body.ellipse(0, 32, 15, 5);
    body.fill({ color: 0x000000, alpha: 0.2 });

    container.addChild(body);

    // Name label
    const label = new PIXI.Text({
      text: name,
      style: {
        fontFamily: "Arial",
        fontSize: 11,
        fill: 0xffffff,
        fontWeight: "bold",
        dropShadow: {
          color: 0x000000,
          blur: 2,
          distance: 1,
        },
      },
    });
    label.anchor.set(0.5, 0);
    label.position.set(0, 35);
    container.addChild(label);

    // Initial position at office
    const office = BUILDINGS.find((b) => b.id === "office");
    if (office) {
      const entrance = getBuildingEntrance(office);
      container.position.set(entrance.x, entrance.y + 20);
    }

    app.stage.addChild(container);

    const sprite: CharacterSprite = {
      container,
      body,
      label,
      bubble: null,
    };

    charactersRef.current.set(id, sprite);
    return sprite;
  };

  // Show thought/speech bubble
  const showBubble = (characterId: string, message: string) => {
    const sprite = charactersRef.current.get(characterId);
    if (!sprite || !appRef.current) return;

    // Remove existing bubble
    if (sprite.bubble) {
      sprite.container.removeChild(sprite.bubble);
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

    sprite.container.addChild(bubble);
    sprite.bubble = bubble;
  };

  // Hide bubble
  const hideBubble = (characterId: string) => {
    const sprite = charactersRef.current.get(characterId);
    if (sprite?.bubble) {
      sprite.container.removeChild(sprite.bubble);
      sprite.bubble = null;
    }
  };

  // Move character to building
  const moveCharacterTo = (characterId: string, buildingName: string) => {
    const sprite = charactersRef.current.get(characterId);
    const building = getBuildingByName(buildingName);

    if (!sprite || !building || !appRef.current) return;

    const entrance = getBuildingEntrance(building);
    const targetY = entrance.y + 20;

    // Simple animation using ticker
    const startX = sprite.container.x;
    const startY = sprite.container.y;
    const distance = Math.sqrt(
      Math.pow(entrance.x - startX, 2) + Math.pow(targetY - startY, 2)
    );
    const duration = Math.min(2000, distance * 3); // ms based on distance
    const startTime = performance.now();

    const animate = () => {
      const elapsed = performance.now() - startTime;
      const progress = Math.min(1, elapsed / duration);

      // Ease out
      const eased = 1 - Math.pow(1 - progress, 3);

      sprite.container.x = startX + (entrance.x - startX) * eased;
      sprite.container.y = startY + (targetY - startY) * eased;

      if (progress < 1) {
        requestAnimationFrame(animate);
      }
    };

    requestAnimationFrame(animate);
  };

  // Update phase background color
  useEffect(() => {
    if (!appRef.current) return;

    const phaseColor = PHASE_COLORS[currentPhase] || 0x87ceeb;
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

  // Update character positions and bubbles based on agent state
  useEffect(() => {
    agents.forEach((agent, id) => {
      const sprite = charactersRef.current.get(id);
      if (!sprite) return;

      // Handle movement
      if (agent.status === "moving" && agent.targetLocation) {
        moveCharacterTo(id, agent.targetLocation);
      }

      // Handle messages
      if (agent.currentMessage) {
        showBubble(id, agent.currentMessage);
      } else {
        hideBubble(id);
      }
    });
  }, [agents]);

  return (
    <div
      ref={canvasRef}
      className="rounded-lg overflow-hidden shadow-2xl border border-slate-700"
      style={{ width: CANVAS_WIDTH, height: CANVAS_HEIGHT }}
    />
  );
}

// Helper function to darken a color
function darkenColor(color: number, factor: number): number {
  const r = ((color >> 16) & 0xff) * (1 - factor);
  const g = ((color >> 8) & 0xff) * (1 - factor);
  const b = (color & 0xff) * (1 - factor);
  return (Math.floor(r) << 16) | (Math.floor(g) << 8) | Math.floor(b);
}
