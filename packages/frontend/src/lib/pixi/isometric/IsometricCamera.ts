/**
 * IsometricCamera - Manages viewport, offset, and coordinate transformations.
 *
 * This is the single source of truth for:
 * - Converting between grid and screen coordinates
 * - Calculating offsets to center the isometric grid
 * - Future: viewport position and zoom
 *
 * Uses diamond isometric projection where:
 * - Moving +1 in gridX moves the sprite right and down on screen
 * - Moving +1 in gridY moves the sprite left and down on screen
 */

import {
  CANVAS_WIDTH,
  CANVAS_HEIGHT,
  GRID_WIDTH,
  GRID_HEIGHT,
  ISO_TILE_WIDTH,
  ISO_TILE_HEIGHT,
  ISO_TILE_HALF_WIDTH,
  ISO_TILE_HALF_HEIGHT,
  ISOMETRIC_MODE,
  ISOMETRIC_TYPE,
  LEGACY_TILE_SIZE,
} from "./constants";

export interface Point {
  x: number;
  y: number;
}

export interface GridPosition {
  gridX: number;
  gridY: number;
}

export interface ScreenBounds {
  width: number;
  height: number;
  offsetX: number;
  offsetY: number;
}

export class IsometricCamera {
  // Camera position in world coordinates (for future panning)
  private _position: Point = { x: 0, y: 0 };

  // Zoom level (for future zooming)
  private _zoom: number = 1;

  // Grid dimensions (can be overridden per-instance)
  private readonly gridWidth: number;
  private readonly gridHeight: number;

  // Canvas dimensions
  private readonly canvasWidth: number;
  private readonly canvasHeight: number;

  constructor(options?: {
    gridWidth?: number;
    gridHeight?: number;
    canvasWidth?: number;
    canvasHeight?: number;
  }) {
    this.gridWidth = options?.gridWidth ?? GRID_WIDTH;
    this.gridHeight = options?.gridHeight ?? GRID_HEIGHT;
    this.canvasWidth = options?.canvasWidth ?? CANVAS_WIDTH;
    this.canvasHeight = options?.canvasHeight ?? CANVAS_HEIGHT;
  }

  // ============================================
  // SCREEN BOUNDS
  // ============================================

  /**
   * Calculate the screen bounds needed to display the entire grid.
   * Returns dimensions and offset for centering.
   */
  getScreenBounds(): ScreenBounds {
    if (!ISOMETRIC_MODE) {
      return {
        width: this.gridWidth * LEGACY_TILE_SIZE,
        height: this.gridHeight * LEGACY_TILE_SIZE,
        offsetX: 0,
        offsetY: 0,
      };
    }

    if (ISOMETRIC_TYPE === "staggered") {
      // Staggered: rectangular grid with offset rows
      // Width = gridWidth * tileWidth + halfWidth (for odd row offset)
      // Height = gridHeight * halfHeight + halfHeight (for tile depth)
      const totalWidth = this.gridWidth * ISO_TILE_WIDTH + ISO_TILE_HALF_WIDTH;
      const totalHeight = (this.gridHeight + 1) * ISO_TILE_HALF_HEIGHT;

      return {
        width: totalWidth,
        height: totalHeight,
        offsetX: 0,
        offsetY: 0,
      };
    }

    // Diamond projection:
    // - Width spans from leftmost tile (0, gridH-1) to rightmost tile (gridW-1, 0)
    // - Height spans from top tile (0, 0) to bottom tile (gridW-1, gridH-1)
    const totalWidth = (this.gridWidth + this.gridHeight) * ISO_TILE_HALF_WIDTH;
    const totalHeight = (this.gridWidth + this.gridHeight) * ISO_TILE_HALF_HEIGHT;

    // Offset to position tile (0,0) correctly
    const offsetX = this.gridHeight * ISO_TILE_HALF_WIDTH;
    const offsetY = 0;

    return {
      width: totalWidth,
      height: totalHeight,
      offsetX,
      offsetY,
    };
  }

  // ============================================
  // OFFSET CALCULATIONS (Single Source of Truth)
  // ============================================

  /**
   * Get the X offset to center the isometric grid on the canvas.
   * Accounts for camera position.
   */
  get offsetX(): number {
    if (!ISOMETRIC_MODE) {
      return -this._position.x;
    }

    if (ISOMETRIC_TYPE === "staggered") {
      // Center the staggered grid horizontally
      const bounds = this.getScreenBounds();
      return (this.canvasWidth - bounds.width) / 2 - this._position.x;
    }

    const bounds = this.getScreenBounds();
    return bounds.offsetX + this.canvasWidth / 2 - bounds.width / 2 - this._position.x;
  }

  /**
   * Get the Y offset for the isometric grid.
   * Minimal top margin to maximize grid coverage.
   */
  get offsetY(): number {
    if (!ISOMETRIC_MODE) {
      return -this._position.y;
    }

    if (ISOMETRIC_TYPE === "staggered") {
      // Small top margin for staggered
      return 10 - this._position.y;
    }

    // Minimal top margin (-20) to maximize vertical coverage
    return -20 - this._position.y;
  }

