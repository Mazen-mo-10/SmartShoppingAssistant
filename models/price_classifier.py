# models/price_classifier.py
import joblib
import json
import os
import re
from pathlib import Path
import numpy as np

class PriceClassifier:
    def __init__(self, model_dir='models'):
        """Initialize the price classifier with saved models"""
        self.model_dir = model_dir
        self.model = None
        self.label_encoder = None
        self.config = None
        self.loaded = False
        self.load_models()
    
    def load_models(self):
        """Load all saved models and configuration"""
        try:
            model_path = os.path.join(self.model_dir, 'price_classifier_model.joblib')
            encoder_path = os.path.join(self.model_dir, 'label_encoder.joblib')
            config_path = os.path.join(self.model_dir, 'price_classifier_config.json')
            
            if os.path.exists(model_path):
                # Load pipeline (may be a sklearn Pipeline or a standalone estimator)
                self.model = joblib.load(model_path)

                # Try to load label encoder if present, otherwise infer classes from the estimator
                if os.path.exists(encoder_path):
                    try:
                        self.label_encoder = joblib.load(encoder_path)
                    except Exception:
                        self.label_encoder = None
                else:
                    self.label_encoder = None

                # Load config if available, otherwise create a safe default
                if os.path.exists(config_path):
                    try:
                        with open(config_path, 'r', encoding='utf-8') as f:
                            self.config = json.load(f)
                    except Exception:
                        self.config = None
                else:
                    self.config = None

                # If label encoder missing, try to infer classes from pipeline
                if self.label_encoder is None:
                    inferred = None
                    try:
                        if hasattr(self.model, 'named_steps') and 'classifier' in self.model.named_steps:
                            inferred = getattr(self.model.named_steps['classifier'], 'classes_', None)
                        inferred = inferred or getattr(self.model, 'classes_', None)
                    except Exception:
                        inferred = None

                    if inferred is not None:
                        # Create a lightweight object with classes_ attribute
                        le = type('LE', (), {})()
                        le.classes_ = np.array(inferred)
                        self.label_encoder = le

                # Ensure there's a config with minimal defaults
                if self.config is None:
                    self.config = {
                        'median_price': 1.0,
                        'lower_threshold': 0.7,
                        'upper_threshold': 1.3,
                        'colors': {
                            'مناسب_جدا': 'green',
                            'متوسط': 'yellow',
                            'غالي_جدا': 'red'
                        },
                        'labels_arabic': {}
                    }

                self.loaded = True
                print(f"✅ Price classifier models loaded successfully (robust mode).")
        except Exception as e:
            print(f"⚠️ Warning: Could not load price classifier models: {e}")
            self.loaded = False
    
    def clean_text(self, text):
        """Clean and preprocess text"""
        if not text:
            return ""
        
        text = str(text).lower()
        text = re.sub(r'<[^>]+>', '', text)  # Remove HTML
        text = re.sub(r'http\S+|www\S+', '', text)  # Remove URLs
        text = re.sub(r'[^a-zA-Z0-9\s\u0600-\u06FF]', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text
    
    def predict(self, title, description="", price=None):
        """
        Predict price category
        
        Args:
            title: Product title
            description: Product description (optional)
            price: Actual price (optional, for feature engineering)
        
        Returns:
            dict with prediction details
        """
        if not self.loaded:
            return None
        
        try:
            import pandas as pd

            # Prepare a few candidate input shapes to try with the saved pipeline
            text = f"{self.clean_text(title)} {self.clean_text(description)}"

            # Default safe price handling
            if price is None:
                price = float(self.config.get('median_price', 1.0))

            price_normalized = 0.0
            try:
                median = float(self.config.get('median_price', 1.0))
                price_normalized = price / (median * 2) if median != 0 else 0.0
                price_normalized = min(max(price_normalized, 0.0), 1.0)
            except Exception:
                price_normalized = 0.5

            attempts = []

            # Common format used by price_classifier.ipynb
            attempts.append(pd.DataFrame({'text_combined': [text], 'price_normalized': [price_normalized]}))

            # Format similar to Sales_model pipeline (name, main_category, sub_category, ratings_num, no_of_ratings_num)
            attempts.append(pd.DataFrame([{
                'name': title,
                'main_category': '',
                'sub_category': '',
                'ratings_num': np.nan,
                'no_of_ratings_num': np.nan
            }]))

            # Simple single-column 'text' or 'title'
            attempts.append(pd.DataFrame({'text': [text]}))
            attempts.append(pd.DataFrame({'title': [text]}))

            last_exception = None
            pred_label = None
            pred_proba = None

            for X in attempts:
                try:
                    # Ensure columns are present as expected by the pipeline
                    pred = self.model.predict(X)
                    pred_proba = None
                    if hasattr(self.model, 'predict_proba'):
                        try:
                            pred_proba = self.model.predict_proba(X)
                        except Exception:
                            # some classifiers inside pipelines expose predict_proba on the classifier
                            try:
                                pred_proba = self.model.named_steps['classifier'].predict_proba(X)
                            except Exception:
                                pred_proba = None

                    pred_val = pred[0] if hasattr(pred, '__len__') else pred

                    # Map numeric predictions to class names if label encoder present
                    if self.label_encoder is not None and hasattr(self.label_encoder, 'classes_'):
                        classes = list(self.label_encoder.classes_)
                        if isinstance(pred_val, (int, np.integer)) and 0 <= int(pred_val) < len(classes):
                            pred_label = classes[int(pred_val)]
                        else:
                            pred_label = str(pred_val)
                    else:
                        pred_label = str(pred_val)

                    # If we have probabilities turn into a list
                    if pred_proba is not None:
                        probs = pred_proba[0].tolist()
                    else:
                        probs = []

                    # Successful prediction
                    break
                except Exception as ex:
                    last_exception = ex
                    continue

            if pred_label is None:
                print(f"Error: model could not predict using any input shape. Last error: {last_exception}")
                return None

            # Normalize label and map to Arabic/colors
            # If model uses English labels like 'Fair' / 'Not Fair', map them
            label_ar = self.config.get('labels_arabic', {}).get(pred_label)
            if not label_ar:
                # Provide sensible defaults
                mapping_en_to_ar = {
                    'Fair': ('مناسب_جدا', '🟢 عادل'),
                    'Not Fair': ('غالي_جدا', '🔴 غير عادل'),
                    'Not_Fair': ('غالي_جدا', '🔴 غير عادل'),
                    'NotFair': ('غالي_جدا', '🔴 غير عادل')
                }

                if pred_label in mapping_en_to_ar:
                    short_label, arabic_label = mapping_en_to_ar[pred_label]
                    color = self.config.get('colors', {}).get(short_label, 'red')
                    label_ar = arabic_label
                    pred_label_out = short_label
                else:
                    # If pred_label already Arabic, use it
                    pred_label_out = pred_label
                    # fallback color
                    if pred_label in self.config.get('colors', {}):
                        color = self.config['colors'][pred_label]
                    else:
                        color = 'gray'
                        label_ar = pred_label
            else:
                # found mapping in config
                color = self.config.get('colors', {}).get(pred_label, 'gray')
                pred_label_out = pred_label

            confidence = max(probs) if probs else 0.0

            probabilities = {}
            if probs and self.label_encoder is not None and hasattr(self.label_encoder, 'classes_'):
                for k, v in zip(self.label_encoder.classes_, probs):
                    probabilities[str(k)] = float(v)

            return {
                'label': pred_label_out,
                'label_arabic': label_ar,
                'color': color,
                'confidence': float(confidence),
                'probabilities': probabilities
            }
        except Exception as e:
            print(f"Error in prediction: {e}")
            return None
    
    def get_badge_html(self, result):
        """Generate HTML badge for the prediction"""
        if result is None:
            return ""
        
        color = result['color']
        label = result['label_arabic']
        confidence = result['confidence']
        
        colors_map = {
            'green': '#10b981',
            'yellow': '#f59e0b',
            'red': '#ef4444'
        }
        
        bg_color = colors_map.get(color, '#6b7280')
        
        html = f"""
        <span style="
            display: inline-block;
            background-color: {bg_color};
            color: white;
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: bold;
            margin-right: 8px;
            text-align: center;
        ">
            {label} ({confidence:.0%})
        </span>
        """
        return html
    
    def get_badge_markdown(self, result, language='ar'):
        """Generate markdown badge (for Streamlit) with language support
        
        Args:
            result: Prediction result dict
            language: 'ar' for Arabic, 'en' for English
        
        Returns:
            Markdown formatted badge string
        """
        if result is None:
            return "⚪ N/A" if language == 'en' else "⚪ غير متاح"
        
        emoji_map = {
            'مناسب_جدا': '🟢',
            'متوسط': '🟡',
            'غالي_جدا': '🔴',
            'Fair': '🟢',
            'Not Fair': '🔴'
        }
        
        emoji = emoji_map.get(result['label'], '⚪')
        
        # Get label in requested language
        if language == 'en':
            # Map internal labels to English
            en_labels = {
                'مناسب_جدا': 'Fair',
                'متوسط': 'Medium',
                'غالي_جدا': 'Expensive',
                'Fair': 'Fair',
                'Not Fair': 'Not Fair'
            }
            label = en_labels.get(result['label'], result['label'])
        else:
            label = result['label_arabic']
        
        # Return without confidence
        return f"{emoji} **{label}**"

# Initialize classifier when imported
price_classifier = None
try:
    # Try to load from models directory
    price_classifier = PriceClassifier('models')
    if not price_classifier.loaded:
        price_classifier = None
except Exception as e:
    print(f"Warning: Could not initialize price classifier: {e}")
    price_classifier = None
