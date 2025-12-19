"""
crawl_multi_platform.py - Unified Multi-Platform Crawler
Searches Amazon, Noon, and Jumia simultaneously
"""

import os
import pandas as pd
import concurrent.futures
from typing import List, Optional

from crawlir import crawl_amazon_to_csv
from crawl_noon import crawl_noon_to_csv
from crawl_jumia import crawl_jumia_to_csv


def crawl_all_platforms(
    query: str,
    output_path: str = "data/multi_platform_results.csv",
    pages: int = 1,
    max_products_per_platform: int = 10,
    detailed: bool = True,
    platforms: Optional[List[str]] = None,
) -> pd.DataFrame:
    """
    Crawl all three platforms (Amazon, Noon, Jumia) and combine results.
    
    Args:
        query: Search query
        output_path: Path to output CSV file
        pages: Number of pages to crawl per platform
        max_products_per_platform: Max products per platform
        detailed: Whether to fetch detailed product info
        platforms: List of platforms to search (None = all platforms)
    
    Returns:
        Combined DataFrame with all products
    """
    if platforms is None:
        platforms = ["Amazon", "Noon", "Jumia"]
    
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    
    print(f"🔍 Starting multi-platform search for: '{query}'")
    print(f"📦 Platforms: {', '.join(platforms)}")
    
    def crawl_amazon():
        """Crawl Amazon."""
        if "Amazon" not in platforms:
            return []
        try:
            csv_path = output_path.replace(".csv", "_amazon_temp.csv")
            crawl_amazon_to_csv(
                query=query,
                output_path=csv_path,
                pages=pages,
                detailed=detailed,
                max_products=max_products_per_platform,
                append=False,
            )
            if os.path.exists(csv_path):
                df = pd.read_csv(csv_path)
                os.remove(csv_path)  # Clean up temp file
                return df.to_dict("records")
        except Exception as e:
            print(f"⚠️ Amazon crawl error: {e}")
        return []
    
    def crawl_noon():
        """Crawl Noon."""
        if "Noon" not in platforms:
            return []
        try:
            csv_path = output_path.replace(".csv", "_noon_temp.csv")
            crawl_noon_to_csv(
                query=query,
                output_path=csv_path,
                pages=pages,
                detailed=detailed,
                max_products=max_products_per_platform,
                append=False,
            )
            if os.path.exists(csv_path):
                df = pd.read_csv(csv_path)
                os.remove(csv_path)  # Clean up temp file
                return df.to_dict("records")
        except Exception as e:
            print(f"⚠️ Noon crawl error: {e}")
        return []
    
    def crawl_jumia():
        """Crawl Jumia."""
        if "Jumia" not in platforms:
            return []
        try:
            csv_path = output_path.replace(".csv", "_jumia_temp.csv")
            crawl_jumia_to_csv(
                query=query,
                output_path=csv_path,
                pages=pages,
                detailed=detailed,
                max_products=max_products_per_platform,
                append=False,
            )
            if os.path.exists(csv_path):
                df = pd.read_csv(csv_path)
                os.remove(csv_path)  # Clean up temp file
                return df.to_dict("records")
        except Exception as e:
            print(f"⚠️ Jumia crawl error: {e}")
        return []
    
    # Crawl all platforms concurrently
    all_results = []
    
    print("🚀 Starting concurrent crawl of all platforms...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(crawl_amazon): "Amazon",
            executor.submit(crawl_noon): "Noon",
            executor.submit(crawl_jumia): "Jumia",
        }
        
        for future in concurrent.futures.as_completed(futures):
            platform = futures[future]
            try:
                results = future.result()
                if results:
                    all_results.extend(results)
                    print(f"✅ {platform}: {len(results)} products collected")
                else:
                    print(f"⚠️ {platform}: No products collected")
            except Exception as e:
                print(f"❌ {platform} crawl failed: {e}")
    
    # Combine results into DataFrame
    if all_results:
        df = pd.DataFrame(all_results)
        
        # Ensure consistent column names
        column_mapping = {
            "title": "title",
            "price": "price",
            "rating": "rating",
            "image": "image",
            "product_link": "product_link",
            "description": "description",
            "search_query": "search_query",
            "website": "website",
        }
        
        # Rename columns if needed
        for old_col, new_col in column_mapping.items():
            if old_col in df.columns and old_col != new_col:
                df = df.rename(columns={old_col: new_col})
        
        # Ensure website column exists
        if "website" not in df.columns:
            df["website"] = "Unknown"
        
        # Save to CSV
        df.to_csv(output_path, index=False, encoding="utf-8-sig")
        print(f"💾 Saved {len(df)} total products to {output_path}")
        
        return df
    else:
        print("⚠️ No products collected from any platform")
        return pd.DataFrame()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Search multiple e-commerce platforms")
    parser.add_argument("--query", "-q", type=str, required=True, help="Product search query")
    parser.add_argument("--pages", "-p", type=int, default=1, help="Number of pages per platform")
    parser.add_argument("--max-products", type=int, default=10, help="Max products per platform")
    parser.add_argument("--output", "-o", type=str, default="data/multi_platform_results.csv", help="Output CSV path")
    parser.add_argument("--detailed", action="store_true", help="Fetch detailed product information")
    parser.add_argument("--platforms", nargs="+", choices=["Amazon", "Noon", "Jumia"], 
                        default=["Amazon", "Noon", "Jumia"], help="Platforms to search")
    
    args = parser.parse_args()

    crawl_all_platforms(
        query=args.query,
        output_path=args.output,
        pages=args.pages,
        max_products_per_platform=args.max_products,
        detailed=args.detailed,
        platforms=args.platforms,
    )

