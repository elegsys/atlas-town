/**
 * AnimatedCharacter - Encapsulates character sprite rendering and frame-based animations.
 *
 * Uses PixelLab-generated sprite sheets with 4 directional views and walking animations.
 * Falls back to procedural graphics if sprite sheets fail to load.
 */

import { Container, Sprite, Text, Graphics, Ticker, Texture } from "pixi.js";
import {
  CharacterAnimationState,
  FacingDirection,
  CharacterDefinition,
  ANIMATION_CONFIG,
  CHARACTER_DISPLAY_WIDTH,
  CHARACTER_DISPLAY_HEIGHT,
  ALL_DIRECTIONS,
  WALKING_FRAME_COUNT,
} from "./characterConfig";
import {
  getCharacterTexture,
  areCharacterAssetsLoaded,
  areCharacterSheetsLoaded,
  getCharacterRotationTexture,
  getCharacterWalkingFrames,
} from "./spriteLoader";

export class AnimatedCharacter {
  /** Main container - add this to the stage */
  public readonly container: Container;

  /** Current animation state */
  private _state: CharacterAnimationState = "idle";

  /** Current facing direction (4 cardinal directions) */
  private _direction: FacingDirection = "south";

  /** Character definition */
  private readonly definition: CharacterDefinition;

  /** Internal sprite for displaying current frame */
  private sprite: Sprite | null = null;

  /** Procedural fallback graphics */
  private fallbackGraphics: Graphics | null = null;

  /** Name label */
  private nameLabel: Text;

  /** Shadow ellipse */
  private shadow: Graphics;

  /** Container for sprite/graphics (for animations) */
  private spriteContainer: Container;

  /** Animation time accumulator */
  private animationTime = 0;

  /** Ticker for animations */
  private ticker: Ticker;

  /** Whether sprite sheets are being used (vs legacy or fallback) */
  private usingSpriteSheets = false;

  /** Cached rotation textures per direction (idle frames) */
  private rotationTextures: Map<FacingDirection, Texture> = new Map();

  /** Cached walking frame textures per direction */
  private walkingFrames: Map<FacingDirection, Texture[]> = new Map();

  /** Current walking animation frame index (0-3) */
  private currentWalkFrame = 0;

  /** Time accumulator for frame advancement */
  private walkFrameTime = 0;

  /** Duration of each walking frame in ms */
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

