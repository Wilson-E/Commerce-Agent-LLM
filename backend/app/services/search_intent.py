"""Keyword-based search query classifier for category-aware API routing.

Classifies a search query into one of three categories (Tech, Fashion, Home)
and returns the list of API sources to query for that category.  When a
category_hint is provided (e.g. from the frontend tab), it is trusted
directly.  Otherwise, keyword matching determines the category.

No external calls — purely in-process token matching, so it adds zero
latency to a search request.
"""
import re
from typing import Dict, List, Optional

# ── Category keyword sets ────────────────────────────────────────────────────

TECH_TERMS: frozenset = frozenset({
    "laptop", "laptops", "notebook", "ultrabook",
    "tv", "television", "televisions", "monitor", "monitors", "display",
    "phone", "phones", "smartphone", "smartphones", "iphone", "android",
    "headphone", "headphones", "earphone", "earphones", "earbuds", "airpods",
    "gaming", "console", "playstation", "xbox", "nintendo", "gpu", "graphics",
    "camera", "cameras", "dslr", "mirrorless", "webcam",
    "tablet", "tablets", "ipad",
    "speaker", "speakers", "soundbar", "subwoofer",
    "router", "modem", "networking", "wifi",
    "printer", "printers", "scanner",
    "keyboard", "mouse", "trackpad", "mousepad",
    "charger", "battery", "powerbank", "cable", "adapter",
    "smartwatch", "fitness tracker", "wearable",
    "drone", "projector", "hard drive", "ssd", "memory", "ram",
    "cpu", "processor", "motherboard", "desktop", "pc",
    "computer", "macbook", "chromebook", "dell", "lenovo", "asus",
    "samsung", "sony", "bose", "jbl",
})

FASHION_TERMS: frozenset = frozenset({
    "dress", "dresses", "shirt", "shirts", "blouse", "blouses",
    "jacket", "jackets", "coat", "coats", "hoodie", "hoodies", "sweater", "sweaters",
    "jeans", "pants", "trousers", "shorts", "skirt", "skirts", "leggings",
    "sneakers", "shoes", "boots", "sandals", "heels", "loafers", "flats",
    "handbag", "purse", "wallet", "backpack", "tote",
    "hat", "hats", "cap", "beanie", "scarf", "scarves", "gloves",
    "jewelry", "necklace", "bracelet", "earrings", "ring", "watch",
    "sunglasses", "glasses", "belt", "belts",
    "outfit", "clothing", "apparel", "fashion", "style", "wear",
    "activewear", "sportswear", "athleisure", "swimwear", "lingerie",
    "nike", "adidas", "zara", "gucci", "prada", "levi",
    "t-shirt", "tshirt", "polo", "cardigan", "vest", "blazer",
    "underwear", "socks", "tie", "suit",
})

HOME_TERMS: frozenset = frozenset({
    "furniture", "couch", "sofa", "table", "chair", "chairs", "desk",
    "lamp", "lamps", "lighting", "chandelier",
    "rug", "rugs", "carpet", "curtain", "curtains", "blinds",
    "mattress", "bed", "beds", "bedding", "pillow", "pillows", "sheets", "comforter",
    "shelf", "shelves", "bookcase", "cabinet", "dresser", "nightstand",
    "decor", "decoration", "wall art", "vase", "candle", "candles",
    "kitchen", "cookware", "pots", "pans", "utensils", "knife", "knives",
    "bathroom", "towel", "towels", "shower", "faucet",
    "garden", "patio", "outdoor", "grill", "planter",
    "appliance", "appliances", "refrigerator", "washer", "dryer", "dishwasher",
    "microwave", "blender", "toaster", "vacuum", "air conditioner",
    "storage", "organizer", "basket", "bin",
    "paint", "hardware", "tools", "drill", "hammer",
    "home improvement", "renovation",
})

FOOD_TERMS: frozenset = frozenset({
    "food", "foods",
    "snack", "snacks",
    "drink", "drinks", "beverage", "beverages",
    "grocery", "groceries",
    "recipe", "recipes", "ingredient", "ingredients",
    "nutrition", "nutritional", "nutrient", "nutrients",
    "organic", "natural", "whole foods",
    "vegan", "vegetarian", "gluten free", "gluten-free", "dairy free",
    "calories", "calorie", "protein", "carbs", "fat", "fiber",
    "cereal", "bread", "pasta", "rice", "flour",
    "coffee", "tea", "juice", "soda", "water",
    "chocolate", "candy", "cookie", "cookies", "cake",
    "sauce", "condiment", "spice", "seasoning",
    "meat", "chicken", "beef", "fish", "seafood",
    "fruit", "vegetable", "vegetables", "produce",
    "dairy", "milk", "cheese", "yogurt", "butter",
    "supplement", "vitamins", "protein powder",
    "frozen meal", "canned", "packaged",
})

# ── Category → API source routing table ──────────────────────────────────────

CATEGORY_API_MAP: Dict[str, List[str]] = {
    "tech":    ["serpapi", "scraperapi", "rainforest"],
    "fashion": ["serpapi", "asos"],
    "home":    ["serpapi", "homedepot"],
}


def _tokenize(query: str) -> List[str]:
    """Lowercase and split query into word tokens."""
    return re.sub(r"[^\w\s]", " ", query.lower()).split()


def classify_search_intent(
    query: str,
    category_hint: Optional[str] = None,
) -> Dict[str, object]:
    """Classify a search query and return category-aware routing instructions.

    Returns a dict with:
      - "category": "tech" | "fashion" | "home"
      - "sources": list of API source names to query

    When *category_hint* is provided (from the frontend tab selection),
    it is trusted directly.  Otherwise keyword matching determines the
    category.  Default fallback is "tech" (broadest API coverage).
    """
    # If the frontend told us which tab the user is on, trust it
    if category_hint and category_hint.lower() in CATEGORY_API_MAP:
        category = category_hint.lower()
        sources = list(CATEGORY_API_MAP[category])

        # Sub-routing: food queries within Home also get openfoodfacts
        if category == "home":
            tokens = set(_tokenize(query))
            if tokens & FOOD_TERMS:
                sources.append("openfoodfacts")

        return {"category": category, "sources": sources}

    # No hint — classify by keyword overlap
    tokens = set(_tokenize(query))

    if tokens & FASHION_TERMS:
        category = "fashion"
    elif tokens & HOME_TERMS:
        category = "home"
    elif tokens & TECH_TERMS:
        category = "tech"
    elif tokens & FOOD_TERMS:
        # Food queries route to Home category + openfoodfacts
        return {
            "category": "home",
            "sources": list(CATEGORY_API_MAP["home"]) + ["openfoodfacts"],
        }
    else:
        # Default: tech (broadest coverage via Amazon APIs)
        category = "tech"

    return {
        "category": category,
        "sources": list(CATEGORY_API_MAP[category]),
    }
