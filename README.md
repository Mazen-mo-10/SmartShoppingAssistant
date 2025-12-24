# 🛒 Smart Shopping Assistant

An intelligent shopping assistant application with multi-platform product search, NLP-powered ranking, and ML-based price classification.

## 🚀 Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run the application
streamlit run app.py
```

The app will be available at `http://localhost:8501`

## 📁 Project Structure

```
.
├── app.py                          # Main Streamlit application
├── models/                         # ML models and inference
│   ├── price_classifier.py        # Price classification predictor
│   └── price_classifier_model.joblib  # Trained model artifact
├── nlp/                           # NLP preprocessing & extraction
│   ├── preprocessing.py
│   ├── attribute_extraction_enhanced.py
│   └── utils.py
├── search/                        # Search engine
│   └── search_engine_enhanced.py
├── data/                          # Data files
│   ├── multi_platform_results.csv
│   └── search_history.json
├── docs/                          # Documentation
└── tests/                         # Test files
```

## 🎯 Features

- **Multi-Platform Search**: Search products across Amazon, Noon, and Jumia
- **NLP Ranking**: Enhanced search results ranking using NLP
- **Price Classification**: ML model that predicts if a price is fair (عادل) or not fair (غير عادل)
- **Multi-Language**: Supports both English and Arabic
- **Real-Time Predictions**: Get price fairness classification as you browse

## 📚 Documentation

For detailed documentation, see the [docs/](docs/) folder:

- **[QUICK_START.md](docs/QUICK_START.md)** — Setup and first run instructions
- **[ARCHITECTURE.md](docs/ARCHITECTURE.md)** — System architecture and design
- **[MODEL_SUMMARY.md](docs/MODEL_SUMMARY.md)** — ML model details and performance
- **[INDEX.md](docs/INDEX.md)** — Complete documentation index

## 🔧 Tech Stack

- **Frontend**: Streamlit (Python web framework)
- **NLP**: NLTK, scikit-learn (TF-IDF)
- **ML**: scikit-learn (RandomForest, Logistic Regression, etc.)
- **Data Processing**: pandas, numpy
- **Crawling**: Custom web scrapers for product platforms

## 📝 License

This project is for educational purposes.
