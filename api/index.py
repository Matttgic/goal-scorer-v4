from flask import Flask, request, jsonify
from flask_cors import CORS
import pickle
import pandas as pd
import numpy as np
import os
import requests
from datetime import datetime
from typing import Dict, Optional, List

app = Flask(__name__)
CORS(app)

# ============ CONFIGURATION ============
API_FOOTBALL_KEY = os.environ.get('API_FOOTBALL_KEY', '')
API_FOOTBALL_BASE = 'https://v3.football.api-sports.io'
CURRENT_SEASON = 2025  # ⚠️ Saison 2025-2026

# ============ CHARGER LES MODÈLES ============
def load_models():
    try:
        with open('xgb_model.pkl', 'rb') as f:
            xgb_model = pickle.load(f)
        with open('lgbm_model.pkl', 'rb') as f:
            lgbm_model = pickle.load(f)
        return xgb_model, lgbm_model
    except Exception as e:
        print(f"Erreur chargement modèles: {e}")
        return None, None

xgb_model, lgbm_model = load_models()
models_loaded = xgb_model is not None and lgbm_model is not None

# ============ CONSTANTES ============
position_map = {'G': 0, 'D': 1, 'M': 2, 'F': 3, 'Goalkeeper': 0, 'Defender': 1, 'Midfielder': 2, 'Attacker': 3}
feature_names = ['position_encoded', 'is_starter', 'is_home', 'minutes_played',
                'match_rating', 'shots_total', 'shots_on', 'shot_conversion',
                'passes_total', 'passes_accuracy', 'team_position', 'opp_position']

LEAGUES = {
    39: {'name': 'Premier League', 'country': 'England'},
    61: {'name': 'Ligue 1', 'country': 'France'},
    140: {'name': 'La Liga', 'country': 'Spain'},
    135: {'name': 'Serie A', 'country': 'Italy'},
    78: {'name': 'Bundesliga', 'country': 'Germany'}
}

# ============ UTILITAIRES API ============

def get_api_football_headers():
    return {'x-apisports-key': API_FOOTBALL_KEY}

def get_team_position(league_id: int, team_id: int) -> int:
    """Récupérer la position actuelle de l'équipe au classement"""
    try:
        response = requests.get(
            f'{API_FOOTBALL_BASE}/standings',
            params={'league': league_id, 'season': CURRENT_SEASON},  # ✅ 2025
            headers=get_api_football_headers(),
            timeout=5
        )
        response.raise_for_status()
        
        data = response.json()
        if data.get('response'):
            for group in data['response'][0].get('league', {}).get('standings', []):
                for team in group:
                    if team['team']['id'] == team_id:
                        return team['rank']
        return 10
    except Exception as e:
        print(f"Erreur récupération position: {e}")
        return 10

def get_player_season_stats(player_id: int, league_id: int) -> Optional[Dict]:
    """
    Récupérer les stats MOYENNES de la saison en cours
    ⚠️ CRUCIAL pour prédire les matchs à venir !
    """
    try:
        response = requests.get(
            f'{API_FOOTBALL_BASE}/players',
            params={
                'id': player_id,
                'league': league_id,
                'season': CURRENT_SEASON  # ✅ 2025
            },
            headers=get_api_football_headers(),
            timeout=5
        )
        response.raise_for_status()
        
        data = response.json()
        if not data.get('response'):
            return None
        
        player_data = data['response'][0]
        stats = player_data['statistics'][0]  # Première ligue (la plus pertinente)
        
        # Extraire les stats moyennes
        games = stats.get('games', {})
        shots = stats.get('shots', {})
        passes = stats.get('passes', {})
        
        return {
            'position': player_data['player']['position'],
            'rating': float(stats.get('games', {}).get('rating') or 7.0),
            'minutes_per_game': int(stats.get('games', {}).get('minutes') or 90) // max(games.get('appearences', 1), 1),
            'shots_total': float(shots.get('total') or 0) / max(games.get('appearences', 1), 1),
            'shots_on': float(shots.get('on') or 0) / max(games.get('appearences', 1), 1),
            'passes_total': float(passes.get('total') or 0) / max(games.get('appearences', 1), 1),
            'passes_accuracy': int(passes.get('accuracy') or 75),
            'is_starter': games.get('lineups') > games.get('appearences', 0) * 0.7  # 70%+ titulaire
        }
    
    except Exception as e:
        print(f"Erreur récupération stats joueur {player_id}: {e}")
        return None

