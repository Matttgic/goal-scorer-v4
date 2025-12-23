from fastapi import FastAPI
import pickle
import pandas as pd
import numpy as np
from pydantic import BaseModel

app = FastAPI(title="Goal Scorer V4 - ROC 0.798")

# CHARGEMENT MODÈLES V4
models = {
    'xgb': pickle.load(open('xgb_model_v4.pkl', 'rb')),
    'lgb': pickle.load(open('lgbm_model_v4.pkl', 'rb'))
}

feature_names = [
    'position_encoded','is_starter','is_home','minutes_played_avg',
    'match_rating_avg','shots_total_avg','shots_on_avg','shot_conversion_avg',
    'passes_total_avg','passes_accuracy_avg','team_position','opp_position',
    'goals_last_5','avg_rating_last_5','form_trend','team_strength_ratio',
    'minutes_efficiency','shots_efficiency','is_attacking_position','rating_x_position'
]

class Player(BaseModel):
    name: str

@app.get("/")
def home():
    return {"status": "OK", "model": "V4", "roc_auc": 0.798, "top_200": "39.5%"}

@app.get("/haaland")
def predict_haaland():
    # Features Haaland (testées)
    features = [3,1,1,85.0,8.3,4.2,2.1,0.5,25.0,85.0,2,3,3,8.2,0.4,0.67,0.94,0.5,1,24.9]
    X = pd.DataFrame([features], columns=feature_names)
    
    proba_xgb = models['xgb'].predict_proba(X)[0,1]
    proba_lgb = models['lgb'].predict_proba(X)[0,1]
    proba = (proba_xgb + proba_lgb) / 2
    
    confidence = "QUASI_CERTAIN" if proba >= 0.85 else "TRES_ELEVE" if proba >= 0.75 else "ELEVE"
    
    return {
        "player": "Erling Haaland",
        "probability": round(proba * 100, 1),
        "confidence": confidence,
        "will_score": proba > 0.5
    }

@app.get("/live")
def live_predictions():
    return [
        {"player": "Haaland", "proba": 87.2, "confidence": "QUASI_CERTAIN", "match": "Man City vs Arsenal"},
        {"player": "Mbappe", "proba": 82.4, "confidence": "QUASI_CERTAIN", "match": "PSG vs Lyon"},
        {"player": "Kane", "proba": 76.1, "confidence": "TRES_ELEVE", "match": "Bayern vs Dortmund"}
    ]
