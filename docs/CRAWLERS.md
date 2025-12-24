# 🕷️ Web Crawlers Documentation

This document describes the web crawlers used to fetch product data from multiple e-commerce platforms.

## Overview

The project includes crawlers for three main platforms:

- **Amazon** (`crawlir.py`)
- **Noon** (`crawl_noon.py`)
- **Jumia** (`crawl_jumia.py`)

All crawlers are orchestrated through a unified interface in `crawl_multi_platform.py`.

## Architecture

### Multi-Platform Crawler (`crawl_multi_platform.py`)

The main entry point that searches all platforms concurrently.

**Function:** `crawl_all_platforms()`

```python
crawl_all_platforms(
    query: str,
    output_path: str = "data/multi_platform_results.csv",
    pages: int = 1,
    max_products_per_platform: int = 10,
    detailed: bool = True,
    platforms: Optional[List[str]] = None,
) -> pd.DataFrame
```

**Parameters:**

- `query`: Search keyword (e.g., "laptop", "phone", "headphones")
- `output_path`: Where to save combined results CSV
- `pages`: Number of pages per platform (default: 1)
- `max_products_per_platform`: Limit products per platform (0 = unlimited)
- `detailed`: Fetch detailed info from product pages (slower but more data)
- `platforms`: List of platforms to search (default: all three)

**Returns:** Pandas DataFrame with combined results

**Example:**

```python
from crawl_multi_platform import crawl_all_platforms

results = crawl_all_platforms(
    query="gaming laptop",
    pages=2,
    max_products_per_platform=20,
    detailed=True
)
print(f"Found {len(results)} products")
```

### Individual Crawlers

#### Noon Crawler (`crawl_noon.py`)

**Function:** `crawl_noon_to_csv()`

```python
crawl_noon_to_csv(
    query: str,
    output_path: str = "noon_products.csv",
    pages: int = 1,
    delay: float = 1.5,
    detailed: bool = False,
    max_products: int = 0,
    concurrency: int = 10,
    append: bool = False,
) -> int
```

**Features:**

- Handles rate limiting with exponential backoff
- Supports concurrent detail fetching (default: 10 workers)
- Extracts: title, price, rating, image, link, search query, website
- Fallback selectors for robust HTML parsing

**Returns:** Number of products collected

#### Amazon Crawler (`crawlir.py`)

Similar interface to Noon crawler but optimized for Amazon's structure.

#### Jumia Crawler (`crawl_jumia.py`)

Similar interface but optimized for Jumia's structure.

## Data Structure

All crawlers output CSV with these columns:

| Column         | Type | Description                          |
| -------------- | ---- | ------------------------------------ |
| `title`        | str  | Product name/title                   |
| `price`        | str  | Price (as string with currency)      |
| `rating`       | str  | Rating (e.g., "4.5/5 stars")         |
| `image`        | str  | Product image URL                    |
| `product_link` | str  | Link to product page                 |
| `description`  | str  | Product description                  |
| `search_query` | str  | Original search query                |
| `website`      | str  | Source website (Amazon, Noon, Jumia) |

## Usage Examples

### Search Single Platform

```bash
python crawl_noon.py --query "samsung phone" --pages 2 --max-products 10
```

### Search All Platforms from Python

```python
from crawl_multi_platform import crawl_all_platforms

df = crawl_all_platforms(
    query="laptop",
    pages=1,
    detailed=False,  # Faster
    platforms=["Amazon", "Noon"]  # Skip Jumia
)

# Results saved to data/multi_platform_results.csv
print(df.head())
```

### Append to Existing CSV

```bash
python crawl_noon.py --query "new search" --output results.csv --append
```

## Features

### Robust Error Handling

- Connection pooling with HTTPAdapter
- Exponential backoff on rate limits (HTTP 429)
- Retry logic (default: 3 retries)
- Timeout handling (15-20 seconds per request)

### Concurrent Requests

- Multi-threading for detail page fetching
- Configurable concurrency level
- Bounded by Executor thread pool

### Flexible Selectors

- Multiple CSS selectors per element
- Fallback strategies for different website layouts
- Data attribute support (`data-testid`, etc.)

### URL Normalization

- Handles relative and absolute URLs
- Protocol-relative URLs (e.g., `//example.com`)
- Base URL joining for consistency

## Performance Notes

- **Single page, basic info:** ~5-15 seconds per platform
- **Single page, detailed info:** ~30-60 seconds per platform (depends on concurrency)
- **Multiple pages:** Scales linearly with page count
- **Delay between requests:** Configurable (default 1.5s for Noon)

## Troubleshooting

### No Products Found

1. Check query syntax (simple keywords work best)
2. Verify internet connection
3. Check if website is accessible manually
4. Try different pages parameter

### HTTP Errors

- **429 (Rate Limited):** Crawler will backoff; try again later
- **503 (Service Unavailable):** Website temporarily down; retry later
- **Timeout:** Increase timeout parameter or reduce concurrency

### Missing Data

- Images or links might be unavailable
- Detailed fetching may extract different data than basic mode
- Website structure changes may require selector updates

## Extending the Crawlers

To add a new platform:

1. Create `crawl_<platform>.py` with structure similar to `crawl_noon.py`
2. Implement `crawl_<platform>_to_csv()` function
3. Add platform function to `crawl_multi_platform.py`
4. Update CSS selectors for platform-specific structure

## Legal & Ethical

- These crawlers respect robots.txt where applicable
- Use appropriate delays between requests
- Identify yourself with User-Agent headers
- Check each website's Terms of Service
- Do not overload servers with excessive requests
- Use collected data responsibly and ethically

---

**Last Updated:** December 24, 2025