def get_match_lineups(fixture_id: int) -> Optional[Dict]:
    """Récupérer les compositions probables d'un match"""
    try:
        response = requests.get(
            f'{API_FOOTBALL_BASE}/fixtures/lineups',
            params={'fixture': fixture_id},
            headers=get_api_football_headers(),
            timeout=5
        )
        response.raise_for_status()
        
        data = response.json()
        return data.get('response', [])
    
    except Exception as e:
        print(f"Erreur récupération lineups: {e}")
        return None

# ============ PRÉDICTIONS ============

def prepare_player_features_for_future_match(
    player_id: int,
    league_id: int,
    team_id: int,
    opponent_id: int,
    is_home: bool
) -> Optional[Dict]:
    """
    Préparer les features pour un match À VENIR
    Utilise les stats historiques du joueur
    """
    
    # Récupérer stats moyennes du joueur
    player_stats = get_player_season_stats(player_id, league_id)
    if not player_stats:
        return None
    
    # Récupérer positions classement
    team_position = get_team_position(league_id, team_id)
    opponent_position = get_team_position(league_id, opponent_id)
    
    features = {
        'position_encoded': position_map.get(player_stats['position'], 3),
        'is_starter': 1 if player_stats['is_starter'] else 0,
        'is_home': 1 if is_home else 0,
        'minutes_played': player_stats['minutes_per_game'],
        'match_rating': player_stats['rating'],
        'shots_total': player_stats['shots_total'],
        'shots_on': player_stats['shots_on'],
        'shot_conversion': player_stats['shots_on'] / max(player_stats['shots_total'], 0.1),
        'passes_total': player_stats['passes_total'],
        'passes_accuracy': player_stats['passes_accuracy'],
        'team_position': team_position,
        'opp_position': opponent_position
    }
    
    return features

def predict_player(features: Dict) -> Optional[Dict]:
    """Prédire la probabilité qu'un joueur marque"""
    if xgb_model is None or lgbm_model is None:
        return None
    
    try:
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
    except Exception as e:
        print(f"Erreur prédiction: {e}")
        return None

# ============ ROUTES ============

@app.route('/')
def home():
    return jsonify({
        'status': 'ok',
        'service': 'Goal Scorer Predictions API',
        'version': '2.1',
        'season': f'{CURRENT_SEASON}-{CURRENT_SEASON + 1}',
        'model_performance': {
            'roc_auc': 0.986,
            'top_200_precision': '96.5%',
            'quasi_certain_precision': '82.8%'
        }
    })

@app.route('/api/health')
def health():
    return jsonify({
        'status': 'ok',
        'models_loaded': models_loaded,
        'api_configured': API_FOOTBALL_KEY != '',
        'season': f'{CURRENT_SEASON}-{CURRENT_SEASON + 1}'
    })

