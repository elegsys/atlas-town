#!/usr/bin/env python3
"""Generate pixel art sprites for Atlas Town using Google Nano Banana Pro.

This script uses the Google Generative AI SDK (Gemini 3 Pro Image / Nano Banana Pro)
to generate 16-bit pixel art sprites for characters, buildings, and environment tiles.

OPTIMIZED: Uses async parallel generation for faster batch processing.

Usage:
    cd packages/simulation
    source .venv/bin/activate
    python scripts/generate_sprites.py [--category CATEGORY] [--asset NAME]

Examples:
    python scripts/generate_sprites.py                    # Generate all assets
    python scripts/generate_sprites.py --category characters
    python scripts/generate_sprites.py --asset sarah      # Generate only Sarah sprite
    python scripts/generate_sprites.py --concurrency 4    # Run 4 parallel requests

Models:
    - gemini-3-pro-image-preview (default, Nano Banana Pro - best quality, 2K/4K)
    - gemini-2.5-flash-image (Nano Banana - faster, good quality)
"""

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path
from typing import NamedTuple

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

try:
    from google import genai
    from google.genai import types
except ImportError:
    print("Error: google-genai package not installed.")
    print("Install with: pip install google-genai")
    sys.exit(1)

# Default to Nano Banana Pro (best quality)
DEFAULT_MODEL = "gemini-3-pro-image-preview"
FAST_MODEL = "gemini-2.5-flash-image"

# Default concurrency (parallel requests)
DEFAULT_CONCURRENCY = 3


# ============================================================================
# SPRITE DEFINITIONS
# ============================================================================

# Master style block to append to all prompts
MASTER_STYLE = """16-bit pixel art style, SNES era aesthetic, top-down RPG view (3/4 perspective), clean defined pixel edges, limited retro color palette, game asset sprite, sharp details, no anti-aliasing, solid magenta background (#FF00FF) for easy removal"""

# Character sprite prompts (64x64 target)
CHARACTER_PROMPTS = {
    "sarah": {
        "name": "Sarah Chen - Accountant",
        "filename": "sarah_chen",
        "prompt": """Pixel art sprite sheet for a character named Sarah Chen. She is a professional Asian woman accountant with neat black hair in a bun, wearing thick-rimmed glasses, a smart navy blue blazer over a white collared blouse, and dark trousers. She is holding a brown clipboard and pen. The sheet should contain a walking animation cycle in four directions (down, up, left, right) arranged in a grid. Friendly, focused expression.""",
    },
    "craig": {
        "name": "Craig Miller - Landscaping",
        "filename": "craig_miller",
        "prompt": """Pixel art sprite sheet for character Craig Miller. A middle-aged Caucasian man with a weathered, tanned face and a friendly grin. He wears a faded green baseball cap, a dirt-stained forest green work shirt with rolled sleeves, durable work jeans, and thick brown work gloves. Walking animation cycle in four directions.""",
    },
    "tony": {
        "name": "Tony Romano - Pizzeria",
        "filename": "tony_romano",
        "prompt": """Pixel art sprite sheet for character Tony Romano. A jovial Italian-American man with a bushy black mustache. He wears a traditional white chef's coat stained slightly red, a checkered red apron, and a tall white chef's hat. He is holding a wooden pizza peel. Warm friendly expression. Walking animation cycle in four directions.""",
    },
    "maya": {
        "name": "Maya Patel - Tech Consulting",
        "filename": "maya_patel",
        "prompt": """Pixel art sprite sheet for character Maya Patel. A modern South Asian woman, confident posture. She wears a stylish charcoal grey blazer over a purple graphic t-shirt, dark jeans, and trendy glasses. She carries a sleek laptop messenger bag over her shoulder. Walking animation cycle in four directions.""",
    },
    "chen": {
        "name": "Dr. David Chen - Dental",
        "filename": "david_chen",
        "prompt": """Pixel art sprite sheet for character Dr. David Chen. An Asian-American man with neat, short dark hair. He wears a crisp white short-sleeved medical/dental coat, light blue scrubs underneath, and has a stethoscope casually around his neck. Clean, kind professional look. Walking animation cycle in four directions.""",
    },
    "marcus": {
        "name": "Marcus Thompson - Real Estate",
        "filename": "marcus_thompson",
        "prompt": """Pixel art sprite sheet for character Marcus Thompson. A tall African-American man with excellent posture. He wears a sharp, tailored navy blue suit, a crisp white shirt, and a red power tie. He is holding a manila folder or portfolio. Confident professional smile. Walking animation cycle in four directions.""",
    },
}