  constructor(definition: CharacterDefinition, ticker: Ticker) {
    this.definition = definition;
    this.ticker = ticker;

    // Create main container
    this.container = new Container();
    this.container.label = `character_${definition.id}`;

    // Create sprite container (for applying animations)
    this.spriteContainer = new Container();
    this.container.addChild(this.spriteContainer);

    // Create shadow
    this.shadow = new Graphics();
    this.shadow.ellipse(0, CHARACTER_DISPLAY_HEIGHT / 2 + 5, 20, 6);
    this.shadow.fill({ color: 0x000000, alpha: 0.25 });
    this.container.addChild(this.shadow);

    // Try to load sprite, fall back to procedural
    this.initializeVisuals();

    // Create name label
    this.nameLabel = new Text({
      text: definition.name,
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

    // Start animation loop
    this.ticker.add(this.update, this);
  }

  /** Initialize sprite or fallback graphics */
  private initializeVisuals(): void {
    // Try sprite sheets first (preferred)
    if (areCharacterSheetsLoaded()) {
      const success = this.loadSpriteSheetTextures();
      if (success) {
        this.usingSpriteSheets = true;
        // Create sprite with initial direction texture
        const initialTexture = this.rotationTextures.get(this._direction);
        if (initialTexture) {
          this.sprite = new Sprite(initialTexture);
          this.setupSprite(this.sprite, initialTexture);
          this.spriteContainer.addChild(this.sprite);
          return;
        }
      }
    }

    // Fall back to legacy single portrait
    const texture = getCharacterTexture(this.definition.id);
    if (texture && areCharacterAssetsLoaded()) {
      this.sprite = new Sprite(texture);
      this.setupSprite(this.sprite, texture);
      this.spriteContainer.addChild(this.sprite);
      return;
    }

    // Final fallback: procedural graphics
    this.fallbackGraphics = this.createFallbackGraphics();
    this.spriteContainer.addChild(this.fallbackGraphics);
  }

  /** Load all sprite sheet textures into caches */
  private loadSpriteSheetTextures(): boolean {
    const characterId = this.definition.id;

    // Load rotation textures
    for (const direction of ALL_DIRECTIONS) {
      const texture = getCharacterRotationTexture(characterId, direction);
      if (texture) {
        this.rotationTextures.set(direction, texture);
      }
    }

    // Load walking frames
    for (const direction of ALL_DIRECTIONS) {
      const frames = getCharacterWalkingFrames(characterId, direction);
      if (frames && frames.length === WALKING_FRAME_COUNT) {
        this.walkingFrames.set(direction, frames);
      }
    }

    // Success if we have at least one rotation and walking set
    return this.rotationTextures.size > 0 && this.walkingFrames.size > 0;
  }

  /** Setup sprite with proper scaling and anchoring */
  private setupSprite(sprite: Sprite, texture: Texture): void {
    // Scale proportionally to fit target dimensions
    const scaleX = CHARACTER_DISPLAY_WIDTH / texture.width;
    const scaleY = CHARACTER_DISPLAY_HEIGHT / texture.height;
    const scale = Math.min(scaleX, scaleY);

    sprite.scale.set(scale);

    // Center anchor for easier positioning
    sprite.anchor.set(0.5, 0.5);
  }

  /** Create procedural fallback graphics (matches original TownCanvas style) */
  private createFallbackGraphics(): Graphics {
    const graphics = new Graphics();
    const color = this.definition.themeColor;

    // Head
    graphics.circle(0, -20, 15);
    graphics.fill(0xffdab9); // Peach

    // Body
    graphics.roundRect(-12, -5, 24, 35, 6);
    graphics.fill(color);

    return graphics;
  }

  /** Animation update loop */
  private update = (ticker: Ticker): void => {
    const delta = ticker.deltaMS / 1000; // Convert to seconds
    this.animationTime += delta;

    // Update movement if active
    if (this.movement.active) {
      this.updateMovement(delta);
    }

    // Apply procedural animations based on state
    this.applyAnimations();
  };

  /** Apply animations based on current state */
  private applyAnimations(): void {
    const config = ANIMATION_CONFIG;

    if (this._state === "walking") {
      // Walking state: frame-based animation (no procedural bob)
      if (this.usingSpriteSheets) {
        // Frame cycling is handled in updateWalkingAnimation()
        // Just apply subtle vertical offset synced with frames
        const frameOffset = Math.sin((this.currentWalkFrame / WALKING_FRAME_COUNT) * Math.PI * 2);
        this.spriteContainer.y = frameOffset * config.walkingBobAmplitude * 0.5;
      } else {
        // Legacy: procedural walking bob
        const bobOffset = Math.sin(this.animationTime * config.walkingBobFrequency * Math.PI * 2) * config.walkingBobAmplitude;
        this.spriteContainer.y = bobOffset;
      }
      // No breathing/scale during walking
      this.spriteContainer.scale.set(1, 1);
    } else {
      // Idle/thinking/speaking: subtle bobbing and breathing
      const bobOffset = Math.sin(this.animationTime * config.idleBobFrequency * Math.PI * 2) * config.idleBobAmplitude;
      this.spriteContainer.y = bobOffset;

      const breathScale = 1 + Math.sin(this.animationTime * 0.8 * Math.PI * 2) * config.breathingScale;
      this.spriteContainer.scale.set(breathScale, breathScale);
    }
  }

  /** Update walking animation frames */
  private updateWalkingAnimation(deltaMs: number): void {
    if (!this.usingSpriteSheets || this._state !== "walking") {
      return;
    }

    this.walkFrameTime += deltaMs;
    if (this.walkFrameTime >= this.frameDuration) {
      this.walkFrameTime = 0;
      this.currentWalkFrame = (this.currentWalkFrame + 1) % WALKING_FRAME_COUNT;
      this.updateSpriteTexture();
    }
  }

  /** Update the sprite texture based on current state and direction */
  private updateSpriteTexture(): void {
    if (!this.sprite || !this.usingSpriteSheets) {
      return;
    }

    let texture: Texture | undefined;

    if (this._state === "walking") {
      // Use walking frame
      const frames = this.walkingFrames.get(this._direction);
      if (frames && frames[this.currentWalkFrame]) {
        texture = frames[this.currentWalkFrame];
      }
    } else {
      // Use rotation (idle) texture
      texture = this.rotationTextures.get(this._direction);
    }

    if (texture) {
      this.sprite.texture = texture;
    }
  }

  /** Update movement animation */
  private updateMovement(delta: number): void {
    const deltaMs = delta * 1000;
    this.movement.elapsed += deltaMs;
    const progress = Math.min(1, this.movement.elapsed / this.movement.duration);

    // Ease out cubic
    const eased = 1 - Math.pow(1 - progress, 3);

    // Update position
    this.container.x = this.movement.startX + (this.movement.targetX - this.movement.startX) * eased;
    this.container.y = this.movement.startY + (this.movement.targetY - this.movement.startY) * eased;

    // Calculate direction based on movement vector (4 cardinal directions)
    const dx = this.movement.targetX - this.movement.startX;
    const dy = this.movement.targetY - this.movement.startY;

    // Use dominant axis to determine direction
    const newDirection = this.calculateDirection(dx, dy);
    if (newDirection !== this._direction) {
      this._direction = newDirection;
      this.updateSpriteTexture();
    }

    // Update walking animation frames
    this.updateWalkingAnimation(deltaMs);

    // Check if complete
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

  /** Calculate facing direction from movement vector */
  private calculateDirection(dx: number, dy: number): FacingDirection {
    // If no movement, keep current direction
    if (dx === 0 && dy === 0) {
      return this._direction;
    }

    // Use dominant axis to determine direction
    // In isometric/top-down games: positive Y is "south" (down), negative Y is "north" (up)
    if (Math.abs(dx) > Math.abs(dy)) {
      return dx > 0 ? "east" : "west";
    } else {
      return dy > 0 ? "south" : "north";
    }
  }

  // ============================================
  // PUBLIC API
  // ============================================

  /** Get current animation state */
  get state(): CharacterAnimationState {
    return this._state;
  }

  /** Set animation state */
  set state(value: CharacterAnimationState) {
    this._state = value;
  }

  /** Get current facing direction */
  get direction(): FacingDirection {
    return this._direction;
  }

  /** Set facing direction */
  set direction(value: FacingDirection) {
    this._direction = value;
  }

  /** Get character ID */
  get id(): string {
    return this.definition.id;
  }

  /** Get character name */
  get name(): string {
    return this.definition.name;
  }

  /** Get current X position */
  get x(): number {
    return this.container.x;
  }

  /** Get current Y position */
  get y(): number {
    return this.container.y;
  }

  /**
   * Move character to a position with animation.
   * @param x - Target X position
   * @param y - Target Y position
   * @param duration - Optional duration in ms (auto-calculated from distance if not provided)
   * @returns Promise that resolves when movement completes
   */
  moveTo(x: number, y: number, duration?: number): Promise<void> {
    return new Promise((resolve) => {
      const distance = Math.sqrt(
        Math.pow(x - this.container.x, 2) + Math.pow(y - this.container.y, 2)
      );

      // Calculate duration based on distance if not provided
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
   * Instantly teleport character to a position (no animation).
   * @param x - Target X position
   * @param y - Target Y position
   */
  teleportTo(x: number, y: number): void {
    this.container.x = x;
    this.container.y = y;
  }

  /**
   * Clean up resources when destroying the character.
   */
  destroy(): void {
    this.ticker.remove(this.update, this);
    this.container.destroy({ children: true });
  }
}
