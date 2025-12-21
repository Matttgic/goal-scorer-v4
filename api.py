"""
API Flask pour prédictions de buteurs
Usage: python api.py
Endpoint: http://localhost:5000/predict
"""

from flask import Flask, request, jsonify
import pickle
import pandas as pd
import numpy as np

app = Flask(__name__)

# Charger modèles
with open('xgb_model.pkl', 'rb') as f:
    xgb_model = pickle.load(f)
with open('lgbm_model.pkl', 'rb') as f:
    lgbm_model = pickle.load(f)

position_map = {'G': 0, 'D': 1, 'M': 2, 'F': 3}
feature_names = ['position_encoded', 'is_starter', 'is_home', 'minutes_played',
                'match_rating', 'shots_total', 'shots_on', 'shot_conversion',
                'passes_total', 'passes_accuracy', 'team_position', 'opp_position']

@app.route('/predict', methods=['POST'])
def predict():
    """
    Prédire la probabilité de but pour un joueur
    
    Body JSON:
    {
        "position": "F",
        "is_starter": 1,
        "is_home": 1,
        "minutes_played": 90,
        "match_rating": 7.5,
        "shots_total": 3,
        "shots_on": 2,
        "passes_total": 25,
        "passes_accuracy": 80,
        "team_position": 5,
        "opp_position": 10
    }
    """
    try:
        data = request.json
        
        features = {
            'position_encoded': position_map.get(data.get('position', 'F'), 3),
            'is_starter': data.get('is_starter', 1),
            'is_home': data.get('is_home', 1),
            'minutes_played': data.get('minutes_played', 90),
            'match_rating': data.get('match_rating', 7.0),
            'shots_total': data.get('shots_total', 0),
            'shots_on': data.get('shots_on', 0),
            'passes_total': data.get('passes_total', 0),
            'passes_accuracy': data.get('passes_accuracy', 0),
            'team_position': data.get('team_position', 10),
            'opp_position': data.get('opp_position', 10)
        }
        
        features['shot_conversion'] = (
            features['shots_on'] / features['shots_total'] 
            if features['shots_total'] > 0 else 0
        )
        
        X = pd.DataFrame([features])[feature_names]
        proba_xgb = xgb_model.predict_proba(X)[0, 1]
        proba_lgbm = lgbm_model.predict_proba(X)[0, 1]
        proba_ensemble = (proba_xgb + proba_lgbm) / 2
        
        if proba_ensemble >= 0.90:
            confidence = 'QUASI_CERTAIN'
        elif proba_ensemble >= 0.80:
            confidence = 'TRES_ELEVE'
        elif proba_ensemble >= 0.70:
            confidence = 'ELEVE'
        elif proba_ensemble >= 0.50:
            confidence = 'MOYEN'
        else:
            confidence = 'FAIBLE'
        
        return jsonify({
            'success': True,
            'probability': float(proba_ensemble),
            'probability_xgb': float(proba_xgb),
            'probability_lgbm': float(proba_lgbm),
            'confidence_level': confidence
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'model': 'loaded'})

if __name__ == '__main__':
    print("🚀 API démarrée sur http://localhost:5000")
    print("Endpoints:")
    print("  POST /predict - Prédire un joueur")
    print("  GET  /health  - Vérifier status")
    app.run(debug=True, host='0.0.0.0', port=5000)