# Building prompts (128x128 to 192x192 target)
BUILDING_PROMPTS = {
    "landscaping": {
        "name": "Craig's Landscaping Shop",
        "filename": "craigs_landscaping",
        "prompt": """Pixel art building exterior of a small landscaping business. A rustic wooden building with a green corrugated metal roof. A sign above the door reads "CRAIG'S LANDSCAPING". Outside there are potted plants, bags of soil stacked, a wheelbarrow, and shovels leaning against the wall. Warm, welcoming, slightly cluttered look.""",
    },
    "pizzeria": {
        "name": "Tony's Pizzeria",
        "filename": "tonys_pizzeria",
        "prompt": """Pixel art building exterior of a cozy Italian pizzeria. Brick facade building with a red and white striped canvas awning over the entrance. A neon-style pixel sign reads "TONY'S PIZZA". Two small round tables with checkered tablecloths are outside on the sidewalk. Warm yellow light glows from the windows.""",
    },
    "tech": {
        "name": "Nexus Tech Office",
        "filename": "nexus_tech",
        "prompt": """Pixel art building exterior of a small two-story modern tech startup office, complete building visible from base to roof. Sleek design using blue tinted glass windows and polished grey concrete walls. A minimalist sign with a blue circuit logo reads "NEXUS TECH". Potted futuristic plants near the glass door. Clean lines, cool color palette. Entire building must fit in frame with space around it.""",
    },
    "dental": {
        "name": "Main Street Dental",
        "filename": "main_street_dental",
        "prompt": """Pixel art building exterior of a dental clinic. Clean white siding building with light blue trim. Large, clean windows showing a waiting room inside. A prominent sign features a smiling tooth logo and reads "MAIN STREET DENTAL". Very tidy and professional appearance.""",
    },
    "realty": {
        "name": "Harbor Realty Office",
        "filename": "harbor_realty",
        "prompt": """Pixel art building exterior of a real estate brokerage. A charming building with warm brown wood and gold accents. A large bay window displays pixelated photos of houses. An elegant sign above the door reads "HARBOR REALTY". Inviting entrance with a welcome mat.""",
    },
    "townhall": {
        "name": "Town Hall",
        "filename": "town_hall",
        "prompt": """Pixel art building exterior of a large town hall civic center. Classic red brick architecture with white columns at the main entrance. A central clock tower with a pixelated clock face. Town flags flying on the roof. Wide steps leading up to large double doors. Grand and central feeling.""",
    },
}

# Environment tile prompts (32x32 target)
TILE_PROMPTS = {
    "street": {
        "name": "Street Tileset",
        "filename": "street_tiles",
        "prompt": """Pixel art tileset for town streets. Includes seamless cobblestone road tiles, concrete sidewalk tiles, street corners, a crosswalk pattern, and a manhole cover tile. Clean RPG map style.""",
    },
    "park": {
        "name": "Park Elements",
        "filename": "park_elements",
        "prompt": """Pixel art assets for a town park. Includes green grass tiles, a wooden park bench, a cast iron lamp post, a small stone water fountain, and an oak tree.""",
    },
}

# UI Icon prompts (24x24 to 32x32 target)
ICON_PROMPTS = {
    "financial": {
        "name": "Financial Icons",
        "filename": "financial_icons",
        "prompt": """A set of 16-bit pixel art icons related to finance and accounting. Individual icons for: a green dollar sign, a stack of gold coins, a calculator, a credit card, a brown leather wallet, and an upward trending arrow graph. Each icon is distinct.""",
    },
    "documents": {
        "name": "Document Icons",
        "filename": "document_icons",
        "prompt": """A set of small 16-bit pixel art icons representing business documents. Individual icons for: An invoice (paper with "INV" text), a receipt (long thin paper scroll), a ledger book (open brown book), and a bank check.""",
    },
}

