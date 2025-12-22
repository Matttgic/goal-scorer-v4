from flask import Flask, request, jsonify
from flask_cors import CORS
import pickle
import pandas as pd
import numpy as np
import os

app = Flask(__name__)
CORS(app)

# Configuration
API_FOOTBALL_KEY = os.environ.get('API_FOOTBALL_KEY', '')

# Charger modèles
try:
    with open('xgb_model.pkl', 'rb') as f:
        xgb_model = pickle.load(f)
    with open('lgbm_model.pkl', 'rb') as f:
        lgbm_model = pickle.load(f)
    models_loaded = True
except:
    xgb_model = None
    lgbm_model = None
    models_loaded = False

position_map = {'G': 0, 'D': 1, 'M': 2, 'F': 3}
feature_names = ['position_encoded', 'is_starter', 'is_home', 'minutes_played',
                'match_rating', 'shots_total', 'shots_on', 'shot_conversion',
                'passes_total', 'passes_accuracy', 'team_position', 'opp_position']

def predict_player(player_data):
    if xgb_model is None or lgbm_model is None:
        return None
    
    features = {
        'position_encoded': position_map.get(player_data.get('position', 'F'), 3),
        'is_starter': 1 if player_data.get('is_starter', True) else 0,
        'is_home': 1 if player_data.get('is_home', True) else 0,
        'minutes_played': player_data.get('minutes_played', 90),
        'match_rating': player_data.get('match_rating', 7.0),
        'shots_total': player_data.get('shots_total', 2),
        'shots_on': player_data.get('shots_on', 1),
        'passes_total': player_data.get('passes_total', 25),
        'passes_accuracy': player_data.get('passes_accuracy', 75),
        'team_position': player_data.get('team_position', 10),
        'opp_position': player_data.get('opp_position', 10)
    }
    
    features['shot_conversion'] = features['shots_on'] / features['shots_total'] if features['shots_total'] > 0 else 0
    
    X = pd.DataFrame([features])[feature_names]
    proba_xgb = float(xgb_model.predict_proba(X)[0, 1])
    proba_lgbm = float(lgbm_model.predict_proba(X)[0, 1])
    proba_ensemble = (proba_xgb + proba_lgbm) / 2
    
    if proba_ensemble >= 0.90:
        confidence = 'QUASI_CERTAIN'
        emoji = '🔥'
    elif proba_ensemble >= 0.80:
        confidence = 'TRES_ELEVE'
        emoji = '⭐'
    elif proba_ensemble >= 0.70:
        confidence = 'ELEVE'
        emoji = '💫'
    elif proba_ensemble >= 0.50:
        confidence = 'MOYEN'
        emoji = '💡'
    else:
        confidence = 'FAIBLE'
        emoji = '🤔'
    
    return {
        'probability': round(proba_ensemble * 100, 1),
        'confidence_level': confidence,
        'confidence_emoji': emoji,
        'models': {
            'xgboost': round(proba_xgb * 100, 1),
            'lightgbm': round(proba_lgbm * 100, 1)
        }
    }

@app.route('/')
def home():
    return jsonify({
        'status': 'ok',
        'service': 'Goal Scorer Predictions API',
        'version': '1.0',
        'model_performance': {
            'roc_auc': 0.986,
            'top_200_precision': '96.5%',
            'quasi_certain_precision': '82.8%'
        },
        'endpoints': {
            'GET /api/health': 'Vérifier le status',
            'POST /api/predict': 'Prédire un joueur',
            'GET /api/test': 'Test simple'
        }
    })

@app.route('/api/health')
def health():
    return jsonify({
        'status': 'ok',
        'models_loaded': models_loaded,
        'api_football_configured': API_FOOTBALL_KEY != ''
    })

@app.route('/api/predict', methods=['POST'])
def predict():
    try:
        data = request.json
        prediction = predict_player(data)
        
        if prediction:
            return jsonify({
                'success': True,
                'player': data.get('player_name', 'Unknown'),
                'prediction': prediction
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Modèles non chargés'
            }), 500
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@app.route('/api/test')
def test():
    test_player = {
        'player_name': 'Test Player',
        'position': 'F',
        'is_starter': True,
        'is_home': True,
        'team_position': 1,
        'opp_position': 15,
        'shots_total': 5,
        'shots_on': 3
    }
    
    prediction = predict_player(test_player)
    
    return jsonify({
        'message': 'API fonctionne !',
        'models': {
            'loaded': models_loaded
        },
        'test_prediction': prediction
    })

# Pour Vercel
app = app
