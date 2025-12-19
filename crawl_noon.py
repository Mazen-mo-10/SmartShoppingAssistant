#!/usr/bin/env python3
"""
crawl_noon.py - Noon Egypt Scraper
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
BASE_URL = "https://www.noon.com/egypt-en"


def make_session(user_agent: Optional[str] = None, max_pool_connections: int = 20) -> requests.Session:
    """Create a requests.Session with connection pooling and retry logic."""
    s = requests.Session()
    s.headers.update({
        "User-Agent": user_agent or DEFAULT_USER_AGENT,
        "Accept-Language": "en-US,en;q=0.9",
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


def clean_price_noon(price_str: str) -> float:
    """Clean and convert Noon price to float (in EGP)."""
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
    """Parse Noon search results page and extract product items."""
    soup = BeautifulSoup(html, "html.parser")
    
    # Try multiple selectors for product containers
    items = soup.find_all("div", class_=re.compile(r"productContainer|product-wrapper|productItem"))
    if not items:
        # Try finding product cards by data attributes
        items = soup.find_all("div", {"data-testid": re.compile(r"product|item")})
    if not items:
        # Fallback: look for article or div with product-like structure
        items = soup.select("div[class*='product'], article[class*='product']")
    
    return items


def extract_from_result_item(item) -> Dict[str, str]:
    """Extract basic product info from Noon search result item."""
    data = {
        "title": "",
        "price": "",
        "rating": "",
        "image_url": "",
        "product_link": "",
    }

    # Title - try multiple selectors
    title_selectors = [
        "h3", "h2", "a[data-testid='product-title']", 
        ".productTitle", "[class*='title']", "div[class*='name']"
    ]
    for selector in title_selectors:
        title_tag = item.select_one(selector)
        if title_tag:
            data["title"] = _clean_text(title_tag.get_text(" ", strip=True))
            if data["title"]:
                break

    # Price - try multiple selectors
    price_selectors = [
        "[data-testid='price']", ".price", "[class*='price']",
        "span[class*='currency']", ".amount"
    ]
    for selector in price_selectors:
        price_tag = item.select_one(selector)
        if price_tag:
            price_text = _clean_text(price_tag.get_text())
            if price_text:
                data["price"] = price_text
                break

    # Rating - try multiple selectors
    rating_selectors = [
        "[data-testid='rating']", ".rating", "[class*='rating']",
        "[class*='star']", ".reviews"
    ]
    for selector in rating_selectors:
        rating_tag = item.select_one(selector)
        if rating_tag:
            rating_text = _clean_text(rating_tag.get_text())
            if rating_text:
                data["rating"] = rating_text
                break

    # Image - try multiple selectors and attributes
    img_selectors = [
        "img[data-testid='product-image']", "img.productImage", 
        "img[class*='image']", "img", "picture img"
    ]
    for selector in img_selectors:
        img = item.select_one(selector)
        if img:
            # Try multiple image attributes
            img_url = (img.get("src") or 
                      img.get("data-src") or 
                      img.get("data-lazy-src") or
                      img.get("data-original") or "")
            
            if img_url:
                # Ensure full URL
                if img_url.startswith("//"):
                    img_url = "https:" + img_url
                elif img_url.startswith("/"):
                    img_url = urljoin(BASE_URL, img_url)
                data["image_url"] = img_url
                break

    # Product link
    link_selectors = [
        "a[data-testid='product-link']", "a.productLink", 
        "a[href*='/p/']", "a[href*='product']", "a"
    ]
    for selector in link_selectors:
        link = item.select_one(selector)
        if link and link.get("href"):
            href = link.get("href")
            if href:
                if href.startswith("/"):
                    data["product_link"] = urljoin(BASE_URL, href)
                elif href.startswith("http"):
                    data["product_link"] = href
                else:
                    data["product_link"] = urljoin(BASE_URL, "/" + href)
                if data["product_link"]:
                    break

    return data


def extract_from_product_page(html: str) -> Dict[str, str]:
    """Extract detailed information from Noon product page."""
    soup = BeautifulSoup(html, "html.parser")
    
    data = {
        "title_full": "",
        "price_full": "",
        "rating_full": "",
        "description": "",
        "image_primary": "",
    }

    # Title
    title_elem = soup.select_one("h1, [data-testid='product-title'], .productTitle")
    if title_elem:
        data["title_full"] = _clean_text(title_elem.get_text())

    # Price
    price_elem = soup.select_one("[data-testid='price'], .price, [class*='price']")
    if price_elem:
        data["price_full"] = _clean_text(price_elem.get_text())

    # Rating
    rating_elem = soup.select_one("[data-testid='rating'], .rating, [class*='rating']")
    if rating_elem:
        data["rating_full"] = _clean_text(rating_elem.get_text())

    # Description
    desc_elem = soup.select_one("[data-testid='description'], .description, [class*='description']")
    if desc_elem:
        data["description"] = _clean_text(desc_elem.get_text())

    # Primary image - try multiple selectors
    img_selectors = [
        "img[data-testid='main-image']", "img.mainImage", 
        "img.productImage", ".product-image img", "picture img"
    ]
    for selector in img_selectors:
        img = soup.select_one(selector)
        if img:
            img_url = (img.get("src") or 
                      img.get("data-src") or 
                      img.get("data-lazy-src") or
                      img.get("data-original") or "")
            if img_url:
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


def crawl_noon_to_csv(
    query: str,
    output_path: str = "noon_products.csv",
    pages: int = 1,
    delay: float = 1.5,
    detailed: bool = False,
    max_products: int = 0,
    concurrency: int = 10,
    append: bool = False,
) -> int:
    """
    Main crawling function - searches Noon and saves results to CSV.
    
    Returns:
        int: Number of products collected
    """
    if pages < 0:
        raise ValueError("pages must be >= 0")

    print(f"🔍 Starting Noon search for: '{query}'")
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

        search_url = f"{BASE_URL}/search?q={query_quoted}&page={page_number}"
        
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
        
        page_bases = [extract_from_result_item(item) for item in items]

        if detailed:
            print(f"   📥 Fetching details (concurrency={concurrency})...")
            
            def fetch_detail(base_item):
                if not base_item.get("product_link"):
                    return base_item
                
                html = fetch_with_retry(session, base_item["product_link"], timeout=15)
                if html and html.text:
                    details = extract_from_product_page(html.text)
                    base_item["title"] = details.get("title_full") or base_item.get("title", "")
                    base_item["price"] = details.get("price_full") or base_item.get("price", "")
                    base_item["rating"] = details.get("rating_full") or base_item.get("rating", "")
                    base_item["image_url"] = details.get("image_primary") or base_item.get("image_url", "")
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
                            "website": "Noon",
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
                    "website": "Noon",
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
    
    parser = argparse.ArgumentParser(description="Search Noon Egypt and collect product data")
    parser.add_argument("--query", "-q", type=str, required=True, help="Product search query")
    parser.add_argument("--pages", "-p", type=int, default=1, help="Number of pages to fetch")
    parser.add_argument("--output", "-o", type=str, default="noon_products.csv", help="CSV output path")
    parser.add_argument("--detailed", action="store_true", help="Fetch detailed product information")
    parser.add_argument("--max-products", type=int, default=0, help="Maximum products to collect (0 = no limit)")
    parser.add_argument("--append", action="store_true", help="Append to output file")
    
    args = parser.parse_args()

    crawl_noon_to_csv(
        query=args.query,
        output_path=args.output,
        pages=args.pages,
        detailed=args.detailed,
        max_products=args.max_products,
        append=args.append,
    )

