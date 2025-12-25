#!/usr/bin/env python3
"""
crawl_jumia.py - Jumia Egypt Scraper (FIXED VERSION)
"""

import os
import time
import csv
import re
import json
from typing import Dict, Optional, List
from urllib.parse import urljoin, quote_plus

import requests
from bs4 import BeautifulSoup
import concurrent.futures
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
BASE_URL = "https://www.jumia.com.eg"


def make_session(user_agent: Optional[str] = None, max_pool_connections: int = 20) -> requests.Session:
    """Create a requests.Session with connection pooling and retry logic."""
    s = requests.Session()
    s.headers.update({
        "User-Agent": user_agent or DEFAULT_USER_AGENT,
        "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Connection": "keep-alive",
    })

    retries = Retry(
        total=3,
        backoff_factor=0.3,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=["GET", "POST"]
    )
    
    adapter = HTTPAdapter(
        max_retries=retries,
        pool_connections=max_pool_connections,
        pool_maxsize=max_pool_connections
    )
    
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    
    return s


def fetch_with_retry(
    session: requests.Session,
    url: str,
    max_retries: int = 3,
    timeout: int = 15
) -> Optional[requests.Response]:
    """Fetch URL with exponential backoff on failures."""
    for attempt in range(max_retries):
        try:
            response = session.get(url, timeout=timeout)
            
            if response.status_code == 200:
                return response
            elif response.status_code == 429:
                wait_time = (2 ** attempt) * 2
                print(f"⚠️ Rate limited. Waiting {wait_time}s before retry...")
                time.sleep(wait_time)
            else:
                print(f"⚠️ HTTP {response.status_code} for {url}")
                if attempt == max_retries - 1:
                    return None
                time.sleep(2 ** attempt)
                
        except requests.Timeout:
            print(f"⏱️ Timeout on attempt {attempt + 1} for {url}")
            if attempt == max_retries - 1:
                return None
            time.sleep(2 ** attempt)
            
        except requests.RequestException as e:
            print(f"❌ Request error on attempt {attempt + 1}: {e}")
            if attempt == max_retries - 1:
                return None
            time.sleep(2 ** attempt)
    
    return None


def _clean_text(text: Optional[str]) -> str:
    """Clean and normalize text."""
    if not text:
        return ""
    return " ".join(text.split()).strip()


def clean_price_jumia(price_str: str) -> float:
    """Clean and convert Jumia price to float (in EGP)."""
    if not isinstance(price_str, str):
        price_str = str(price_str)
    
    # Remove currency symbols and text
    price_str = price_str.replace("EGP", "").replace("ج.م", "").replace("جنيه", "")
    price_str = price_str.replace(",", "").replace(" ", "").strip()
    
    # Extract numbers
    match = re.search(r'(\d+\.?\d*)', price_str)
    if match:
        try:
            return float(match.group(1))
        except:
            return 0.0
    return 0.0


def parse_search_results(html: str) -> List:
    """Parse Jumia search results page and extract product items."""
    soup = BeautifulSoup(html, "html.parser")
    
    # Jumia uses article tags for products
    items = soup.find_all("article", class_=re.compile(r"prd|product|card"))
    if not items:
        # Try alternative selectors
        items = soup.find_all("a", {"href": re.compile(r"/product/|/catalog/")})
        # Filter to get parent containers
        items = [item.find_parent("article") or item.find_parent("div") for item in items if item.find_parent("article") or item.find_parent("div")]
        items = [item for item in items if item is not None]
    
    return items