  // ============================================
  // COORDINATE TRANSFORMATIONS
  // ============================================

  /**
   * Convert grid coordinates to screen coordinates (isometric projection).
   * Returns the center of the tile in screen space.
   *
   * @param gridX - X position in grid coordinates
   * @param gridY - Y position in grid coordinates
   * @returns Screen position in pixels (with offsets applied)
   */
  gridToScreen(gridX: number, gridY: number): Point {
    if (!ISOMETRIC_MODE) {
      return {
        x: gridX * LEGACY_TILE_SIZE + this.offsetX,
        y: gridY * LEGACY_TILE_SIZE + this.offsetY,
      };
    }

    if (ISOMETRIC_TYPE === "staggered") {
      // Staggered isometric formula:
      // Odd rows are offset by half a tile width
      const rowOffset = (gridY % 2) * ISO_TILE_HALF_WIDTH;
      return {
        x: gridX * ISO_TILE_WIDTH + rowOffset + ISO_TILE_HALF_WIDTH + this.offsetX,
        y: gridY * ISO_TILE_HALF_HEIGHT + ISO_TILE_HALF_HEIGHT + this.offsetY,
      };
    }

    // Diamond isometric formula:
    // screenX = (gridX - gridY) * halfWidth
    // screenY = (gridX + gridY) * halfHeight
    return {
      x: (gridX - gridY) * ISO_TILE_HALF_WIDTH + this.offsetX,
      y: (gridX + gridY) * ISO_TILE_HALF_HEIGHT + this.offsetY,
    };
  }

  /**
   * Convert grid coordinates to screen coordinates WITHOUT offsets.
   * Useful for internal calculations.
   */
  gridToScreenRaw(gridX: number, gridY: number): Point {
    if (!ISOMETRIC_MODE) {
      return {
        x: gridX * LEGACY_TILE_SIZE,
        y: gridY * LEGACY_TILE_SIZE,
      };
    }

    if (ISOMETRIC_TYPE === "staggered") {
      const rowOffset = (gridY % 2) * ISO_TILE_HALF_WIDTH;
      return {
        x: gridX * ISO_TILE_WIDTH + rowOffset + ISO_TILE_HALF_WIDTH,
        y: gridY * ISO_TILE_HALF_HEIGHT + ISO_TILE_HALF_HEIGHT,
      };
    }

    return {
      x: (gridX - gridY) * ISO_TILE_HALF_WIDTH,
      y: (gridX + gridY) * ISO_TILE_HALF_HEIGHT,
    };
  }

  /**
   * Convert screen coordinates to grid coordinates (reverse projection).
   * Useful for mouse picking and collision detection.
   *
   * @param screenX - X position in pixels
   * @param screenY - Y position in pixels
   * @returns Grid position (floored to integers)
   */
  screenToGrid(screenX: number, screenY: number): GridPosition {
    if (!ISOMETRIC_MODE) {
      return {
        gridX: Math.floor((screenX - this.offsetX) / LEGACY_TILE_SIZE),
        gridY: Math.floor((screenY - this.offsetY) / LEGACY_TILE_SIZE),
      };
    }

    // Remove offsets first
    const relX = screenX - this.offsetX;
    const relY = screenY - this.offsetY;

    if (ISOMETRIC_TYPE === "staggered") {
      // Staggered reverse transform
      // First, find approximate row (gridY)
      const approxY = Math.floor((relY - ISO_TILE_HALF_HEIGHT) / ISO_TILE_HALF_HEIGHT);
      const gridY = Math.max(0, approxY);

      // Then find column accounting for row offset
      const rowOffset = (gridY % 2) * ISO_TILE_HALF_WIDTH;
      const gridX = Math.floor((relX - rowOffset - ISO_TILE_HALF_WIDTH) / ISO_TILE_WIDTH);

      return { gridX: Math.max(0, gridX), gridY };
    }

    // Diamond reverse transform:
    // x = (gx - gy) * halfW  =>  x/halfW = gx - gy
    // y = (gx + gy) * halfH  =>  y/halfH = gx + gy
    //
    // Adding: x/halfW + y/halfH = 2*gx  =>  gx = (x/halfW + y/halfH) / 2
    // Subtracting: y/halfH - x/halfW = 2*gy  =>  gy = (y/halfH - x/halfW) / 2
    const gx = (relX / ISO_TILE_HALF_WIDTH + relY / ISO_TILE_HALF_HEIGHT) / 2;
    const gy = (relY / ISO_TILE_HALF_HEIGHT - relX / ISO_TILE_HALF_WIDTH) / 2;

    return {
      gridX: Math.floor(gx),
      gridY: Math.floor(gy),
    };
  }

