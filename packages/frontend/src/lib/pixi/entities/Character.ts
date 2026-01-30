/**
 * Character - Isometric character entity for Atlas Town.
 *
 * Handles character sprite rendering with directional animations.
 * Extends IsometricEntity for grid-based positioning with smooth movement.
 *
 * This is an adaptation of AnimatedCharacter that integrates with the
 * new isometric architecture while preserving animation functionality.
 */

import { Sprite, Text, Graphics, Ticker, Texture, Container } from "pixi.js";
import { IsometricEntity, EntityConfig } from "../isometric/IsometricEntity";
import { IsometricCamera } from "../isometric/IsometricCamera";
import {
  ISOMETRIC_MODE,
  ISO_TILE_HEIGHT,
} from "../isometric/constants";
import {
  CharacterAnimationState,
  FacingDirection,
  FacingDirection8,
  ANIMATION_CONFIG,
  CHARACTER_DISPLAY_WIDTH,
  CHARACTER_DISPLAY_HEIGHT,
  DIRECTIONS_4,
  DIRECTIONS_8,
  WALKING_FRAME_COUNT,
  DIRECTION_8_TO_4,
} from "../characterConfig";
import { getDirectionFromDelta } from "../isometric";

export interface CharacterConfig extends EntityConfig {
  /** Theme color for procedural fallback */
  themeColor: number;
  /** Path to legacy portrait sprite */
  spritePath?: string;
}

// Callbacks for texture loading (set by TownCanvas during asset loading)
export type TextureLoader = {
  getRotationTexture: (characterId: string, direction: FacingDirection) => Texture | undefined;
  getWalkingFrames: (characterId: string, direction: FacingDirection) => Texture[] | undefined;
  areAssetsLoaded: () => boolean;
  areSheetsLoaded: () => boolean;
};

let textureLoader: TextureLoader | null = null;

/**
 * Set the texture loader callbacks.
 * Must be called before creating Character instances.
 */
export function setCharacterTextureLoader(loader: TextureLoader): void {
  textureLoader = loader;
}

export class Character extends IsometricEntity {
  /** Character configuration */
  private readonly config: CharacterConfig;

  /** Animation ticker */
  private readonly ticker: Ticker;

  /** Current animation state */
  private _state: CharacterAnimationState = "idle";

  /** Current facing direction */
  private _direction: FacingDirection = "south";

  /** Sprite container (for animations) */
  private spriteContainer: Container;

  /** Main sprite */
  private sprite: Sprite | null = null;

  /** Procedural fallback graphics */
  private fallbackGraphics: Graphics | null = null;

  /** Shadow ellipse */
  private shadow: Graphics | null = null;

  /** Name label */
  private nameLabel: Text | null = null;

  /** Animation time accumulator */
  private animationTime = 0;

  /** Whether using sprite sheets */
  private usingSpriteSheets = false;

  /** Cached rotation textures */
  private rotationTextures: Map<FacingDirection, Texture> = new Map();

  /** Cached walking frames */
  private walkingFrames: Map<FacingDirection, Texture[]> = new Map();

  /** Current walking frame index */
  private currentWalkFrame = 0;

  /** Walking frame time accumulator */
  private walkFrameTime = 0;

  /** Frame duration in ms */
  private readonly frameDuration = 150;

  /** Movement animation state */
  private movement: {
    active: boolean;
    startX: number;
    startY: number;
    targetX: number;
    targetY: number;
    duration: number;
    elapsed: number;
    resolve: (() => void) | null;
  } = {
    active: false,
    startX: 0,
    startY: 0,
    targetX: 0,
    targetY: 0,
    duration: 0,
    elapsed: 0,
    resolve: null,
  };

  constructor(camera: IsometricCamera, config: CharacterConfig, ticker: Ticker) {
    super(camera, config);
    this.config = config;
    this.ticker = ticker;

    // Create sprite container for animations
    this.spriteContainer = new Container();
    this.container.addChild(this.spriteContainer);

    // Start animation loop
    this.ticker.add(this.update, this);
  }

  // ============================================
  // BUILD (from IsometricEntity)
  // ============================================