def extract_from_result_item(item, current_url: Optional[str] = None) -> Dict[str, str]:
    """
    Extract basic product info from Jumia search result item.
    
    Args:
        item: BeautifulSoup element containing product info
        current_url: The current page URL (used when on product detail pages)
    """
    data = {
        "title": "",
        "price": "",
        "rating": "",
        "image_url": "",
        "product_link": "",
    }

    # Title - Jumia uses h3 or data-name attribute
    title_selectors = [
        "h3.name", "h2.name", "h3", ".name", 
        "[data-name]", "a.name", ".prd-name"
    ]
    for selector in title_selectors:
        title_tag = item.select_one(selector)
        if title_tag:
            title_text = title_tag.get_text(" ", strip=True) or title_tag.get("data-name", "")
            if title_text:
                data["title"] = _clean_text(title_text)
                break

    # Price - Jumia uses .prc or .price classes
    price_selectors = [
        ".prc", ".price", "[data-price]", 
        ".price-box", ".old", "[class*='price']"
    ]
    for selector in price_selectors:
        price_tag = item.select_one(selector)
        if price_tag:
            price_text = _clean_text(price_tag.get_text())
            if price_text:
                data["price"] = price_text
                break

    # Rating - Jumia uses stars or rating elements
    rating_selectors = [
        ".rev", ".rating", "[data-rating]", 
        "[class*='star']", ".stars"
    ]
    for selector in rating_selectors:
        rating_tag = item.select_one(selector)
        if rating_tag:
            rating_text = _clean_text(rating_tag.get_text())
            if rating_text:
                data["rating"] = rating_text
                break

    # Image - Jumia uses img with data-src or lazy-loaded images
    img_selectors = [
        "img.img", "img", "picture img", 
        "[data-src]", ".img-c"
    ]
    for selector in img_selectors:
        img = item.select_one(selector)
        if img:
            # Jumia often uses data-src for lazy loading
            img_url = (img.get("data-src") or 
                      img.get("src") or 
                      img.get("data-lazy-src") or
                      img.get("data-original") or "")
            
            if img_url:
                # Clean URL (remove size parameters if present)
                if "?raw=true" in img_url or "?" in img_url:
                    img_url = img_url.split("?")[0]
                
                # Ensure full URL
                if img_url.startswith("//"):
                    img_url = "https:" + img_url
                elif img_url.startswith("/"):
                    img_url = urljoin(BASE_URL, img_url)
                data["image_url"] = img_url
                break

    # Product link - FIXED VERSION
    # If current_url is provided and looks like a product page, use it
    if current_url and (".html" in current_url or "/product/" in current_url):
        # This is already a product detail page, use the current URL
        data["product_link"] = current_url
    else:
        # Try multiple selectors to find the product link
        link_selectors = [
            "a.core", 
            "a[href*='/product/']", 
            "a[href*='/catalog/']",
            "a[href*='jumia.com']",
            "a"
        ]
        for selector in link_selectors:
            links = item.select(selector)
            for link in links:
                if link and link.get("href"):
                    href = link.get("href")
                    if href and href.strip():
                        # Accept various Jumia URL patterns
                        valid_patterns = [
                            "/product/",
                            "/catalog/", 
                            "jumia.com",
                            ".html"
                        ]
                        
                        # Check if href matches any valid pattern
                        if any(pattern in href for pattern in valid_patterns):
                            # Ensure full URL
                            if href.startswith("//"):
                                full_url = "https:" + href
                            elif href.startswith("/"):
                                full_url = urljoin(BASE_URL, href)
                            elif href.startswith("http"):
                                full_url = href
                            else:
                                continue
                            
                            # Additional validation: must contain actual product identifier
                            # Jumia product URLs typically contain numbers or dashes
                            if re.search(r'[-\d]', full_url):
                                data["product_link"] = full_url
                                break
            
            if data["product_link"]:
                break

    return data


def extract_from_product_page(html: str, current_url: Optional[str] = None) -> Dict[str, str]:
    """
    Extract detailed information from Jumia product page.
    
    Args:
        html: HTML content of the page
        current_url: The current page URL (to ensure correct link)
    """
    soup = BeautifulSoup(html, "html.parser")
    
    data = {
        "title_full": "",
        "price_full": "",
        "rating_full": "",
        "description": "",
        "image_primary": "",
        "product_link": current_url or "",  # Use current URL as the product link
    }

    # Title
    title_elem = soup.select_one("h1, .name, [data-name]")
    if title_elem:
        data["title_full"] = _clean_text(title_elem.get_text())

    # Price
    price_elem = soup.select_one(".price, .-b, [data-price], .-fs16")
    if price_elem:
        data["price_full"] = _clean_text(price_elem.get_text())

    # Rating
    rating_elem = soup.select_one(".stars, .rating, [data-rating]")
    if rating_elem:
        data["rating_full"] = _clean_text(rating_elem.get_text())

    # Description
    desc_elem = soup.select_one(".markup, .description, [data-description]")
    if desc_elem:
        data["description"] = _clean_text(desc_elem.get_text())

    # Primary image - Jumia uses specific image containers
    img_selectors = [
        "img.-fw", "img[data-src]", ".sldr img", 
        ".images img", "picture img"
    ]
    for selector in img_selectors:
        img = soup.select_one(selector)
        if img:
            img_url = (img.get("data-src") or 
                      img.get("src") or 
                      img.get("data-lazy-src") or "")
            if img_url:
                # Clean URL
                if "?raw=true" in img_url or "?" in img_url:
                    img_url = img_url.split("?")[0]
                
                if img_url.startswith("//"):
                    img_url = "https:" + img_url
                elif img_url.startswith("/"):
                    img_url = urljoin(BASE_URL, img_url)
                data["image_primary"] = img_url
                break

    # Fallback to og:image
    if not data["image_primary"]:
        og_img = soup.select_one("meta[property='og:image']")
        if og_img:
            data["image_primary"] = og_img.get("content", "")

    return data