  /**
   * Get precise grid position (floating point) for smooth interpolation.
   */
  screenToGridPrecise(screenX: number, screenY: number): Point {
    if (!ISOMETRIC_MODE) {
      return {
        x: (screenX - this.offsetX) / LEGACY_TILE_SIZE,
        y: (screenY - this.offsetY) / LEGACY_TILE_SIZE,
      };
    }

    const relX = screenX - this.offsetX;
    const relY = screenY - this.offsetY;

    if (ISOMETRIC_TYPE === "staggered") {
      const y = (relY - ISO_TILE_HALF_HEIGHT) / ISO_TILE_HALF_HEIGHT;
      const gridY = Math.max(0, y);
      const rowOffset = (Math.floor(gridY) % 2) * ISO_TILE_HALF_WIDTH;
      const x = (relX - rowOffset - ISO_TILE_HALF_WIDTH) / ISO_TILE_WIDTH;
      return { x, y: gridY };
    }

    return {
      x: (relX / ISO_TILE_HALF_WIDTH + relY / ISO_TILE_HALF_HEIGHT) / 2,
      y: (relY / ISO_TILE_HALF_HEIGHT - relX / ISO_TILE_HALF_WIDTH) / 2,
    };
  }

  // ============================================
  // DEPTH SORTING
  // ============================================

  /**
   * Calculate depth value for z-sorting (painter's algorithm).
   * Objects with higher depth values render on top.
   *
   * In isometric view, depth = gridX + gridY (objects further down-right are "in front")
   */
  calculateDepth(gridX: number, gridY: number): number {
    if (!ISOMETRIC_MODE) {
      return gridY;
    }
    return gridX + gridY;
  }

  /**
   * Calculate depth from screen Y position.
   * Works well with PixiJS's sortableChildren since screen Y increases as we go deeper.
   */
  calculateDepthFromScreenY(screenY: number): number {
    return screenY;
  }

  // ============================================
  // GRID VALIDATION
  // ============================================

  /**
   * Check if a grid position is within valid bounds.
   */
  isValidGridPosition(gridX: number, gridY: number): boolean {
    return (
      gridX >= 0 &&
      gridX < this.gridWidth &&
      gridY >= 0 &&
      gridY < this.gridHeight
    );
  }

  /**
   * Clamp a grid position to valid bounds.
   */
  clampGridPosition(gridX: number, gridY: number): GridPosition {
    return {
      gridX: Math.max(0, Math.min(this.gridWidth - 1, gridX)),
      gridY: Math.max(0, Math.min(this.gridHeight - 1, gridY)),
    };
  }

  // ============================================
  // VIEWPORT QUERIES (For future camera features)
  // ============================================

  /**
   * Get the visible grid bounds (tiles that are on screen).
   * Useful for culling optimization.
   */
  getVisibleBounds(): { minX: number; maxX: number; minY: number; maxY: number } {
    // Convert screen corners to grid positions
    const topLeft = this.screenToGrid(0, 0);
    const topRight = this.screenToGrid(this.canvasWidth, 0);
    const bottomLeft = this.screenToGrid(0, this.canvasHeight);
    const bottomRight = this.screenToGrid(this.canvasWidth, this.canvasHeight);

    // Get bounding box with padding
    const padding = 2;
    return {
      minX: Math.max(0, Math.min(topLeft.gridX, bottomLeft.gridX) - padding),
      maxX: Math.min(this.gridWidth - 1, Math.max(topRight.gridX, bottomRight.gridX) + padding),
      minY: Math.max(0, Math.min(topLeft.gridY, topRight.gridY) - padding),
      maxY: Math.min(this.gridHeight - 1, Math.max(bottomLeft.gridY, bottomRight.gridY) + padding),
    };
  }

  /**
   * Check if a grid position is currently visible on screen.
   */
  isVisible(gridX: number, gridY: number): boolean {
    const bounds = this.getVisibleBounds();
    return (
      gridX >= bounds.minX &&
      gridX <= bounds.maxX &&
      gridY >= bounds.minY &&
      gridY <= bounds.maxY
    );
  }

  // ============================================
  // CAMERA CONTROL (For future features)
  // ============================================

  /** Get camera position */
  get position(): Point {
    return { ...this._position };
  }

  /** Set camera position */
  set position(value: Point) {
    this._position = { ...value };
  }

  /** Get zoom level */
  get zoom(): number {
    return this._zoom;
  }

  /** Set zoom level */
  set zoom(value: number) {
    this._zoom = Math.max(0.5, Math.min(2, value));
  }

  /** Pan camera by delta */
  pan(dx: number, dy: number): void {
    this._position.x += dx;
    this._position.y += dy;
  }

  /** Center camera on a grid position */
  centerOn(gridX: number, gridY: number): void {
    const screenPos = this.gridToScreenRaw(gridX, gridY);
    this._position.x = screenPos.x - this.canvasWidth / 2;
    this._position.y = screenPos.y - this.canvasHeight / 2;
  }
}
