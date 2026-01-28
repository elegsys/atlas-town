/**
 * AnimatedCharacter - Encapsulates character sprite rendering and procedural animations.
 *
 * Since current assets are single portrait images (not sprite sheets), this class
 * implements procedural animations (bobbing, breathing) using ticker-based sin waves.
 * Architecture is ready for future sprite sheet support.
 */

import { Container, Sprite, Text, Graphics, Ticker, Texture } from "pixi.js";
import {
  CharacterAnimationState,
  FacingDirection,
  CharacterDefinition,
  ANIMATION_CONFIG,
  CHARACTER_DISPLAY_WIDTH,
  CHARACTER_DISPLAY_HEIGHT,
} from "./characterConfig";
import { getCharacterTexture, areCharacterAssetsLoaded } from "./spriteLoader";

export class AnimatedCharacter {
  /** Main container - add this to the stage */
  public readonly container: Container;

  /** Current animation state */
  private _state: CharacterAnimationState = "idle";

  /** Current facing direction */
  private _direction: FacingDirection = "right";

  /** Character definition */
  private readonly definition: CharacterDefinition;

  /** Internal sprite (may be null if fallback) */
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
    const texture = getCharacterTexture(this.definition.id);

    if (texture && areCharacterAssetsLoaded()) {
      // Use sprite
      this.sprite = new Sprite(texture);
      this.setupSprite(this.sprite, texture);
      this.spriteContainer.addChild(this.sprite);
    } else {
      // Use procedural fallback
      this.fallbackGraphics = this.createFallbackGraphics();
      this.spriteContainer.addChild(this.fallbackGraphics);
    }
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

  /** Apply bobbing and breathing animations */
  private applyAnimations(): void {
    const config = ANIMATION_CONFIG;
    let bobAmplitude: number;
    let bobFrequency: number;

    // Select animation parameters based on state
    if (this._state === "walking") {
      bobAmplitude = config.walkingBobAmplitude;
      bobFrequency = config.walkingBobFrequency;
    } else {
      // idle, thinking, speaking all use idle animation
      bobAmplitude = config.idleBobAmplitude;
      bobFrequency = config.idleBobFrequency;
    }

    // Bobbing (vertical oscillation)
    const bobOffset = Math.sin(this.animationTime * bobFrequency * Math.PI * 2) * bobAmplitude;
    this.spriteContainer.y = bobOffset;

    // Breathing (scale oscillation) - only for idle states
    if (this._state !== "walking") {
      const breathScale = 1 + Math.sin(this.animationTime * 0.8 * Math.PI * 2) * config.breathingScale;
      this.spriteContainer.scale.set(
        this._direction === "left" ? -breathScale : breathScale,
        breathScale
      );
    } else {
      // Walking - just handle direction flip
      this.spriteContainer.scale.set(
        this._direction === "left" ? -1 : 1,
        1
      );
    }
  }

  /** Update movement animation */
  private updateMovement(delta: number): void {
    this.movement.elapsed += delta * 1000; // Convert to ms
    const progress = Math.min(1, this.movement.elapsed / this.movement.duration);

    // Ease out cubic
    const eased = 1 - Math.pow(1 - progress, 3);

    // Update position
    this.container.x = this.movement.startX + (this.movement.targetX - this.movement.startX) * eased;
    this.container.y = this.movement.startY + (this.movement.targetY - this.movement.startY) * eased;

    // Update direction based on movement
    if (this.movement.targetX < this.movement.startX) {
      this._direction = "left";
    } else if (this.movement.targetX > this.movement.startX) {
      this._direction = "right";
    }

    // Check if complete
    if (progress >= 1) {
      this.movement.active = false;
      this._state = "idle";
      if (this.movement.resolve) {
        this.movement.resolve();
        this.movement.resolve = null;
      }
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
