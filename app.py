import os
import sys
import time
import re
from datetime import datetime
from typing import Dict, Optional, List

import streamlit as st
import pandas as pd

from crawl_multi_platform import crawl_all_platforms
from nlp.preprocessing import preprocess_text
from nlp.attribute_extraction_enhanced import extract_enhanced_attributes
from nlp.utils import clean_price_egp
from search.search_engine_enhanced import search_products_enhanced

# Import price classifier model
try:
    from models.price_classifier import price_classifier
except ImportError:
    price_classifier = None
    print("⚠️ Price classifier not available yet. Run the notebook first.")

# Ensure project root is in path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# History storage
HISTORY_FILE = os.path.join(BASE_DIR, "data", "search_history.json")
import json

def load_history():
    """Load search history from JSON file."""
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"Error loading history: {e}")
    return []

def save_history(history):
    """Save search history to JSON file."""
    try:
        os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving history: {e}")

# =========================
# Page Configuration
# =========================
st.set_page_config(
    page_title="Smart Shopping Assistant",
    page_icon="🛒",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize session state
if "history" not in st.session_state:
    st.session_state.history = load_history()  # Load from persistent storage
if "language" not in st.session_state:
    st.session_state.language = "en"
if "current_page" not in st.session_state:
    st.session_state.current_page = 0
if "search_results" not in st.session_state:
    st.session_state.search_results = pd.DataFrame()
if "raw_ranked_results" not in st.session_state:
    st.session_state.raw_ranked_results = pd.DataFrame()
if "website_filter" not in st.session_state:
    st.session_state.website_filter = ["Amazon", "Noon", "Jumia"]

# Translations
TRANSLATIONS = {
    "en": {
        "title": "🛒 Smart Shopping Assistant",
        "subtitle": "Enhanced NLP Pipeline → Intelligent Ranking → Multi-Platform Results",
        "search_placeholder": "Describe what you're looking for...",
        "search_button": "🚀 Search Products",
        "filters": "⚙️ Search Filters",
        "website_filter": "🌐 Filter by Website",
        "min_price": "🏷️ Minimum Price (EGP)",
        "max_price": "🏷️ Maximum Price (EGP)",
        "min_rating": "⭐ Minimum Rating",
        "brand_filter": "🔍 Filter by Brand",
        "sorting": "📊 Sorting",
        "sort_by": "Sort by",
        "direction": "Direction",
        "results": "Search Results",
        "found": "Found",
        "products": "products matching your criteria",
        "no_results": "No products match your filters. Try adjusting the filters in the sidebar.",
        "no_products": "No products found. Try different keywords.",
        "history": "🕒 Search History",
        "about": "ℹ️ About",
        "clear_history": "🗑️ Clear History",
    },
    "ar": {
        "title": "🛒 مساعد التسوق الذكي",
        "subtitle": "خط أنابيب معالجة اللغة الطبيعية المحسّن → الترتيب الذكي → نتائج متعددة المنصات",
        "search_placeholder": "اوصف ما تبحث عنه...",
        "search_button": "🚀 البحث عن المنتجات",
        "filters": "⚙️ فلاتر البحث",
        "website_filter": "🌐 فلتر حسب الموقع",
        "max_price": "🏷️ أقصى سعر (جنيه)",
        "min_rating": "⭐ الحد الأدنى للتقييم",
        "brand_filter": "🔍 فلتر حسب العلامة التجارية",
        "sorting": "📊 الترتيب",
        "sort_by": "ترتيب حسب",
        "direction": "الاتجاه",
        "results": "نتائج البحث",
        "found": "تم العثور على",
        "products": "منتج يطابق معاييرك",
        "no_results": "لا توجد منتجات تطابق الفلاتر. حاول تعديل الفلاتر في الشريط الجانبي.",
        "no_products": "لم يتم العثور على منتجات. جرّب كلمات مفتاحية مختلفة.",
        "history": "🕒 تاريخ البحث",
        "about": "ℹ️ حول المشروع",
        "clear_history": "🗑️ مسح السجل",
    }
}

def t(key: str) -> str:
    """Get translation for current language."""
    return TRANSLATIONS.get(st.session_state.language, TRANSLATIONS["en"]).get(key, key)

# =========================
# Helper Functions
# =========================

def safe_get(row: pd.Series, key: str, default=None):
    """Safely get value from row, handling NaN."""
    value = row.get(key, default)
    if pd.isna(value):
        return default
    return value

def safe_str(value) -> str:
    """Safely convert value to string, handling NaN."""
    if pd.isna(value) or value is None:
        return ""
    return str(value)

def apply_ui_filters(
    results: pd.DataFrame,
    sort_by: str,
    sort_dir: str,
    min_price: Optional[float],
    max_price: Optional[float],
    min_rating: Optional[float],
    brand_filter: Optional[str],
    website_filter: List[str]
) -> pd.DataFrame:
    """Apply UI filters and sorting to results DataFrame."""
    df = results.copy()

    # Website filter
    if website_filter and "website" in df.columns:
        df = df[df["website"].isin(website_filter)]

    # Price filter - min and max
    if "price" in df.columns:
        if min_price is not None and min_price > 0:
            df = df[df["price"] >= min_price]
        if max_price is not None and max_price > 0:
            df = df[df["price"] <= max_price]

    # Rating filter
    if min_rating is not None and min_rating > 0 and "rating_numeric" in df.columns:
        df = df[df["rating_numeric"] >= min_rating]

    # Brand filter
    if brand_filter and brand_filter.strip() and "product_name" in df.columns:
        bf = brand_filter.strip().lower()
        df = df[df["product_name"].fillna("").str.lower().str.contains(bf, na=False)]

    # Sorting
    if sort_by and sort_by in df.columns:
        ascending = (sort_dir == "Ascending" or sort_dir == "تصاعدي")
        df = df.sort_values(by=sort_by, ascending=ascending)

    return df

def clean_price_column(df: pd.DataFrame) -> pd.DataFrame:
    """Clean and convert price column using unified utility."""
    if "price" not in df.columns:
        return df
    
    df = df.copy()
    df["price"] = df["price"].apply(clean_price_egp)
    df = df.dropna(subset=["price"])
    
    return df

def extract_rating_numeric(rating_str) -> float:
    """Extract numeric rating from string like '4.5 out of 5 stars'."""
    if pd.isna(rating_str):
        return 0.0
    if not isinstance(rating_str, str):
        try:
            return float(rating_str)
        except:
            return 0.0
    
    match = re.search(r'(\d+\.?\d*)', str(rating_str))
    if match:
        try:
            val = float(match.group(1))
            return min(5.0, max(0.0, val))  # Clamp between 0 and 5
        except:
            return 0.0
    return 0.0

def format_price_display(price) -> str:
    """Format price for display with proper separators."""
    if pd.isna(price):
        return "N/A"
    
    try:
        price_float = float(price)
        price_str = f"{price_float:,.2f}"
        return f"{price_str} EGP"
    except:
        return "N/A"

def is_valid_image_url(url) -> bool:
    """Check if URL is a valid image URL."""
    if pd.isna(url) or not url:
        return False
    url_str = str(url).strip()
    if not url_str or url_str == "nan":
        return False
    
    if not (url_str.startswith("http://") or url_str.startswith("https://")):
        return False
    
    return True

def render_product_card_enhanced(row: pd.Series, show_relevance: bool = True):
    """Enhanced product card with better styling, relevance score, and website indicator."""
    name = safe_str(safe_get(row, "product_name", "Unknown product"))
    price = safe_get(row, "price", 0)
    rating = safe_get(row, "rating", "-")
    rating_numeric = safe_get(row, "rating_numeric", 0)
    link = safe_str(safe_get(row, "link", "#"))
    img = safe_str(safe_get(row, "image_url", ""))
    relevance = safe_get(row, "relevance_score", 0)
    website = safe_str(safe_get(row, "website", "Unknown"))

    # Website colors and labels
    website_info = {
        "Amazon": {"color": "#FF9900", "label": "Amazon", "icon": "📦"},
        "Noon": {"color": "#E6C912", "label": "Noon", "icon": "🌙"},
        "Jumia": {"color": "#0EE520", "label": "Jumia", "icon": "🛒"},
    }
    
    site_info = website_info.get(website, {"color": "#666666", "label": website, "icon": "🛍"})

    # Product card with modern styling
    st.markdown(f"""
    <style>
    .product-card {{
        background: linear-gradient(135deg, {current_theme['primary_color']} 0%, {current_theme['secondary_color']} 100%);
        border-radius: 16px;
        padding: 20px;
        margin: 15px 0;
        box-shadow: 0 8px 16px rgba(0,0,0,0.1);
        transition: transform 0.3s ease, box-shadow 0.3s ease;
    }}
    .product-card:hover {{
        transform: translateY(-5px);
        box-shadow: 0 12px 24px rgba(0,0,0,0.15);
    }}
    </style>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns([1, 2.5])

    with col1:
        # Improved image display with error handling
        if img and is_valid_image_url(img):
            try:
                st.image(img, width='content')
            except:
                st.markdown(
                    f'<div style="width:280px;height:280px;border-radius:12px;'
                    f'background:linear-gradient(135deg,{current_theme["primary_color"]}33,{current_theme["secondary_color"]}33);'
                    f'display:flex;align-items:center;justify-content:center;font-size:48px;">'
                    f'{site_info["icon"]}</div>',
                    unsafe_allow_html=True
                )
        else:
            st.markdown(
                f'<div style="width:280px;height:280px;border-radius:12px;'
                f'background:linear-gradient(135deg,#667eea33,#764ba233);'
                f'display:flex;align-items:center;justify-content:center;font-size:48px;">'
                f'{site_info["icon"]}</div>',
                unsafe_allow_html=True
            )

    with col2:
        # Website badge
        st.markdown(
            f'<span style="background:{site_info["color"]};color:{current_theme["text_color"]};'
            f'padding:8px 16px;border-radius:12px;font-size:14px;font-weight:700;'
            f'box-shadow: 0 2px 8px rgba(0,0,0,0.2);">{site_info["icon"]} {site_info["label"]}</span>',
            unsafe_allow_html=True
        )
        
        # Relevance badge
        if show_relevance and relevance > 0:
            relevance_color = "#00D09C" if relevance >= 50 else "#FFA500" if relevance >= 30 else "#FF6B6B"
            st.markdown(
                f'<span style="background:{relevance_color};color:{current_theme["text_color"]};'
                f'padding:6px 12px;border-radius:8px;font-size:12px;font-weight:600;margin-left:10px;">'
                f'Match: {relevance:.0f}%</span>',
                unsafe_allow_html=True
            )

        st.markdown(f"#### {name[:100]}{'...' if len(name) > 100 else ''}")
        
        # Price with formatting + Price Classification Badge
        price_display = format_price_display(price)
        
        # Get price classification from model
        price_badge = ""
        if price_classifier and price_classifier.loaded:
            try:
                result = price_classifier.predict(name, "", price)
                if result:
                    # Pass current language to badge generator
                    current_lang = st.session_state.get('language', 'ar')
                    price_badge = price_classifier.get_badge_markdown(result, language=current_lang)
                    st.markdown(f"### 💰 {price_display} {price_badge}")
                else:
                    st.markdown(f"### 💰 {price_display}")
            except Exception as e:
                st.markdown(f"### 💰 {price_display}")
        else:
            st.markdown(f"### 💰 {price_display}")
        
        # Rating with stars - improved styling without borders
        if rating_numeric and rating_numeric > 0:
            stars = "⭐" * min(5, int(rating_numeric))
            st.markdown(f"{stars} **{rating_numeric:.1f}/5.0**")
        elif rating and str(rating) != "-" and str(rating) != "nan":
            st.markdown(f"⭐ {rating}")
        
        # Link button with website-specific text - works for all platforms
        if link and str(link).strip() and link != "#" and str(link).lower() != "nan":
            # Clean up the link
            link_str = str(link).strip()
            
            # If link doesn't start with http, try to add it
            if not link_str.startswith(("http://", "https://")):
                link_str = "https://" + link_str if link_str else "#"
            
            # Only show button if we have a valid link
            if link_str.startswith(("http://", "https://")) and link_str != "https://#":
                button_text = f"🛒 View on {site_info['label']}"
                try:
                    st.link_button(button_text, link_str, width='stretch', type="primary")
                except Exception as e:
                    # Fallback to markdown link if button fails
                    st.markdown(
                        f'<a href="{link_str}" target="_blank" style="display:inline-block;padding:10px 20px;background:{current_theme["primary_color"]};color:white;text-decoration:none;border-radius:8px;font-weight:600;width:100%;text-align:center;box-sizing:border-box;">{button_text}</a>',
                        unsafe_allow_html=True
                    )

# =========================
# Theme Configuration (Dark Theme)
# =========================

current_theme = {
    "primary_gradient": "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
    "primary_color": "#667eea",
    "secondary_color": "#764ba2",
    "background": "#0f0f1e",
    "sidebar_bg": "linear-gradient(180deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%)",
    "text_color": "white",
    "text_muted": "rgba(255,255,255,0.7)",
    "card_bg": "#1a1a2e",
    "border_color": "rgba(102,126,234,0.3)",
}

# =========================
# Custom CSS for Modern Design
# =========================

css_styles = f"""
<style>
    * {{
        margin: 0;
        padding: 0;
        box-sizing: border-box;
    }}
    
    html, body {{
        background: {current_theme['background']} !important;
        color: {current_theme['text_color']} !important;
    }}
    
    .stApp {{
        background: {current_theme['background']} !important;
    }}
    
    [data-testid="stAppViewContainer"] {{
        background: {current_theme['background']} !important;
    }}
    
    /* Root variables for theme */
    :root {{
        --primary-gradient: {current_theme['primary_gradient']};
        --primary-color: {current_theme['primary_color']};
        --secondary-color: {current_theme['secondary_color']};
        --background: {current_theme['background']};
        --text-color: {current_theme['text_color']};
        --text-muted: {current_theme['text_muted']};
        --card-bg: {current_theme['card_bg']};
        --border-color: {current_theme['border_color']};
    }}
    
    /* Main styling */
    .main {{
        padding-top: 2rem;
        background: {current_theme['background']};
    }}
    
    body {{
        background: {current_theme['background']};
        color: {current_theme['text_color']};
    }}
    
    /* Language toggle button */
    .top-controls {{
        position: fixed;
        top: 20px;
        right: 20px;
        z-index: 1000;
        display: flex;
        gap: 10px;
    }}

    /* Ensure main content uses theme text color */

    [data-testid="stAppViewContainer"] .block-container,
    [data-testid="stAppViewContainer"] .main,
    [data-testid="stAppViewContainer"] .stMarkdown {{
        color: {current_theme['text_color']} !important;
    }}
    
    /* Header styling */
    .main-header {{
        background: linear-gradient(135deg, {current_theme['primary_color']} 0%, {current_theme['secondary_color']} 100%);
        padding: 40px;
        border-radius: 20px;
        color: white;
        text-align: center;
        margin-bottom: 30px;
        box-shadow: 0 12px 24px rgba(0,0,0,0.15);
        animation: slideDown 0.6s ease;
        position: relative;
    }}
    
    @keyframes slideDown {{
        from {{
            opacity: 0;
            transform: translateY(-20px);
        }}
        to {{
            opacity: 1;
            transform: translateY(0);
        }}
    }}
    
    .main-header h1 {{
        font-size: 48px;
        font-weight: 700;
        margin-bottom: 10px;
        text-shadow: 2px 2px 4px rgba(0,0,0,0.2);
    }}
    
    .main-header p {{
        font-size: 18px;
        opacity: 0.95;
    }}
    
    /* Search bar styling */
    .stTextArea textarea {{
        border-radius: 12px !important;
        border: 2px solid {current_theme['primary_color']} !important;
        padding: 15px !important;
        font-size: 16px !important;
        background: {current_theme['card_bg']} !important;
        color: {current_theme['text_color']} !important;
    }}
    
    .stTextArea textarea::placeholder {{
        color: {current_theme['text_muted']} !important;
    }}
    
    /* Button styling */
    .stButton > button {{
        background: linear-gradient(135deg, {current_theme['primary_color']} 0%, {current_theme['secondary_color']} 100%) !important;
        color: white !important;
        border: none !important;
        border-radius: 12px !important;
        padding: 12px 24px !important;
        font-weight: 600 !important;
        font-size: 16px !important;
        transition: all 0.3s ease !important;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15) !important;
    }}
    
    .stButton > button:hover {{
        transform: translateY(-2px) !important;
        box-shadow: 0 6px 16px rgba(0,0,0,0.2) !important;
    }}
    
    /* Sidebar styling */
    [data-testid="stSidebar"] {{
        background: {current_theme['sidebar_bg']} !important;
        color: {current_theme['text_color']} !important;
    }}
    
    [data-testid="stSidebar"] * {{
        color: {current_theme['text_color']} !important;
    }}
    
    /* Sidebar header styling */
    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3,
    [data-testid="stSidebar"] h4 {{
        color: {current_theme['text_color']} !important;
        text-shadow: 0 2px 4px rgba(0,0,0,0.3);
    }}
    
    /* Sidebar section dividers */
    [data-testid="stSidebar"] hr {{
        border-color: {current_theme['border_color']} !important;
        margin: 20px 0 !important;
    }}
    
    /* Input fields in sidebar */
    [data-testid="stSidebar"] .stNumberInput > div > div > input,
    [data-testid="stSidebar"] .stTextInput > div > div > input {{
        background: rgba(255,255,255,0.1) !important;
        border: 2px solid {current_theme['border_color']} !important;
        border-radius: 10px !important;
        color: {current_theme['text_color']} !important;
        padding: 10px 15px !important;
        transition: all 0.3s ease !important;
    }}
    
    [data-testid="stSidebar"] .stNumberInput > div > div > input:focus,
    [data-testid="stSidebar"] .stTextInput > div > div > input:focus {{
        background: rgba(255,255,255,0.15) !important;
        border-color: {current_theme['primary_color']} !important;
        box-shadow: 0 0 0 3px {current_theme['border_color']} !important;
        outline: none !important;
    }}
    
    [data-testid="stSidebar"] .stNumberInput > div > div > input::placeholder,
    [data-testid="stSidebar"] .stTextInput > div > div > input::placeholder {{
        color: {current_theme['text_muted']} !important;
    }}
    
    /* Number input buttons */
    [data-testid="stSidebar"] button[aria-label*="decrease"],
    [data-testid="stSidebar"] button[aria-label*="increase"] {{
        background: {current_theme['border_color']} !important;
        border: 1px solid {current_theme['border_color']} !important;
        color: {current_theme['text_color']} !important;
        border-radius: 6px !important;
    }}
    
    [data-testid="stSidebar"] button[aria-label*="decrease"]:hover,
    [data-testid="stSidebar"] button[aria-label*="increase"]:hover {{
        background: {current_theme['border_color']} !important;
    }}
    
    /* Slider styling */
    [data-testid="stSidebar"] .stSlider > div > div {{
        background: rgba(255,255,255,0.1) !important;
    }}
    
    [data-testid="stSidebar"] .stSlider > div > div > div {{
        background: var(--primary-gradient) !important;
    }}
    
    [data-testid="stSidebar"] .stSlider > div > div > div > div {{
        background: white !important;
        box-shadow: 0 2px 8px rgba(0,0,0,0.3) !important;
    }}
    
    /* Selectbox/Dropdown styling */
    [data-testid="stSidebar"] .stSelectbox > div > div {{
        background: rgba(255,255,255,0.1) !important;
        border: 2px solid {current_theme['border_color']} !important;
        border-radius: 10px !important;
        color: {current_theme['text_color']} !important;
    }}
    
    [data-testid="stSidebar"] .stSelectbox > div > div:hover {{
        background: rgba(255,255,255,0.15) !important;
        border-color: {current_theme['primary_color']} !important;
    }}
    
    /* Multiselect styling */
    [data-testid="stSidebar"] .stMultiSelect > div > div {{
        background: rgba(255,255,255,0.1) !important;
        border: 2px solid {current_theme['border_color']} !important;
        border-radius: 10px !important;
    }}
    
    [data-testid="stSidebar"] .stMultiSelect > div > div:hover {{
        border-color: {current_theme['primary_color']} !important;
    }}
    
    /* Radio button styling */
    [data-testid="stSidebar"] .stRadio > div {{
        background: rgba(255,255,255,0.05) !important;
        padding: 15px !important;
        border-radius: 12px !important;
        border: 1px solid {current_theme['border_color']} !important;
        margin: 10px 0 !important;
    }}
    
    [data-testid="stSidebar"] .stRadio > div > label {{
        color: {current_theme['text_color']} !important;
    }}
    
    [data-testid="stSidebar"] .stRadio > div > label:hover {{
        color: {current_theme['primary_color']} !important;
    }}
    
    /* Info box styling */
    [data-testid="stSidebar"] .stInfo {{
        background: {current_theme['border_color']} !important;
        border-left: 4px solid {current_theme['primary_color']} !important;
        border-radius: 8px !important;
        padding: 15px !important;
        margin: 15px 0 !important;
    }}
    
    [data-testid="stSidebar"] .stInfo > div {{
        color: {current_theme['text_muted']} !important;
    }}
    
    /* Multiselect tag styling */
    [data-testid="stSidebar"] [data-baseweb="tag"] {{
        background: var(--primary-gradient) !important;
        color: white !important;
        border-radius: 8px !important;
        padding: 6px 12px !important;
        margin: 4px !important;
        font-weight: 600 !important;
        box-shadow: 0 2px 6px rgba(0,0,0,0.2) !important;
    }}
    
    /* Label styling */
    [data-testid="stSidebar"] label {{
        color: {current_theme['text_color']} !important;
        font-weight: 600 !important;
        font-size: 14px !important;
        margin-bottom: 8px !important;
        display: block !important;
    }}
    
    /* Section headers in sidebar */
    [data-testid="stSidebar"] .element-container:has(h3),
    [data-testid="stSidebar"] .element-container:has(h4) {{
        background: {current_theme['border_color']} !important;
        padding: 12px 15px !important;
        border-radius: 10px !important;
        margin: 15px 0 !important;
        border: 1px solid {current_theme['border_color']} !important;
    }}
    
    /* Scrollbar styling for sidebar */
    [data-testid="stSidebar"]::-webkit-scrollbar {{
        width: 8px;
    }}
    
    [data-testid="stSidebar"]::-webkit-scrollbar-track {{
        background: rgba(255,255,255,0.05);
        border-radius: 10px;
    }}
    
    [data-testid="stSidebar"]::-webkit-scrollbar-thumb {{
        background: var(--primary-gradient);
        border-radius: 10px;
    }}
    
    [data-testid="stSidebar"]::-webkit-scrollbar-thumb:hover {{
        background: var(--primary-gradient);
    }}
    
    /* Button styling in sidebar */
    [data-testid="stSidebar"] .stButton > button {{
        background: var(--primary-gradient) !important;
        color: white !important;
        border: none !important;
        border-radius: 10px !important;
        padding: 10px 20px !important;
        font-weight: 600 !important;
        transition: all 0.3s ease !important;
        box-shadow: 0 4px 12px rgba(0,0,0,0.3) !important;
        width: 100% !important;
    }}
    
    [data-testid="stSidebar"] .stButton > button:hover {{
        transform: translateY(-2px) !important;
        box-shadow: 0 6px 16px {current_theme['border_color']} !important;
    }}
    
    /* Markdown text in sidebar */
    [data-testid="stSidebar"] .stMarkdown,
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] div {{
        color: {current_theme['text_muted']} !important;
    }}
    
    [data-testid="stSidebar"] .stMarkdown strong {{
        color: {current_theme['text_color']} !important;
        font-weight: 700 !important;
    }}
    
    /* Code blocks in sidebar */
    [data-testid="stSidebar"] code {{
        background: rgba(0,0,0,0.3) !important;
        color: {current_theme['primary_color']} !important;
        padding: 2px 6px !important;
        border-radius: 4px !important;
    }}
    
    /* Better spacing for sidebar elements */
    [data-testid="stSidebar"] .element-container {{
        margin-bottom: 20px !important;
    }}
    
    /* Dropdown arrow styling */
    [data-testid="stSidebar"] [data-baseweb="select"] svg {{
        fill: {current_theme['text_color']} !important;
    }}
    
    /* Selectbox options styling */
    [data-baseweb="popover"] {{
        background: {current_theme['card_bg']} !important;
        border: 1px solid {current_theme['border_color']} !important;
        border-radius: 10px !important;
    }}
    
    [data-baseweb="popover"] [data-baseweb="menu"] {{
        background: {current_theme['card_bg']} !important;
    }}
    
    [data-baseweb="popover"] [data-baseweb="option"] {{
        color: {current_theme['text_color']} !important;
        background: transparent !important;
    }}
    
    [data-baseweb="popover"] [data-baseweb="option"]:hover {{
        background: {current_theme['border_color']} !important;
    }}
    
    /* Multiselect dropdown items */
    [data-baseweb="popover"] [role="option"] {{
        color: {current_theme['text_color']} !important;
    }}
    
    [data-baseweb="popover"] [role="option"]:hover {{
        background: {current_theme['border_color']} !important;
    }}
    
    /* Tabs styling */
    [data-testid="stTabs"] {{
        background: transparent !important;
    }}
    
    .stTabs [data-baseweb="tab"] {{
        color: {current_theme['text_muted']} !important;
        font-weight: 600 !important;
        padding: 15px 20px !important;
        border-radius: 10px 10px 0 0 !important;
        transition: all 0.3s ease !important;
    }}
    
    .stTabs [data-baseweb="tab"][aria-selected="true"] {{
        color: white !important;
        background: var(--primary-gradient) !important;
        box-shadow: 0 4px 12px {current_theme['border_color']} !important;
    }}
    
    /* Pagination styling */
    .pagination-container {{
        display: flex;
        justify-content: center;
        align-items: center;
        gap: 20px;
        margin: 30px 0;
        padding: 20px;
        background: {current_theme['card_bg']};
        border-radius: 12px;
        border: 1px solid {current_theme['border_color']};
    }}
    
    .pagination-button {{
        background: var(--primary-gradient);
        color: white;
        border: none;
        border-radius: 50%;
        width: 50px;
        height: 50px;
        font-size: 20px;
        cursor: pointer;
        transition: all 0.3s ease;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    }}
    
    .pagination-button:hover:not(:disabled) {{
        transform: scale(1.1);
        box-shadow: 0 6px 16px rgba(0,0,0,0.2);
    }}
    
    .pagination-button:disabled {{
        opacity: 0.5;
        cursor: not-allowed;
    }}
    
    /* History item styling */
    .history-item {{
        background: {current_theme['card_bg']};
        border: 1px solid {current_theme['border_color']};
        border-radius: 12px;
        padding: 15px;
        margin: 10px 0;
        cursor: pointer;
        transition: all 0.3s ease;
    }}
    
    .history-item:hover {{
        transform: translateX(5px);
        box-shadow: 0 4px 12px {current_theme['border_color']};
        border-color: {current_theme['primary_color']};
    }}
    
    /* Animation */
    @keyframes fadeIn {{
        from {{ opacity: 0; transform: translateY(20px); }}
        to {{ opacity: 1; transform: translateY(0); }}
    }}
    
    .fade-in {{
        animation: fadeIn 0.5s ease;
    }}