def crawl_jumia_to_csv(
    query: str,
    output_path: str = "jumia_products.csv",
    pages: int = 1,
    delay: float = 1.5,
    detailed: bool = False,
    max_products: int = 0,
    concurrency: int = 10,
    append: bool = False,
) -> int:
    """
    Main crawling function - searches Jumia and saves results to CSV.
    
    Returns:
        int: Number of products collected
    """
    if pages < 0:
        raise ValueError("pages must be >= 0")

    print(f"🔍 Starting Jumia search for: '{query}'")
    print(f"📄 Pages to crawl: {pages}")
    print(f"🎯 Max products: {max_products if max_products > 0 else 'unlimited'}")
    
    session = make_session(max_pool_connections=max(20, concurrency + 5))
    query_quoted = quote_plus(query)

    collected = []
    page_number = 1
    fetched_products = 0

    while True:
        if pages and page_number > pages:
            break

        search_url = f"{BASE_URL}/catalog/?q={query_quoted}&page={page_number}"
        
        print(f"📖 Fetching page {page_number}...")
        
        response = fetch_with_retry(session, search_url, timeout=20)
        if not response:
            print(f"❌ Failed to fetch page {page_number}. Stopping.")
            break

        items = parse_search_results(response.text)
        if not items:
            print("ℹ️ No more items found. Stopping pagination.")
            break

        print(f"✅ Found {len(items)} items on page {page_number}")
        
        # Pass the current URL to extract_from_result_item (though not needed for search pages)
        page_bases = [extract_from_result_item(item, search_url) for item in items]

        if detailed:
            print(f"   📥 Fetching details (concurrency={concurrency})...")
            
            def fetch_detail(base_item):
                if not base_item.get("product_link"):
                    return base_item
                
                response = fetch_with_retry(session, base_item["product_link"], timeout=15)
                if response and response.text:
                    # Pass the product URL to extract_from_product_page
                    details = extract_from_product_page(response.text, base_item["product_link"])
                    base_item["title"] = details.get("title_full") or base_item.get("title", "")
                    base_item["price"] = details.get("price_full") or base_item.get("price", "")
                    base_item["rating"] = details.get("rating_full") or base_item.get("rating", "")
                    base_item["image_url"] = details.get("image_primary") or base_item.get("image_url", "")
                    # Ensure product_link stays correct
                    base_item["product_link"] = details.get("product_link") or base_item["product_link"]
                return base_item
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
                futures = [executor.submit(fetch_detail, base) for base in page_bases]
                
                for fut in concurrent.futures.as_completed(futures):
                    try:
                        merged = fut.result()
                        collected.append({
                            "title": merged.get("title", ""),
                            "price": merged.get("price", ""),
                            "rating": merged.get("rating", ""),
                            "image": merged.get("image_url", ""),
                            "product_link": merged.get("product_link", ""),
                            "description": "",
                            "search_query": query,
                            "website": "Jumia",
                        })
                        fetched_products += 1
                        
                        if max_products and fetched_products >= max_products:
                            break
                    except Exception as exc:
                        print(f"   ⚠️ Detail fetch error: {exc}")
                
                if max_products and fetched_products >= max_products:
                    break
        else:
            for base in page_bases:
                collected.append({
                    "title": base.get("title", ""),
                    "price": base.get("price", ""),
                    "rating": base.get("rating", ""),
                    "image": base.get("image_url", ""),
                    "product_link": base.get("product_link", ""),
                    "description": "",
                    "search_query": query,
                    "website": "Jumia",
                })
                fetched_products += 1
                
                if max_products and fetched_products >= max_products:
                    break

        if max_products and fetched_products >= max_products:
            print(f"🎯 Reached max-products limit ({max_products})")
            break

        page_number += 1
        time.sleep(delay / 3.0)

    if collected:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        
        fieldnames = [
            "title", "price", "rating",
            "image", "product_link",
            "description", "search_query", "website"
        ]
        
        file_exists = append and os.path.isfile(output_path)
        mode = "a" if append else "w"

        with open(output_path, mode, newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            for row in collected:
                writer.writerow(row)
        
        print(f"💾 Saved {len(collected)} products to {output_path}")
    else:
        print("⚠️ No products collected")

    return len(collected)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Search Jumia Egypt and collect product data")
    parser.add_argument("--query", "-q", type=str, required=True, help="Product search query")
    parser.add_argument("--pages", "-p", type=int, default=1, help="Number of pages to fetch")
    parser.add_argument("--output", "-o", type=str, default="jumia_products.csv", help="CSV output path")
    parser.add_argument("--detailed", action="store_true", help="Fetch detailed product information")
    parser.add_argument("--max-products", type=int, default=0, help="Maximum products to collect (0 = no limit)")
    parser.add_argument("--append", action="store_true", help="Append to output file")
    
    args = parser.parse_args()

    crawl_jumia_to_csv(
        query=args.query,
        output_path=args.output,
        pages=args.pages,
        detailed=args.detailed,
        max_products=args.max_products,
        append=args.append,
    )