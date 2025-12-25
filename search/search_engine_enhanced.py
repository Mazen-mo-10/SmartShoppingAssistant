import pandas as pd
from typing import Dict, Any, Optional
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


# ==============================
# TF-IDF UTILITIES
# ==============================

def build_tfidf_model(df: pd.DataFrame):
    vectorizer = TfidfVectorizer(
        stop_words="english",
        ngram_range=(1, 2)
    )
    tfidf_matrix = vectorizer.fit_transform(
        df["product_name"].fillna("")
    )
    return vectorizer, tfidf_matrix


def compute_similarity(query: str, vectorizer, tfidf_matrix):
    if not query:
        return [0.0] * tfidf_matrix.shape[0]
    query_vec = vectorizer.transform([query])
    return cosine_similarity(query_vec, tfidf_matrix)[0]


# ==============================
# ACCESSORY FILTER
# ==============================

def is_accessory(product_name: str) -> bool:
    accessory_keywords = [
        "case", "cover", "charger", "cable", "adapter",
        "earphone", "headphone", "screen protector",
        "strap", "band", "holder", "stand", "bag"
    ]
    name = product_name.lower()
    return any(k in name for k in accessory_keywords)


# ==============================
# RULE-BASED SCORING
# ==============================

def calculate_relevance_score(product_row: pd.Series, attrs: Dict[str, Any]) -> float:
    score = 0.0
    name = str(product_row.get("product_name", "")).lower()
    price = product_row.get("price", 0)

    # Brand
    brand = attrs.get("brand")
    if brand and brand.lower() in name:
        score += 30

    # Price
    price_range = attrs.get("price_range", {})
    if price and price_range.get("max") and price <= price_range["max"]:
        score += 20

    # Features
    for f in attrs.get("features", {}).values():
        if str(f).lower() in name:
            score += 5

    # Rating
    rating = product_row.get("rating_numeric", 0)
    if rating:
        score += (rating / 5) * 15

    # Color
    color = attrs.get("color")
    if color and color.lower() in name:
        score += 10

    return round(score, 2)


# ==============================
# MAIN SEARCH FUNCTION
# ==============================

def search_products_enhanced(
    df: pd.DataFrame,
    attrs: Dict[str, Any],
    top_n: int = 10
) -> pd.DataFrame:

    if df.empty:
        return df

    result = df.copy()

    # Rename title if needed
    if "product_name" not in result.columns and "title" in result.columns:
        result.rename(columns={"title": "product_name"}, inplace=True)

    # Remove accessories
    product_type = attrs.get("product")
    if product_type in ["phone", "laptop", "tablet", "watch"]:
        result = result[~result["product_name"].apply(is_accessory)]

    # Hard price filters
    price_range = attrs.get("price_range", {})
    if price_range.get("max"):
        result = result[result["price"] <= price_range["max"]]
    if price_range.get("min"):
        result = result[result["price"] >= price_range["min"]]

    if result.empty:
        return result

    # ==============================
    # RULE-BASED SCORE
    # ==============================
    result["rule_score"] = result.apply(
        lambda row: calculate_relevance_score(row, attrs),
        axis=1
    )

    # ==============================
    # TF-IDF SIMILARITY
    # ==============================
    result = result.reset_index(drop=True)

    vectorizer, tfidf_matrix = build_tfidf_model(df)

    similarity_scores = compute_similarity(
        attrs.get("raw_query", ""),
        vectorizer,
        tfidf_matrix
    )

    # SAFE indexing
    result["tfidf_score"] = result.index.map(
        lambda i: similarity_scores[i] * 100 if i < len(similarity_scores) else 0.0
    )


    # ==============================
    # HYBRID FINAL SCORE
    # ==============================
    result["final_score"] = (
        0.6 * result["rule_score"] +
        0.4 * result["tfidf_score"]
    )

    # Sort
    result = result.sort_values(
        by=["final_score", "price"],
        ascending=[False, True]
    )

    return result.head(top_n)


# ==============================
# BACKWARD COMPATIBILITY
# ==============================

def search_products(
    df: pd.DataFrame,
    attrs: Dict[str, Any],
    top_n: int = 5
) -> pd.DataFrame:
    return search_products_enhanced(df, attrs, top_n)