# Additional buildings for a complete town
EXTRA_BUILDINGS_PROMPTS = {
    "accounting_office": {
        "name": "Sarah's Accounting Office",
        "filename": "sarahs_office",
        "prompt": """Pixel art building exterior of a small professional accounting office. Clean modern design with large windows, a blue "CHEN ACCOUNTING" sign above the door, potted plants at entrance, well-maintained brick facade with white trim. Organized and professional look.""",
    },
    "bank": {
        "name": "Town Bank",
        "filename": "town_bank",
        "prompt": """Pixel art building exterior of a classic small town bank. Imposing stone facade with columns, large "ATLAS BANK" sign, brass doors, security camera visible, green awning. Trustworthy and secure appearance.""",
    },
    "cafe": {
        "name": "Corner Cafe",
        "filename": "corner_cafe",
        "prompt": """Pixel art building exterior of a cozy coffee shop cafe. Warm brown wood exterior, large windows showing interior, "BREW & CO" sign with coffee cup logo, outdoor seating with umbrellas, chalkboard menu sign outside. Inviting and warm.""",
    },
    "general_store": {
        "name": "General Store",
        "filename": "general_store",
        "prompt": """Pixel art building exterior of an old-fashioned general store. Wooden building with covered porch, "ATLAS GENERAL" painted sign, barrels and crates outside, classic small-town Americana feel.""",
    },
    "house_blue": {
        "name": "Blue Residential House",
        "filename": "house_blue",
        "prompt": """Pixel art building exterior of a cute suburban house with blue siding, white picket fence, small front yard with flowers, chimney, two windows with shutters, red front door. Cozy family home feel.""",
    },
    "house_yellow": {
        "name": "Yellow Residential House",
        "filename": "house_yellow",
        "prompt": """Pixel art building exterior of a charming cottage-style house with yellow walls, green roof, flower boxes in windows, stone pathway to front door, small garden. Warm and welcoming.""",
    },
    "apartment": {
        "name": "Small Apartment Building",
        "filename": "apartment_building",
        "prompt": """Pixel art building exterior of a three-story brick apartment building. Multiple windows with balconies, "ATLAS APARTMENTS" sign, entrance awning, fire escapes on side. Urban residential feel.""",
    },
}

# Decorations and props for the town
DECORATIONS_PROMPTS = {
    "trees": {
        "name": "Tree Collection",
        "filename": "trees",
        "prompt": """Pixel art collection of trees for a town. Includes: large oak tree with full canopy, smaller maple tree, pine/evergreen tree, cherry blossom tree with pink flowers. Each tree distinct, suitable for RPG town.""",
    },
    "bushes": {
        "name": "Bushes and Shrubs",
        "filename": "bushes",
        "prompt": """Pixel art collection of bushes and shrubs for landscaping. Includes: round green bush, flowering bush with pink flowers, hedge section, small decorative shrub. Clean garden elements.""",
    },
    "flowers": {
        "name": "Flower Beds",
        "filename": "flowers",
        "prompt": """Pixel art collection of flower arrangements. Includes: tulip bed (red, yellow, pink), rose bush, sunflower patch, daisy cluster. Colorful and cheerful garden elements.""",
    },
    "streetlights": {
        "name": "Street Lights",
        "filename": "streetlights",
        "prompt": """Pixel art collection of street lighting. Includes: classic lamp post with ornate top, modern street light, hanging string lights, old gas-style lamp. Day and lit versions.""",
    },
    "benches_tables": {
        "name": "Outdoor Furniture",
        "filename": "outdoor_furniture",
        "prompt": """Pixel art collection of outdoor furniture. Includes: wooden park bench, metal cafe table with chairs, picnic table, garden chair. Public seating elements.""",
    },
    "signs": {
        "name": "Town Signs",
        "filename": "signs",
        "prompt": """Pixel art collection of town signs. Includes: "Welcome to Atlas Town" wooden sign, street name signs, directional sign post, "OPEN/CLOSED" shop sign, parking sign.""",
    },
    "street_props": {
        "name": "Street Props",
        "filename": "street_props",
        "prompt": """Pixel art collection of street objects. Includes: red fire hydrant, green mailbox, trash can, newspaper stand, parking meter, phone booth. Urban street elements.""",
    },
    "fences": {
        "name": "Fences and Barriers",
        "filename": "fences",
        "prompt": """Pixel art collection of fences and barriers. Includes: white picket fence sections, wooden fence, iron fence, brick wall section, hedge fence. Boundary elements.""",
    },
}

# Vehicles for the town
VEHICLES_PROMPTS = {
    "cars": {
        "name": "Town Cars",
        "filename": "cars",
        "prompt": """Pixel art collection of small town vehicles. Includes: red sedan, blue compact car, silver SUV, green vintage car. Top-down/3/4 view matching RPG perspective. Parked position.""",
    },
    "work_vehicles": {
        "name": "Work Vehicles",
        "filename": "work_vehicles",
        "prompt": """Pixel art collection of work vehicles. Includes: green landscaping pickup truck with tools, white delivery van, yellow taxi, pizza delivery scooter with "TONY'S" box. Top-down RPG view.""",
    },
}


