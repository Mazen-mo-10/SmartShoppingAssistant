# crawl_noon.py (FINAL FIX)
# - Correct Noon JSON endpoint: /_svc/catalog/api/v3/u/search/ (returns "hits")
# - Backward-compatible signature with crawl_multi_platform.py and tests (pages, max_products, detailed, append)
# - Query normalization for better recall on Noon
# - FIXED images: ensures correct CDN URL, including required "/p/" prefix for keys like "pnsku/..."
# - Outputs consistent CSV schema:
#   title, price, rating, image, product_link, description, search_query, website

import csv
import os
import re
import time
from typing import Dict, List, Optional
from urllib.parse import urljoin

import requests

BASE_API = "https://www.noon.com/_svc/catalog/api/v3/u/search/"
BASE_SITE = "https://www.noon.com/egypt-en"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": BASE_SITE,
}


def normalize_noon_query(query: str) -> str:
    """
    Noon API usually works better with short, brand-oriented queries.
    Example: "laptop 16gb ram" -> "laptop"
    """
    q = (query or "").lower()
    q = re.sub(r"\b\d+gb\b", "", q)
    q = re.sub(r"\bram\b", "", q)
    q = re.sub(r"\bssd\b", "", q)
    q = re.sub(r"\bhdd\b", "", q)
    q = re.sub(r"\b\d+\b", "", q)
    q = re.sub(r"\s+", " ", q).strip()
    return q


def _safe_get_json(session: requests.Session, params: dict, timeout: int = 15) -> Optional[dict]:
    try:
        r = session.get(BASE_API, headers=HEADERS, params=params, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"❌ Noon API error: {e}")
        return None


def _pick_price(hit: dict) -> str:
    # Noon payload varies; try multiple price representations
    candidates = [
        ("price", "value"),
        ("sale_price", "value"),
        ("offer_price", "value"),
        ("final_price", None),
        ("price", None),
        ("sale_price", None),
        ("offer_price", None),
    ]
    for key, sub in candidates:
        if key not in hit or hit[key] is None:
            continue
        v = hit[key]
        if isinstance(v, dict) and sub:
            vv = v.get(sub)
            if vv is not None:
                return str(vv)
        if not isinstance(v, dict):
            return str(v)
    return ""


def _pick_rating(hit: dict) -> str:
    for k in ["rating", "reviews_average", "avg_rating", "average_rating"]:
        if k in hit and hit[k] is not None:
            return str(hit[k])
    return ""


def _build_noon_image_url(key: str, prefer_size: Optional[int] = None) -> str:
    """
    Noon image keys can look like:
      - "pnsku/N701.../45/_/...jpg"  -> needs: https://f.nooncdn.com/p/pnsku/...
      - "pim/..."                   -> often also under /p/
      - already full URL            -> keep as-is
    """
    key = (key or "").strip()
    if not key:
        return ""

    # already a URL
    if key.startswith("http://") or key.startswith("https://"):
        url = key
    else:
        if key.startswith("/"):
            key = key[1:]

        # CRITICAL: keys like "pnsku/..." should be served under "/p/"
        if key.startswith(("pnsku/", "pim/", "pmd/", "psku/")):
            url = "https://f.nooncdn.com/p/" + key
        else:
            url = "https://f.nooncdn.com/" + key

        # add extension if missing (best-effort)
        if not re.search(r"\.(jpg|jpeg|png|webp)$", url, re.IGNORECASE):
            url += ".jpg"

    # Optional: increase size if key has "/45/_/" etc.
    # if prefer_size and isinstance(prefer_size, int):
    #     url = re.sub(r"/(45|60|80|120|160)/_/", f"/{prefer_size}/_/", url)

    return url


def _pick_image(hit: dict) -> str:
    candidates: List[Optional[str]] = [
        hit.get("image_key"),
        hit.get("imageKey"),
        hit.get("image"),
        hit.get("thumbnail"),
        hit.get("product_image"),
    ]

    images = hit.get("images")
    if isinstance(images, list) and images:
        first = images[0]
        if isinstance(first, dict):
            candidates.append(first.get("key") or first.get("image_key") or first.get("url"))
        elif isinstance(first, str):
            candidates.append(first)
    elif isinstance(images, dict):
        candidates.append(images.get("key") or images.get("image_key") or images.get("url"))

    for c in candidates:
        if isinstance(c, str) and c.strip():
            return _build_noon_image_url(c.strip())

    return ""


