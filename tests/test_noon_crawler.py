#!/usr/bin/env python3
"""Quick test of Noon crawler"""

from crawl_noon import crawl_noon_to_csv
import os

# Test with a simple search
query = "laptop"
output = "data/test_noon.csv"

try:
    print(f"Testing Noon crawler with query: '{query}'")
    count = crawl_noon_to_csv(
        query=query,
        output_path=output,
        pages=1,
        max_products=5,
        detailed=False
    )
    print(f"✅ Noon crawler test completed. Collected: {count} products")
    
    if os.path.exists(output):
        with open(output, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            print(f"📄 Output file size: {len(lines)} lines")
            if len(lines) > 1:
                print("✅ Products were saved successfully")
            else:
                print("⚠️ No products were saved (header only)")
except Exception as e:
    print(f"❌ Error testing Noon crawler: {e}")
    import traceback
    traceback.print_exc()