  build(): void {
    // Create shadow
    this.shadow = new Graphics();
    this.shadow.ellipse(0, CHARACTER_DISPLAY_HEIGHT / 2 + 5, 20, 6);
    this.shadow.fill({ color: 0x000000, alpha: 0.25 });
    this.container.addChild(this.shadow);

    // Initialize visuals (sprite or fallback)
    this.initializeVisuals();

    // Create name label
    this.nameLabel = new Text({
      text: this.name,
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
    this.nameLabel.anchor.set(0.5, 0);
    this.nameLabel.position.set(0, CHARACTER_DISPLAY_HEIGHT / 2 + 12);
    this.container.addChild(this.nameLabel);
  }

  /**
   * Initialize sprite or fallback graphics.
   */
  private initializeVisuals(): void {
    if (textureLoader?.areSheetsLoaded()) {
      const success = this.loadSpriteSheetTextures();
      if (success) {
        this.usingSpriteSheets = true;
        const initialTexture = this.rotationTextures.get(this._direction);
        if (initialTexture) {
          this.sprite = new Sprite(initialTexture);
          this.setupSprite(this.sprite, initialTexture);
          this.spriteContainer.addChild(this.sprite);
          return;
        }
      }
    }

    // Fallback to procedural
    this.fallbackGraphics = this.createFallbackGraphics();
    this.spriteContainer.addChild(this.fallbackGraphics);
  }

  /**
   * Load sprite sheet textures into caches.
   */
  private loadSpriteSheetTextures(): boolean {
    if (!textureLoader) return false;

    const directionsToLoad = ISOMETRIC_MODE ? DIRECTIONS_8 : DIRECTIONS_4;

    // Load rotation textures
    for (const direction of directionsToLoad) {
      const texture = textureLoader.getRotationTexture(this.id, direction);
      if (texture) {
        this.rotationTextures.set(direction, texture);
      } else if (ISOMETRIC_MODE) {
        // Fallback to 4-direction
        const fallbackDir = DIRECTION_8_TO_4[direction as FacingDirection8];
        if (fallbackDir !== direction) {
          const fallbackTexture = textureLoader.getRotationTexture(this.id, fallbackDir);
          if (fallbackTexture) {
            this.rotationTextures.set(direction, fallbackTexture);
          }
        }
      }
    }

    // Load walking frames
    for (const direction of directionsToLoad) {
      const frames = textureLoader.getWalkingFrames(this.id, direction);
      if (frames && frames.length === WALKING_FRAME_COUNT) {
        this.walkingFrames.set(direction, frames);
      } else if (ISOMETRIC_MODE) {
        const fallbackDir = DIRECTION_8_TO_4[direction as FacingDirection8];
        if (fallbackDir !== direction) {
          const fallbackFrames = textureLoader.getWalkingFrames(this.id, fallbackDir);
          if (fallbackFrames && fallbackFrames.length === WALKING_FRAME_COUNT) {
            this.walkingFrames.set(direction, fallbackFrames);
          }
        }
      }
    }

    return this.rotationTextures.size > 0 && this.walkingFrames.size > 0;
  }

  /**
   * Setup sprite scaling and anchor.
   */
  private setupSprite(sprite: Sprite, texture: Texture): void {
    const scaleX = CHARACTER_DISPLAY_WIDTH / texture.width;
    const scaleY = CHARACTER_DISPLAY_HEIGHT / texture.height;
    const scale = Math.min(scaleX, scaleY);

    sprite.scale.set(scale);
    sprite.anchor.set(0.5, 0.5);
  }

  /**
   * Create procedural fallback graphics.
   */
  private createFallbackGraphics(): Graphics {
    const graphics = new Graphics();
    const color = this.config.themeColor;

    // Head
    graphics.circle(0, -20, 15);
    graphics.fill(0xffdab9);

    // Body
    graphics.roundRect(-12, -5, 24, 35, 6);
    graphics.fill(color);

    return graphics;
  }

  // ============================================
  // ANIMATION LOOP
  // ============================================

  private update = (ticker: Ticker): void => {
    const delta = ticker.deltaMS / 1000;
    this.animationTime += delta;

    if (this.movement.active) {
      this.updateMovement(delta);
    }

    this.applyAnimations();
  };

  private applyAnimations(): void {
    const config = ANIMATION_CONFIG;

    if (this._state === "walking") {
      if (this.usingSpriteSheets) {
        const frameOffset = Math.sin((this.currentWalkFrame / WALKING_FRAME_COUNT) * Math.PI * 2);
        this.spriteContainer.y = frameOffset * config.walkingBobAmplitude * 0.5;
      } else {
        const bobOffset = Math.sin(this.animationTime * config.walkingBobFrequency * Math.PI * 2) * config.walkingBobAmplitude;
        this.spriteContainer.y = bobOffset;
      }
      this.spriteContainer.scale.set(1, 1);
    } else {
      const bobOffset = Math.sin(this.animationTime * config.idleBobFrequency * Math.PI * 2) * config.idleBobAmplitude;
      this.spriteContainer.y = bobOffset;

      const breathScale = 1 + Math.sin(this.animationTime * 0.8 * Math.PI * 2) * config.breathingScale;
      this.spriteContainer.scale.set(breathScale, breathScale);
    }
  }

  private updateWalkingAnimation(deltaMs: number): void {
    if (!this.usingSpriteSheets || this._state !== "walking") return;

    this.walkFrameTime += deltaMs;
    if (this.walkFrameTime >= this.frameDuration) {
      this.walkFrameTime = 0;
      this.currentWalkFrame = (this.currentWalkFrame + 1) % WALKING_FRAME_COUNT;
      this.updateSpriteTexture();
    }
  }

  private updateSpriteTexture(): void {
    if (!this.sprite || !this.usingSpriteSheets) return;

    let texture: Texture | undefined;

    if (this._state === "walking") {
      const frames = this.walkingFrames.get(this._direction);
      if (frames && frames[this.currentWalkFrame]) {
        texture = frames[this.currentWalkFrame];
      }
    } else {
      texture = this.rotationTextures.get(this._direction);
    }

    if (texture) {
      this.sprite.texture = texture;
    }
  }

  private updateMovement(delta: number): void {
    const deltaMs = delta * 1000;
    this.movement.elapsed += deltaMs;
    const progress = Math.min(1, this.movement.elapsed / this.movement.duration);

    // Ease out cubic
    const eased = 1 - Math.pow(1 - progress, 3);

    // Update position
    this.container.x = this.movement.startX + (this.movement.targetX - this.movement.startX) * eased;
    this.container.y = this.movement.startY + (this.movement.targetY - this.movement.startY) * eased;

    // Update depth as we move
    this.updateDepth();

    // Calculate direction
    const dx = this.movement.targetX - this.movement.startX;
    const dy = this.movement.targetY - this.movement.startY;
    const newDirection = this.calculateDirection(dx, dy);
    if (newDirection !== this._direction) {
      this._direction = newDirection;
      this.updateSpriteTexture();
    }

    this.updateWalkingAnimation(deltaMs);

    // Check completion
    if (progress >= 1) {
      this.movement.active = false;
      this._state = "idle";
      this.currentWalkFrame = 0;
      this.walkFrameTime = 0;
      this.updateSpriteTexture();
      if (this.movement.resolve) {
        this.movement.resolve();
        this.movement.resolve = null;
      }
    }
  }

  private calculateDirection(dx: number, dy: number): FacingDirection {
    if (dx === 0 && dy === 0) return this._direction;

    if (ISOMETRIC_MODE) {
      const isoDir = getDirectionFromDelta(dx, dy);
      if (isoDir) return isoDir as FacingDirection;
      return this._direction;
    }

    if (Math.abs(dx) > Math.abs(dy)) {
      return dx > 0 ? "east" : "west";
    } else {
      return dy > 0 ? "south" : "north";
    }
  }

  // ============================================
  // PUBLIC API
  // ============================================

  get state(): CharacterAnimationState {
    return this._state;
  }

  set state(value: CharacterAnimationState) {
    this._state = value;
    this.updateSpriteTexture();
  }

  get direction(): FacingDirection {
    return this._direction;
  }

  set direction(value: FacingDirection) {
    this._direction = value;
    this.updateSpriteTexture();
  }

  get themeColor(): number {
    return this.config.themeColor;
  }

  /**
   * Move character to screen position with animation.
   */
  moveTo(x: number, y: number, duration?: number): Promise<void> {
    return new Promise((resolve) => {
      const distance = Math.sqrt(
        Math.pow(x - this.container.x, 2) + Math.pow(y - this.container.y, 2)
      );

      const actualDuration = duration ?? Math.min(2000, Math.max(500, distance * 3));

      this.movement = {
        active: true,
        startX: this.container.x,
        startY: this.container.y,
        targetX: x,
        targetY: y,
        duration: actualDuration,
        elapsed: 0,
        resolve,
      };

      this._state = "walking";
    });
  }

  /**
   * Move to a grid position with animation.
   */
  moveToGrid(gridX: number, gridY: number, duration?: number): Promise<void> {
    const screenPos = this.camera.gridToScreen(gridX, gridY);
    return this.moveTo(screenPos.x, screenPos.y + ISO_TILE_HEIGHT / 2, duration);
  }

  /**
   * Teleport to screen position instantly.
   */
  teleportTo(x: number, y: number): void {
    this.container.x = x;
    this.container.y = y;
    this.updateDepth();
  }

  /**
   * Override updatePosition to add tile height offset.
   */
  override updatePosition(): void {
    const screenPos = this.camera.gridToScreen(this._gridX, this._gridY);
    this.container.x = screenPos.x;
    this.container.y = screenPos.y + ISO_TILE_HEIGHT / 2;
    this.updateDepth();
  }

  /**
   * Clean up resources.
   */
  override destroy(): void {
    this.ticker.remove(this.update, this);
    super.destroy();
  }
}
