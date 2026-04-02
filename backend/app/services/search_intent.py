"""Keyword-based search query classifier for API routing.

Classifies a search query into Tier-1 (always-on general APIs) and a single
Tier-2 specialist API based on keyword overlap.  No external calls — purely
in-process token matching, so it adds zero latency to a search request.
"""
import re
from typing import Dict, List

ELECTRONICS_TERMS: frozenset = frozenset({
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
    "appliance", "appliances", "refrigerator", "washer", "dryer", "dishwasher",
    "microwave", "blender", "toaster", "vacuum", "air conditioner",
    "keyboard", "mouse", "trackpad", "mousepad",
    "charger", "battery", "powerbank", "cable", "adapter",
    "smartwatch", "fitness tracker", "wearable",
    "drone", "projector", "hard drive", "ssd", "memory", "ram",
    "cpu", "processor", "motherboard", "desktop", "pc",
})

HANDMADE_TERMS: frozenset = frozenset({
    "handmade", "handcrafted", "hand made", "hand crafted",
    "vintage", "antique", "retro",
    "custom", "customized", "personalized", "personalised", "engraved",
    "jewelry", "jewellery", "necklace", "bracelet", "earrings", "ring", "rings",
    "craft", "crafts", "crafted",
    "art", "artwork", "painting", "illustration", "print", "prints",
    "gift", "gifts", "gifting",
    "etsy", "handmade shop",
    "knit", "knitted", "crochet", "crocheted", "sewn", "embroidered",
    "pottery", "ceramic", "ceramics", "candle", "candles",
    "woodwork", "wooden", "carved",
    "wedding", "bridal", "boutique", "unique",
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


def _tokenize(query: str) -> List[str]:
    """Lowercase and split query into word tokens."""
    return re.sub(r"[^\w\s]", " ", query.lower()).split()


def classify_search_intent(query: str) -> Dict[str, object]:
    """Classify a search query and return routing instructions.

    Returns a dict with:
      - "tier1": list of always-on general API names (["serpapi", "rapidapi"])
      - "tier2": name of the specialist API to activate for this query

    Tier-2 routing:
      - Any electronics keyword  → "bestbuy"
      - Any handmade/craft keyword → "etsy"
      - Any food/grocery keyword  → "openfoodfacts"
      - No match                  → "walmart" (general retail default)
    """
    tokens = set(_tokenize(query))

    if tokens & ELECTRONICS_TERMS:
        tier2 = "bestbuy"
    elif tokens & HANDMADE_TERMS:
        tier2 = "etsy"
    elif tokens & FOOD_TERMS:
        tier2 = "openfoodfacts"
    else:
        tier2 = "walmart"

    return {
        "tier1": ["serpapi", "rapidapi"],
        "tier2": tier2,
    }