</style>
"""

st.markdown(css_styles, unsafe_allow_html=True)

# =========================
# Language Toggle Button (Top Right)
# =========================

# Position language button at top right corner
col_space, col_lang = st.columns([21, 1])

with col_lang:
    lang_button_text = "English" if st.session_state.language == "ar" else "Arabic"
    if st.button(lang_button_text, key="lang_toggle", help="Switch Language / تبديل اللغة"):
        st.session_state.language = "ar" if st.session_state.language == "en" else "en"
        st.rerun()

# =========================
# Main Header
# =========================

st.markdown(f"""
<div class="main-header fade-in">
    <h1>{t("title")}</h1>
    <p>{t("subtitle")}</p>
</div>
""", unsafe_allow_html=True)

# =========================
# Sidebar Controls
# =========================

st.sidebar.markdown(f"### {t('filters')}")

# Website filter
st.sidebar.markdown(f"#### {t('website_filter')}")
website_options = ["Amazon", "Noon", "Jumia"]
website_filter = st.sidebar.multiselect(
    "Filter by website",
    options=website_options,
    default=st.session_state.website_filter if set(st.session_state.website_filter).issubset(set(website_options)) else website_options,
    label_visibility="collapsed"
)
if not website_filter:
    website_filter = website_options  # Show all if none selected

# Price filters - Min and Max
price_col1, price_col2 = st.sidebar.columns(2)
with price_col1:
    min_price_val = st.number_input(
        t("min_price"),
        min_value=0,
        value=0,
        step=500,
        help="Min price" if st.session_state.language == "en" else "الحد الأدنى"
    )
    min_price_val = None if min_price_val == 0 else float(min_price_val)

with price_col2:
    max_price_val = st.number_input(
        t("max_price"),
        min_value=0,
        value=0,
        step=500,
        help="Max price" if st.session_state.language == "en" else "الحد الأقصى"
    )
    max_price_val = None if max_price_val == 0 else float(max_price_val)

# Rating filter
min_rating_val = st.sidebar.slider(
    t("min_rating"),
    min_value=0.0,
    max_value=5.0,
    value=0.0,
    step=0.5,
    help="Filter products by minimum rating" if st.session_state.language == "en" else "فلتر المنتجات حسب الحد الأدنى للتقييم"
)
min_rating_val = None if min_rating_val == 0 else min_rating_val

# Brand filter
brand_filter = st.sidebar.text_input(
    t("brand_filter"),
    value="",
    placeholder="e.g., samsung, xiaomi" if st.session_state.language == "en" else "مثال: سامسونج، شاومي"
).strip() or None

# Sorting options
st.sidebar.markdown(f"### {t('sorting')}")
sort_by = st.sidebar.selectbox(
    t("sort_by"),
    options=["relevance_score", "price", "rating_numeric"],
    index=0,
    format_func=lambda x: {
        "relevance_score": "Relevance" if st.session_state.language == "en" else "الأهمية",
        "price": "Price" if st.session_state.language == "en" else "السعر",
        "rating_numeric": "Rating" if st.session_state.language == "en" else "التقييم"
    }.get(x, x)
)

sort_dir_options = ["Descending", "Ascending"] if st.session_state.language == "en" else ["تنازلي", "تصاعدي"]
sort_dir = st.sidebar.radio(
    t("direction"),
    options=sort_dir_options,
    index=0
)

st.sidebar.markdown("---")
tips_en = "💡 **Tip:** Try queries like:\n- 'samsung s25 ultra'\n- 'laptop with 16GB RAM'\n- '4k lg tv 55 inch'"
tips_ar = "💡 **نصيحة:** جرب استفسارات مثل:\n- 'هاتف سامسونج تحت 10000'\n- 'لابتوب بذاكرة 16 جيجا'"
st.sidebar.info(tips_en if st.session_state.language == "en" else tips_ar)

# =========================
# Main Search Interface
# =========================

user_input = st.text_area(
    "Filter by website",
    placeholder=t("search_placeholder"),
    height=120,
    help="Describe the product in Arabic or English" if st.session_state.language == "en" else "اوصف المنتج بالعربية أو الإنجليزية",
    label_visibility="collapsed"
)

# Centered search button - full width
search_clicked = st.button(t("search_button"), width='stretch', type="primary")

# =========================
# Search Processing
# =========================

if search_clicked:
    if not user_input.strip():
        st.warning("⚠️ Please enter a product description" if st.session_state.language == "en" else "⚠️ يرجى إدخال وصف المنتج")
    else:
        progress_bar = st.progress(0)
        status_text = st.empty()

        try:
            # Step 1: Preprocessing
            status_text.text("🔍 Analyzing your query..." if st.session_state.language == "en" else "🔍 تحليل الاستفسار...")
            progress_bar.progress(20)
            tokens, lang = preprocess_text(user_input)

            # Step 2: Enhanced attribute extraction
            status_text.text("🧠 Extracting attributes..." if st.session_state.language == "en" else "🧠 استخراج السمات...")
            progress_bar.progress(40)
            attrs = extract_enhanced_attributes(tokens, user_input, lang)

            # Step 3: Build search query
            query = " ".join(tokens).strip()
            if not query:
                st.error("❌ Could not extract meaningful search terms." if st.session_state.language == "en" else "❌ لم يتم استخراج مصطلحات بحث ذات معنى.")
                progress_bar.empty()
                status_text.empty()
                st.stop()

            # Step 4: Crawl all platforms (optimized - reduced detailed fetching for speed)
            status_text.text("🛒 Searching Amazon, Noon & Jumia..." if st.session_state.language == "en" else "🛒 البحث في أمازون ونون وجوميا...")
            progress_bar.progress(60)
            
            csv_path = os.path.join("data", "multi_platform_results.csv")
            os.makedirs("data", exist_ok=True)

            # Optimize: Use fewer products per platform and less detailed fetching for speed
            products_per_platform = 15  # Fixed amount for faster results
            
            try:
                raw_results = crawl_all_platforms(
                    query=query,
                    output_path=csv_path,
                    pages=1,  # Single page for speed
                    max_products_per_platform=products_per_platform,
                    detailed=False,  # Disable detailed fetching for speed
                )
            except Exception as e:
                st.error(f"❌ Error during search: {str(e)}")
                progress_bar.empty()
                status_text.empty()
                st.stop()

            # Step 5: Load and process results
            status_text.text("📊 Processing results..." if st.session_state.language == "en" else "📊 معالجة النتائج...")
            progress_bar.progress(80)

            if raw_results.empty:
                try:
                    raw_results = pd.read_csv(csv_path)
                except:
                    st.warning(t("no_products"))
                    progress_bar.empty()
                    status_text.empty()
                    st.stop()

            if raw_results.empty:
                st.warning(t("no_products"))
                progress_bar.empty()
                status_text.empty()
                st.stop()

            # Clean and prepare data
            raw_results = clean_price_column(raw_results)
            
            # Rename columns for compatibility
            column_mapping = {
                "title": "product_name",
                "image": "image_url",
                "product_link": "link"
            }
            for old_col, new_col in column_mapping.items():
                if old_col in raw_results.columns:
                    raw_results = raw_results.rename(columns={old_col: new_col})
            
            results = raw_results

            # Extract numeric rating
            if "rating" in results.columns:
                results["rating_numeric"] = results["rating"].apply(extract_rating_numeric)
            else:
                results["rating_numeric"] = 0.0
            
            # Ensure website column exists
            if "website" not in results.columns:
                results["website"] = "Unknown"

            # Step 6: Calculate relevance and rank
            status_text.text("🎯 Ranking by relevance..." if st.session_state.language == "en" else "🎯 الترتيب حسب الأهمية...")
            progress_bar.progress(90)
            
            ranked_results = search_products_enhanced(results, attrs, top_n=len(results))
            
            # Store raw ranked results for filter re-application
            st.session_state.raw_ranked_results = ranked_results
            st.session_state.current_page = 0

            progress_bar.progress(100)
            status_text.text("✅ Search complete!" if st.session_state.language == "en" else "✅ اكتمل البحث!")
            
            # Apply filters to get final results
            final_results = apply_ui_filters(
                ranked_results,
                sort_by=sort_by,
                sort_dir=sort_dir,
                min_price=min_price_val,
                max_price=max_price_val,
                min_rating=min_rating_val,
                brand_filter=brand_filter,
                website_filter=website_filter
            )
            st.session_state.search_results = final_results

            # Save to history
            st.session_state.history.insert(0, {
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "query": user_input,
                "attrs": attrs,
                "count": len(final_results)
            })
            save_history(st.session_state.history)  # Persist to file

            time.sleep(0.3)
            progress_bar.empty()
            status_text.empty()
            st.success(f"✅ {t('found')} {len(final_results)} {t('products')}" if len(final_results) > 0 else t("no_results"))
            st.rerun()

        except Exception as e:
            progress_bar.empty()
            status_text.empty()
            # Silently handle errors to prevent user-facing error messages
            st.warning(t("no_products"))
            import traceback
            traceback.print_exc()  # Print to console for debugging

# =========================
# Display Results with Pagination
# =========================

# Re-apply filters if we have raw results (for when filters change)
if not st.session_state.raw_ranked_results.empty:
    results_df = apply_ui_filters(
        st.session_state.raw_ranked_results,
        sort_by=sort_by,
        sort_dir=sort_dir,
        min_price=min_price_val,
        max_price=max_price_val,
        min_rating=min_rating_val,
        brand_filter=brand_filter,
        website_filter=website_filter
    )
    st.session_state.search_results = results_df
elif not st.session_state.search_results.empty:
    results_df = st.session_state.search_results
else:
    results_df = pd.DataFrame()

if not results_df.empty:
    items_per_page = 5
    total_pages = (len(results_df) - 1) // items_per_page + 1
    
    if total_pages > 0:
        # Pagination controls
        col_prev, col_info, col_next = st.columns([1, 3, 1])
        
        with col_prev:
            prev_disabled = st.session_state.current_page == 0
            if st.button("⬅️", disabled=prev_disabled, width='stretch', key="prev_page"):
                st.session_state.current_page = max(0, st.session_state.current_page - 1)
                st.rerun()
        
        with col_info:
            page_info = f"Page {st.session_state.current_page + 1} of {total_pages} | {len(results_df)} total products"
            if st.session_state.language == "ar":
                page_info = f"الصفحة {st.session_state.current_page + 1} من {total_pages} | {len(results_df)} منتج إجمالي"
            st.markdown(f"<div style='text-align:center;padding:15px;font-size:16px;font-weight:600;'>{page_info}</div>", unsafe_allow_html=True)
        
        with col_next:
            next_disabled = st.session_state.current_page >= total_pages - 1
            if st.button("➡️", disabled=next_disabled, width='stretch', key="next_page"):
                st.session_state.current_page = min(total_pages - 1, st.session_state.current_page + 1)
                st.rerun()
        
        # Display products for current page
        start_idx = st.session_state.current_page * items_per_page
        end_idx = min(start_idx + items_per_page, len(results_df))
        page_results = results_df.iloc[start_idx:end_idx]
        
        st.markdown("---")
        for idx, (_, row) in enumerate(page_results.iterrows()):
            try:
                render_product_card_enhanced(row, show_relevance=True)
                if idx < len(page_results) - 1:
                    st.markdown("<br>", unsafe_allow_html=True)
            except Exception as e:
                # Silently skip problematic products
                continue

# =========================
# History & About Sections at Bottom
# =========================

st.markdown("---")
st.markdown("## 📋 Additional Information")

bottom_tab_history, bottom_tab_about = st.tabs(["🕒 Search History", "ℹ️ About"])

with bottom_tab_history:
    if st.session_state.history:
        col_clear, col_count = st.columns([1, 2])
        with col_clear:
            if st.button(t("clear_history"), key="clear_history_btn"):
                st.session_state.history = []
                st.rerun()
        
        with col_count:
            history_count = f"📊 {len(st.session_state.history)} searches in history"
            if st.session_state.language == "ar":
                history_count = f"📊 {len(st.session_state.history)} عمليات بحث في السجل"
            st.markdown(f"**{history_count}**")
        
        st.markdown("")
        
        for idx, item in enumerate(st.session_state.history):
            timestamp = item["time"]
            query = item["query"][:50] + "..." if len(item["query"]) > 50 else item["query"]
            count = item["count"]
            
            # Create clickable history item
            if st.button(
                f"🕐 {timestamp} | 📝 {query} | ({count} results)",
                key=f"history_{idx}",
                width='stretch',
                help="Click to view this search again"
            ):
                # Re-run search with this query
                st.session_state.search_results = pd.DataFrame()
                st.session_state.raw_ranked_results = pd.DataFrame()
                st.rerun()
    else:
        st.info("💡 No search history yet. Try searching for a product!" if st.session_state.language == "en" else "💡 لا يوجد سجل بحث حتى الآن. جرب البحث عن منتج!")

with bottom_tab_about:
    about_content_en = """
    ## 🎓 Smart Shopping Assistant
    
    This is an **NLP-powered shopping assistant** built for university coursework that helps you find the best products across multiple platforms.
    
    ### ✨ Core Features
    - **🌍 Multi-Platform Search**: Compare prices from Amazon, Noon, and Jumia in real-time
    - **🧠 Intelligent Ranking**: Advanced NLP-based relevance scoring
    - **🌐 Bilingual Support**: Full support for Arabic and English
    - **🔍 Smart Filtering**: Filter by price, rating, brand, and website
    - **📱 Responsive Design**: Beautiful UI with light and dark themes
    
    ### 🚀 Technical Stack
    - **Backend**: Python, Streamlit, BeautifulSoup, Pandas
    - **NLP**: Advanced preprocessing and attribute extraction
    - **Performance**: Concurrent web scraping for fast results
    
    ### 💡 How to Use
    1. Enter a product description (e.g., "Samsung phone under 10000")
    2. Adjust filters in the sidebar
    3. Click "Search Products"
    4. Browse results with relevance scores
    5. Click on product titles to view on the original website
    
    ### 👥 Built By

    - **Mazen Mohamed**
    - **Youssef Mohamed**
    - **Abdulrahman Sami**
    - **Mahmoud Ismail**
    - **Justina Hani**

    Project for **Natural Language Processing** course  
    Third Year — AI / Computer Science

    ### 📞 Support
    For issues or suggestions, please contact the development team.
    """
    
    about_content_ar = """
    ## 🎓 مساعد التسوق الذكي
    
    هذا **مساعد تسوق مدعوم بمعالجة اللغة الطبيعية** مبني لمشروع جامعي يساعدك في العثور على أفضل المنتجات عبر منصات متعددة.
    
    ### ✨ الميزات الأساسية
    - **🌍 بحث متعدد المنصات**: قارن الأسعار من أمازون ونون وجوميا في الوقت الفعلي
    - **🧠 ترتيب ذكي**: نظام تقييم متقدم قائم على معالجة اللغة الطبيعية
    - **🌐 دعم ثنائي اللغة**: دعم كامل للعربية والإنجليزية
    - **🔍 فلترة ذكية**: فلتر حسب السعر والتقييم والعلامة التجارية والموقع
    - **📱 واجهة سريعة الاستجابة**: واجهة جميلة مع مظاهر فاتحة ومظلمة
    
    ### 🚀 التقنيات المستخدمة
    - **الخادم الخلفي**: Python, Streamlit, BeautifulSoup, Pandas
    - **معالجة اللغة الطبيعية**: معالجة متقدمة واستخراج السمات
    - **الأداء**: كشط الويب المتزامن للحصول على نتائج سريعة
    
    ### 💡 كيفية الاستخدام
    1. أدخل وصف المنتج (مثال: "هاتف سامسونج تحت 10000")
    2. اضبط الفلاتر في الشريط الجانبي
    3. انقر على "البحث عن المنتجات"
    4. استعرض النتائج مع درجات الملاءمة
    5. انقر على عناوين المنتجات للعرض على الموقع الأصلي
    
    ### 👥 مبني بواسطة

    - **Mazen Mohamed**
    - **Youssef Mohamed**
    - **Abdulrahman Sami**
    - **Mahmoud Ismail**
    - **Justina Hani**


    مشروع مقرر **معالجة اللغة الطبيعية**  
    السنة الثالثة — ذكاء اصطناعي / علوم الحاسب


    ### 📞 الدعم
    إذا واجهت مشاكل أو لديك اقتراحات، يرجى التواصل مع فريق التطوير.
    """
    
    st.markdown(about_content_en if st.session_state.language == "en" else about_content_ar)