# ============================================================================
# IMAGE GENERATION
# ============================================================================


class GenerationTask(NamedTuple):
    """A single image generation task."""
    key: str
    name: str
    prompt: str
    output_path: Path
    category: str


async def generate_image_async(
    client: genai.Client,
    task: GenerationTask,
    model: str = DEFAULT_MODEL,
    semaphore: asyncio.Semaphore | None = None,
) -> tuple[str, bool, str]:
    """Generate a single image asynchronously.

    Args:
        client: Google GenAI client
        task: Generation task with prompt and output path
        model: Model to use
        semaphore: Optional semaphore for concurrency control

    Returns:
        Tuple of (task_key, success, message)
    """
    full_prompt = f"{task.prompt} {MASTER_STYLE}"

    async def _generate():
        try:
            # Use async API for parallel execution
            response = await client.aio.models.generate_content(
                model=model,
                contents=full_prompt,
                config=types.GenerateContentConfig(
                    image_config=types.ImageConfig(
                        aspect_ratio="1:1",
                        image_size="1K",
                    ),
                ),
            )

            # Extract image from response
            if response.parts:
                for part in response.parts:
                    if part.inline_data is not None:
                        image = part.as_image()
                        task.output_path.parent.mkdir(parents=True, exist_ok=True)
                        image.save(str(task.output_path))
                        return (task.key, True, f"✓ {task.name}")
                    elif part.text is not None:
                        return (task.key, False, f"✗ {task.name}: Model returned text: {part.text[:100]}")

            return (task.key, False, f"✗ {task.name}: No image in response")

        except Exception as e:
            return (task.key, False, f"✗ {task.name}: {e}")

    if semaphore:
        async with semaphore:
            return await _generate()
    else:
        return await _generate()


async def generate_batch_async(
    client: genai.Client,
    tasks: list[GenerationTask],
    model: str = DEFAULT_MODEL,
    concurrency: int = DEFAULT_CONCURRENCY,
) -> dict[str, bool]:
    """Generate multiple images in parallel.

    Args:
        client: Google GenAI client
        tasks: List of generation tasks
        model: Model to use
        concurrency: Maximum parallel requests

    Returns:
        Dictionary mapping task keys to success status
    """
    if not tasks:
        return {}

    print(f"\n  Generating {len(tasks)} images with concurrency={concurrency}")
    print(f"  Model: {model}")
    print("-" * 50)

    # Create semaphore for concurrency control
    semaphore = asyncio.Semaphore(concurrency)

    # Create all generation coroutines
    coroutines = [
        generate_image_async(client, task, model, semaphore)
        for task in tasks
    ]

    # Run all in parallel with progress updates
    results = {}
    start_time = time.time()

    # Use asyncio.as_completed for real-time progress
    for coro in asyncio.as_completed(coroutines):
        key, success, message = await coro
        results[key] = success
        elapsed = time.time() - start_time
        completed = len(results)
        print(f"  [{completed}/{len(tasks)}] ({elapsed:.1f}s) {message}")

    return results


async def run_generation(
    client: genai.Client,
    categories: dict[str, dict],
    output_dir: Path,
    model: str = DEFAULT_MODEL,
    concurrency: int = DEFAULT_CONCURRENCY,
    specific_category: str | None = None,
    specific_asset: str | None = None,
) -> dict[str, dict[str, bool]]:
    """Run sprite generation for all categories.

    Args:
        client: Google GenAI client
        categories: Dictionary of category -> prompts
        output_dir: Base output directory
        model: Model to use
        concurrency: Maximum parallel requests
        specific_category: If set, only generate this category
        specific_asset: If set, only generate this asset

    Returns:
        Dictionary mapping categories to results
    """
    all_results: dict[str, dict[str, bool]] = {}

    # Build list of all tasks
    all_tasks: list[GenerationTask] = []

    for cat_name, cat_prompts in categories.items():
        if specific_category and specific_category != "all" and cat_name != specific_category:
            continue

        category_dir = output_dir / cat_name

        for key, asset in cat_prompts.items():
            if specific_asset and key != specific_asset:
                continue

            task = GenerationTask(
                key=f"{cat_name}/{key}",
                name=asset["name"],
                prompt=asset["prompt"],
                output_path=category_dir / f"{asset['filename']}.png",
                category=cat_name,
            )
            all_tasks.append(task)

    if not all_tasks:
        print("No tasks to generate!")
        return {}

    print(f"\n{'='*60}")
    print(f"BATCH GENERATION")
    print(f"{'='*60}")
    print(f"Total assets: {len(all_tasks)}")
    print(f"Concurrency: {concurrency}")
    print(f"Model: {model}")

    # Generate all images in parallel
    start_time = time.time()
    results = await generate_batch_async(client, all_tasks, model, concurrency)
    total_time = time.time() - start_time

    # Organize results by category
    for task in all_tasks:
        cat = task.category
        key = task.key.split("/")[1]
        if cat not in all_results:
            all_results[cat] = {}
        all_results[cat][key] = results.get(task.key, False)

    print(f"\n  Total time: {total_time:.1f}s")
    print(f"  Average per image: {total_time/len(all_tasks):.1f}s")

    return all_results


