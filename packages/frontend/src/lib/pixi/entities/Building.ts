/**
 * Building - Isometric building entity for Atlas Town.
 *
 * Renders building sprites or procedural fallback graphics.
 * Extends IsometricEntity for grid-based positioning.
 */

import { Sprite, Text, Graphics, Texture } from "pixi.js";
import { IsometricEntity, EntityConfig } from "../isometric/IsometricEntity";
import { IsometricCamera } from "../isometric/IsometricCamera";
import {
  ISO_TILE_HEIGHT,
  ISO_BUILDING_SCALE,
  ISOMETRIC_MODE,
} from "../isometric/constants";

export interface BuildingConfig extends EntityConfig {
  /** Building type */
  type: "business" | "office" | "landmark";
  /** Industry (for business buildings) */
  industry?: string;
  /** Legacy pixel dimensions */
  width: number;
  height: number;
  /** Theme color for procedural rendering */
  color: number;
  /** Label text (multi-line) */
  label: string;
  /** Path to sprite asset */
  spritePath?: string;
}

export class Building extends IsometricEntity {
  /** Building configuration */
  private readonly config: BuildingConfig;

  /** Current texture (if loaded) */
  private texture: Texture | null = null;

  /** Sprite for the building */
  private sprite: Sprite | null = null;

  /** Procedural graphics (fallback) */
  private graphics: Graphics | null = null;

  /** Label text */
  private label: Text | null = null;

  /** Scaled dimensions for isometric view */
  private readonly scaledWidth: number;
  private readonly scaledHeight: number;

  constructor(camera: IsometricCamera, config: BuildingConfig) {
    super(camera, config);
    this.config = config;

    // Calculate scaled dimensions
    this.scaledWidth = ISOMETRIC_MODE
      ? config.width * ISO_BUILDING_SCALE
      : config.width;
    this.scaledHeight = ISOMETRIC_MODE
      ? config.height * ISO_BUILDING_SCALE
      : config.height;
  }

  // ============================================
  // TEXTURE MANAGEMENT
  // ============================================

  /**
   * Set the texture for this building.
   * Call this after assets are loaded.
   */
  setTexture(texture: Texture): void {
    this.texture = texture;
  }

  /**
   * Check if a texture has been set.
   */
  hasTexture(): boolean {
    return this.texture !== null;
  }

  // ============================================
  // RENDERING
  // ============================================

  /**
   * Build the visual representation of this building.
   */
  build(): void {
    // Clear any existing children
    this.container.removeChildren();

    if (this.texture) {
      this.renderSprite();
    } else {
      this.renderProcedural();
    }

    this.renderLabel();
    this.adjustPosition();
  }

  /**
   * Render using sprite texture.
   */
  private renderSprite(): void {
    if (!this.texture) return;

    this.sprite = new Sprite(this.texture);

    // Scale to fit target dimensions while maintaining aspect ratio
    const scaleX = this.scaledWidth / this.texture.width;
    const scaleY = this.scaledHeight / this.texture.height;
    const scale = Math.min(scaleX, scaleY);

    this.sprite.scale.set(scale);
    this.sprite.anchor.set(0.5, 1); // Center-bottom anchor

    this.container.addChild(this.sprite);
  }

  /**
   * Render using procedural graphics (fallback).
   */
  private renderProcedural(): void {
    this.graphics = new Graphics();

    const w = this.scaledWidth;
    const h = this.scaledHeight;
    const scaleRatio = w / this.config.width;

    // Building body
    this.graphics.roundRect(-w / 2, -h, w, h, 8 * scaleRatio);
    this.graphics.fill(this.config.color);
    this.graphics.stroke({ width: 2 * scaleRatio, color: 0x333333 });

    // Roof (simple triangle)
    this.graphics.moveTo(0, -h - 20 * scaleRatio);
    this.graphics.lineTo(-w / 2 - 10 * scaleRatio, -h);
    this.graphics.lineTo(w / 2 + 10 * scaleRatio, -h);
    this.graphics.closePath();
    this.graphics.fill(this.darkenColor(this.config.color, 0.3));

    // Door
    this.graphics.roundRect(
      -15 * scaleRatio,
      -40 * scaleRatio,
      30 * scaleRatio,
      40 * scaleRatio,
      4 * scaleRatio
    );
    this.graphics.fill(0x8b4513);

    // Windows
    const windowWidth = 25 * scaleRatio;
    const windowHeight = 30 * scaleRatio;
    const windowY = -h + 30 * scaleRatio;

    for (let i = 0; i < 2; i++) {
      const winX = i === 0 ? -w / 2 + 20 * scaleRatio : w / 2 - 45 * scaleRatio;
      this.graphics.roundRect(winX, windowY, windowWidth, windowHeight, 2 * scaleRatio);
      this.graphics.fill(0xadd8e6);
      this.graphics.stroke({ width: 1 * scaleRatio, color: 0x333333 });
    }

    this.container.addChild(this.graphics);
  }

  /**
   * Render the building label.
   */
  private renderLabel(): void {
    this.label = new Text({
      text: this.config.label,
      style: {
        fontFamily: "Arial",
        fontSize: ISOMETRIC_MODE ? 10 : 12,
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

    this.label.anchor.set(0.5, 0);
    this.label.position.set(0, 3);

    this.container.addChild(this.label);
  }

  /**
   * Adjust position for proper isometric placement.
   * Buildings anchor at center-bottom of their sprite.
   */
  private adjustPosition(): void {
    // In isometric mode, offset Y by half tile height to align with grid
    if (ISOMETRIC_MODE) {
      // Position is already set by updatePosition() from base class
      // But we need to adjust for building height and tile alignment
      this.container.y += ISO_TILE_HEIGHT / 2;
    }
  }

  /**
   * Darken a color by a factor.
   */
  private darkenColor(color: number, factor: number): number {
    const r = ((color >> 16) & 0xff) * (1 - factor);
    const g = ((color >> 8) & 0xff) * (1 - factor);
    const b = (color & 0xff) * (1 - factor);
    return (Math.floor(r) << 16) | (Math.floor(g) << 8) | Math.floor(b);
  }

  // ============================================
  // ACCESSORS
  // ============================================

  /** Get building type */
  get type(): "business" | "office" | "landmark" {
    return this.config.type;
  }

  /** Get industry */
  get industry(): string | undefined {
    return this.config.industry;
  }

  /** Get scaled width */
  get width(): number {
    return this.scaledWidth;
  }

  /** Get scaled height */
  get height(): number {
    return this.scaledHeight;
  }

  /** Get label text */
  get labelText(): string {
    return this.config.label;
  }
}