@app.route('/api/matches')
def get_upcoming_matches():
    """Récupérer les matchs À VENIR des 5 ligues (aujourd'hui + 7 jours)"""
    
    if not API_FOOTBALL_KEY:
        return jsonify({'error': 'Clé API manquante'}), 400
    
    try:
        from datetime import timedelta
        today = datetime.now()
        next_week = today + timedelta(days=7)
        
        response = requests.get(
            f'{API_FOOTBALL_BASE}/fixtures',
            params={
                'from': today.strftime('%Y-%m-%d'),
                'to': next_week.strftime('%Y-%m-%d'),
                'status': 'NS'  # ✅ NS = Not Started (matchs à venir)
            },
            headers=get_api_football_headers(),
            timeout=10
        )
        response.raise_for_status()
        
        data = response.json()
        matches = []
        
        if data.get('response'):
            for fixture in data['response']:
                league_id = fixture['league']['id']
                
                if league_id in LEAGUES:
                    match_info = {
                        'fixture_id': fixture['fixture']['id'],
                        'date': fixture['fixture']['date'],
                        'status': fixture['fixture']['status']['long'],
                        'home_team': {
                            'id': fixture['teams']['home']['id'],
                            'name': fixture['teams']['home']['name'],
                            'logo': fixture['teams']['home']['logo']
                        },
                        'away_team': {
                            'id': fixture['teams']['away']['id'],
                            'name': fixture['teams']['away']['name'],
                            'logo': fixture['teams']['away']['logo']
                        },
                        'league': {
                            'id': league_id,
                            'name': LEAGUES[league_id]['name'],
                            'country': LEAGUES[league_id]['country']
                        }
                    }
                    matches.append(match_info)
        
        return jsonify({
            'success': True,
            'count': len(matches),
            'period': f"{today.strftime('%Y-%m-%d')} to {next_week.strftime('%Y-%m-%d')}",
            'matches': matches
        })
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/predict-match/<int:fixture_id>', methods=['GET'])
def predict_match_scorers(fixture_id: int):
    """
    🎯 ENDPOINT PRINCIPAL : Prédire les top buteurs d'un match à venir
    Usage: GET /api/predict-match/12345
    """
    
    try:
        # 1. Récupérer infos du match
        response = requests.get(
            f'{API_FOOTBALL_BASE}/fixtures',
            params={'id': fixture_id},
            headers=get_api_football_headers(),
            timeout=5
        )
        response.raise_for_status()
        
        match_data = response.json()['response'][0]
        league_id = match_data['league']['id']
        home_team_id = match_data['teams']['home']['id']
        away_team_id = match_data['teams']['away']['id']
        
        # 2. Récupérer les compositions probables ou les joueurs des équipes
        response = requests.get(
            f'{API_FOOTBALL_BASE}/players/squads',
            params={'team': home_team_id},
            headers=get_api_football_headers(),
            timeout=5
        )
        home_squad = response.json()['response'][0]['players']
        
        response = requests.get(
            f'{API_FOOTBALL_BASE}/players/squads',
            params={'team': away_team_id},
            headers=get_api_football_headers(),
            timeout=5
        )
        away_squad = response.json()['response'][0]['players']
        
        # 3. Prédire pour les attaquants/milieux des deux équipes
        all_predictions = []
        
        for player in home_squad[:11]:  # Top 11
            features = prepare_player_features_for_future_match(
                player['id'],
                league_id,
                home_team_id,
                away_team_id,
                is_home=True
            )
            
            if features:
                prediction = predict_player(features)
                if prediction:
                    all_predictions.append({
                        'player_id': player['id'],
                        'player_name': player['name'],
                        'team': match_data['teams']['home']['name'],
                        'is_home': True,
                        'prediction': prediction
                    })
        
        for player in away_squad[:11]:
            features = prepare_player_features_for_future_match(
                player['id'],
                league_id,
                away_team_id,
                home_team_id,
                is_home=False
            )
            
            if features:
                prediction = predict_player(features)
                if prediction:
                    all_predictions.append({
                        'player_id': player['id'],
                        'player_name': player['name'],
                        'team': match_data['teams']['away']['name'],
                        'is_home': False,
                        'prediction': prediction
                    })
        
        # 4. Trier par probabilité
        all_predictions.sort(
            key=lambda x: x['prediction']['probability'],
            reverse=True
        )
        
        return jsonify({
            'success': True,
            'match': {
                'fixture_id': fixture_id,
                'date': match_data['fixture']['date'],
                'home_team': match_data['teams']['home']['name'],
                'away_team': match_data['teams']['away']['name'],
                'league': LEAGUES[league_id]['name']
            },
            'top_scorers': all_predictions[:10],  # Top 10
            'total_predictions': len(all_predictions)
        })
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/test')
def test():
    return jsonify({
        'message': 'API opérationnelle !',
        'season': f'{CURRENT_SEASON}-{CURRENT_SEASON + 1}',
        'models_loaded': models_loaded
    })

if __name__ == '__main__':
    app.run(debug=True)