def _pick_link(hit: dict) -> str:
    """
    Construct proper Noon product URL with SKU.
    Format: https://www.noon.com/egypt-en/{slug}/{sku}/p/
    """
    # Get SKU (required for proper URL)
    sku = hit.get("sku") or hit.get("SKU") or hit.get("product_sku") or ""
    
    # Get slug/URL
    slug = hit.get("url") or hit.get("product_url") or hit.get("path") or hit.get("slug") or ""
    
    # If it's already a full URL, return it
    if isinstance(slug, str) and (slug.startswith("http://") or slug.startswith("https://")):
        return slug
    
    # If we have both slug and SKU, construct the proper URL
    if slug and sku:
        # Clean the slug
        slug = str(slug).lstrip("/")
        # Construct URL in format: /egypt-en/{slug}/{sku}/p/
        if not slug.startswith("egypt-en/"):
            slug = f"egypt-en/{slug}"
        # Remove /p/ if it already exists in slug
        slug = slug.replace("/p/", "").replace("/p", "")
        # Build final URL
        return f"https://www.noon.com/{slug}/{sku}/p/"
    
    # Fallback: if we only have slug, use old method
    if slug:
        return urljoin(BASE_SITE + "/", str(slug).lstrip("/"))
    
    return ""


def crawl_noon_to_csv(
    query: str,
    output_path: str = "noon_products.csv",
    pages: int = 1,
    delay: float = 1.0,
    detailed: bool = False,     # kept for compatibility (not used)
    max_products: int = 0,
    append: bool = False,
    **kwargs                    # swallow extra args from orchestrator safely
) -> int:
    """
    Noon crawler used by crawl_multi_platform.py.
    Returns number of products collected.
    """

    print(f"🔍 Starting Noon search for: '{query}'")
    print(f"📄 Pages to crawl: {pages}")
    print(f"🎯 Max products: {max_products if max_products > 0 else 'unlimited'}")

    session = requests.Session()
    session.headers.update(HEADERS)

    normalized = normalize_noon_query(query)

    fieldnames = [
        "title", "price", "rating",
        "image", "product_link",
        "description", "search_query", "website"
    ]

    rows: List[Dict] = []
    per_page_limit = 50
    page_number = 1

    while True:
        if pages and page_number > pages:
            break

        got_hits = False
        for q_try in [normalized, query]:  # normalized first, then raw fallback
            params = {
                "q": q_try,
                "page": page_number,
                "limit": per_page_limit,
                "country": "eg",  # best-effort hint
            }

            print(f"📖 Calling Noon API page {page_number} (q='{q_try}')...")
            data = _safe_get_json(session, params=params, timeout=15)
            if not data:
                continue

            hits = data.get("hits") or []
            if not hits:
                continue

            got_hits = True
            for hit in hits:
                title = hit.get("name") or hit.get("title") or ""
                if not title:
                    continue

                rows.append({
                    "title": str(title),
                    "price": _pick_price(hit),
                    "rating": _pick_rating(hit),
                    "image": _pick_image(hit),
                    "product_link": _pick_link(hit),
                    "description": "",      # keep consistent schema
                    "search_query": query,  # preserve original user query
                    "website": "Noon",
                })

                if max_products and len(rows) >= max_products:
                    break

            break  # stop trying the other q_try once we got hits

        if max_products and len(rows) >= max_products:
            print(f"🎯 Reached max-products limit ({max_products})")
            break

        if not got_hits:
            if page_number == 1:
                print("ℹ️ No hits returned from Noon API. Stopping pagination.")
            break

        page_number += 1
        time.sleep(max(0.2, delay))

    if not rows:
        print("⚠️ No products collected")
        return 0

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    mode = "a" if append else "w"
    file_exists = append and os.path.exists(output_path)

    with open(output_path, mode, newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerows(rows)

    print(f"💾 Saved {len(rows)} Noon products to {output_path}")
    return len(rows)