import logging
import requests
from typing import List, Dict, Optional

logger = logging.getLogger("PriceIntel.Sentiment")

# Models IDs used in Mahameru Sentiment Service
ID_MODEL_ID = "poerwiyanto/bert-base-indonesian-522M-finetuned-sentiment"
EN_MODEL_ID = "ProsusAI/finbert"

class SentimentAnalyzer:
    def __init__(self):
        self.id_pipeline = None
        self.en_pipeline = None
        self.models_loaded = False

    def load_models(self):
        """Lazy load transformers models"""
        if self.models_loaded:
            return
        
        try:
            from transformers import pipeline
            from langdetect import detect, DetectorFactory
            DetectorFactory.seed = 0
            
            logger.info("Loading Sentiment Models (Indonesian BERT & FinBERT)...")
            self.id_pipeline = pipeline("sentiment-analysis", model=ID_MODEL_ID)
            self.en_pipeline = pipeline("sentiment-analysis", model=EN_MODEL_ID)
            self.detect = detect
            self.models_loaded = True
            logger.info("Sentiment models loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to load sentiment models: {e}")
            self.models_loaded = False

    def analyze_text(self, text: str) -> str:
        """Analyze a single piece of text"""
        if not self.models_loaded:
            self.load_models()
        
        if not self.models_loaded:
            return "NEUTRAL"

        try:
            lang = self.detect(text[:512])
            pipe = self.id_pipeline if lang == 'id' else self.en_pipeline
            
            if not pipe:
                return "NEUTRAL"
            
            res = pipe(text[:512])[0]
            label = res['label'].upper()
            
            sentiment = "NEUTRAL"
            if 'LABEL_0' in label or 'NEGATIVE' in label: sentiment = "NEGATIVE"
            elif 'LABEL_1' in label or 'NEUTRAL' in label: sentiment = "NEUTRAL"
            elif 'LABEL_2' in label or 'POSITIVE' in label: sentiment = "POSITIVE"
            
            return sentiment
        except Exception as e:
            logger.error(f"Sentiment analysis error: {e}")
            return "NEUTRAL"

    def analyze_news_batch(self, news: List[Dict]) -> Dict[str, int]:
        """Analyze a batch of news and return distribution"""
        dist = {"POSITIVE": 0, "NEGATIVE": 0, "NEUTRAL": 0}
        
        for n in news:
            text = f"{n['title']}" # Title is usually enough and faster
            sentiment = self.analyze_text(text)
            n['sentiment'] = sentiment
            dist[sentiment] += 1
            
        return dist