def main():
    parser = argparse.ArgumentParser(
        description="Generate pixel art sprites for Atlas Town using Google Nano Banana Pro"
    )
    parser.add_argument(
        "--category",
        choices=["characters", "buildings", "extra_buildings", "tiles", "icons", "decorations", "vehicles", "all"],
        default="all",
        help="Category of assets to generate",
    )
    parser.add_argument(
        "--asset",
        type=str,
        help="Specific asset key to generate (e.g., 'sarah', 'pizzeria')",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=DEFAULT_MODEL,
        choices=[DEFAULT_MODEL, FAST_MODEL],
        help=f"Model to use (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=DEFAULT_CONCURRENCY,
        help=f"Number of parallel requests (default: {DEFAULT_CONCURRENCY})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).parent.parent.parent.parent / "assets" / "sprites",
        help="Output directory for sprites",
    )
    args = parser.parse_args()

    # Get API key from environment
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        # Try loading from .env file
        env_path = Path(__file__).parent.parent / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith("GOOGLE_API_KEY="):
                    api_key = line.split("=", 1)[1].strip()
                    break

    if not api_key:
        print("Error: GOOGLE_API_KEY not found in environment or .env file")
        print("Set it with: export GOOGLE_API_KEY=your-key")
        print("Get a key at: https://aistudio.google.com/apikey")
        sys.exit(1)

    # Initialize client
    client = genai.Client(api_key=api_key)

    model_name = "Nano Banana Pro" if args.model == DEFAULT_MODEL else "Nano Banana"

    print("=" * 60)
    print("Atlas Town Sprite Generator (Optimized Batch Mode)")
    print(f"Using Google {model_name} ({args.model})")
    print("=" * 60)
    print(f"Output directory: {args.output}")
    print(f"Category: {args.category}")
    print(f"Concurrency: {args.concurrency}")
    if args.asset:
        print(f"Specific asset: {args.asset}")

    # All categories
    categories = {
        "characters": CHARACTER_PROMPTS,
        "buildings": BUILDING_PROMPTS,
        "extra_buildings": EXTRA_BUILDINGS_PROMPTS,
        "tiles": TILE_PROMPTS,
        "decorations": DECORATIONS_PROMPTS,
        "vehicles": VEHICLES_PROMPTS,
        "icons": ICON_PROMPTS,
    }

    # Run async generation
    all_results = asyncio.run(
        run_generation(
            client=client,
            categories=categories,
            output_dir=args.output,
            model=args.model,
            concurrency=args.concurrency,
            specific_category=args.category,
            specific_asset=args.asset,
        )
    )

    # Summary
    print("\n" + "=" * 60)
    print("GENERATION SUMMARY")
    print("=" * 60)

    total_success = 0
    total_failed = 0

    for category, results in all_results.items():
        success = sum(1 for v in results.values() if v)
        failed = sum(1 for v in results.values() if not v)
        total_success += success
        total_failed += failed
        status = "✓" if failed == 0 else "⚠"
        print(f"  {status} {category}: {success} succeeded, {failed} failed")

    print("-" * 60)
    print(f"  Total: {total_success} succeeded, {total_failed} failed")

    if total_failed > 0:
        print("\nNote: Some generations failed. Try:")
        print("  - Reduce concurrency: --concurrency 2")
        print("  - Use faster model: --model gemini-2.5-flash-image")
        print("  - Re-run for failed assets: --asset <name>")

    print("\nTip: Generated images have magenta background (#FF00FF) for easy removal")


if __name__ == "__main__":
    main()
