import io
from PIL import Image

# Supported Quest Colors with friendly metadata and HSV ranges
# Note: Pillow HSV maps Hue 0..360° to 0..255 (h_val = degree * 255 / 360)
def deg(deg_val: float) -> int:
    return int((deg_val % 360.0) * 255.0 / 360.0)

COLOR_DEFINITIONS = {
    "red": {
        "name": "Ruby Red",
        "emoji": "🔴",
        "search_term": "red aesthetic",
        # Red wraps around 0/360 degrees: (345..360 and 0..15)
        "hsv_ranges": [
            {"h_min": deg(345), "h_max": 255, "s_min": 45, "v_min": 40},
            {"h_min": 0, "h_max": deg(15), "s_min": 45, "v_min": 40},
        ],
    },
    "green": {
        "name": "Emerald Green",
        "emoji": "🟢",
        "search_term": "green foliage nature",
        "hsv_ranges": [
            {"h_min": deg(75), "h_max": deg(165), "s_min": 40, "v_min": 35},
        ],
    },
    "blue": {
        "name": "Ocean Blue",
        "emoji": "🔵",
        "search_term": "blue sky water ocean",
        "hsv_ranges": [
            {"h_min": deg(185), "h_max": deg(255), "s_min": 40, "v_min": 35},
        ],
    },
    "yellow": {
        "name": "Golden Yellow",
        "emoji": "🟡",
        "search_term": "yellow sunflowers warmth",
        "hsv_ranges": [
            {"h_min": deg(38), "h_max": deg(72), "s_min": 45, "v_min": 50},
        ],
    },
    "orange": {
        "name": "Amber Orange",
        "emoji": "🟠",
        "search_term": "orange autumn sunset",
        "hsv_ranges": [
            {"h_min": deg(16), "h_max": deg(37), "s_min": 50, "v_min": 45},
        ],
    },
    "purple": {
        "name": "Electric Purple",
        "emoji": "🟣",
        "search_term": "purple flowers neon violet",
        "hsv_ranges": [
            {"h_min": deg(260), "h_max": deg(315), "s_min": 35, "v_min": 35},
        ],
    },
    "pink": {
        "name": "Pastel Pink",
        "emoji": "🌸",
        "search_term": "pink blossom pastel",
        "hsv_ranges": [
            {"h_min": deg(316), "h_max": deg(344), "s_min": 35, "v_min": 50},
        ],
    },
}

def analyze_pixel_fraction(image_bytes: bytes, target_color_key: str) -> dict:
    """
    Analyzes what percentage of the image matches the target color in HSV space.
    Returns:
    {
        "percentage": float (0.0 to 100.0),
        "target_color": str,
        "emoji": str,
        "total_pixels": int,
        "matched_pixels": int,
    }
    """
    color_info = COLOR_DEFINITIONS.get(target_color_key.lower())
    if not color_info:
        raise ValueError(f"Unknown target color: {target_color_key}")

    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    # Resize down to at most 400x400 for rapid and consistent processing
    img.thumbnail((400, 400), Image.Resampling.BILINEAR)
    hsv_img = img.convert("HSV")

    matched_count = 0
    total_pixels = hsv_img.width * hsv_img.height
    ranges = color_info["hsv_ranges"]

    # Use get_flattened_data if available (Pillow 13+), otherwise getdata
    if hasattr(hsv_img, "get_flattened_data"):
        pixel_triplets = hsv_img.get_flattened_data()
    else:
        pixel_triplets = hsv_img.getdata()

    # Iterate through pixels
    for h, s, v in pixel_triplets:
        for r in ranges:
            if r["h_min"] <= h <= r["h_max"] and s >= r["s_min"] and v >= r["v_min"]:
                matched_count += 1
                break

    percentage = round((matched_count / total_pixels) * 100.0, 1) if total_pixels > 0 else 0.0

    return {
        "percentage": percentage,
        "target_color": color_info["name"],
        "emoji": color_info["emoji"],
        "total_pixels": total_pixels,
        "matched_pixels": matched_count,
    }


def compute_dhash(image_bytes: bytes, hash_size: int = 8) -> str:
    """
    Computes a 64-bit difference hash (dHash) for perceptual similarity comparison.
    """
    img = Image.open(io.BytesIO(image_bytes)).convert("L")
    # Resize to (hash_size + 1, hash_size)
    img = img.resize((hash_size + 1, hash_size), Image.Resampling.LANCZOS)
    if hasattr(img, "get_flattened_data"):
        pixels = list(img.get_flattened_data())
    else:
        pixels = list(img.getdata())

    # Compare adjacent pixels row by row
    diff = []
    width = hash_size + 1
    for row in range(hash_size):
        row_offset = row * width
        for col in range(hash_size):
            p1 = pixels[row_offset + col]
            p2 = pixels[row_offset + col + 1]
            diff.append("1" if p1 > p2 else "0")

    return "".join(diff)


def compute_similarity(hash1: str, hash2: str) -> float:
    """
    Computes similarity percentage between two 64-bit binary hashes (0.0 to 1.0).
    """
    if not hash1 or not hash2 or len(hash1) != len(hash2):
        return 0.0
    matches = sum(1 for a, b in zip(hash1, hash2) if a == b)
    return round(matches / len(hash1), 3)
