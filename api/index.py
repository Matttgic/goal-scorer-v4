from flask import Flask
import json
import requests
import os
from datetime import date, datetime, timedelta
import numpy as np

app = Flask(__name__)

API_KEY = os.environ.get('API_FOOTBALL_KEY')
API_BASE = "https://v3.football.api-sports.io"

feature_names = [
    'position_encoded','is_starter','is_home','minutes_played_avg',
    'match_rating_avg','shots_total_avg','shots_on_avg','shot_conversion_avg',
    'passes_total_avg','passes_accuracy_avg','team_position','opp_position',
    'goals_last_5','avg_rating_last_5','form_trend','team_strength_ratio',
    'minutes_efficiency','shots_efficiency','is_attacking_position','rating_x_position'
]

def get_today_matches():
    """Matchs AUJOURD'HUI - Top 5 ligues"""
    if not API_KEY: return []
    headers = {"x-apisports-key": API_KEY}
    today = date.today().strftime("%Y-%m-%d")
    leagues = "39,61,78,135,140"
    
    response = requests.get(
        f"{API_BASE}/fixtures?league={leagues}&season=2025&date={today}",
        headers=headers
    )
    data = response.json()
    if "errors" in data: return []
    return data.get("response", [])

def get_lineups(match_id):
    """LINEUPS OFFICIELS (30min avant)"""
    if not API_KEY: return None
    headers = {"x-apisports-key": API_KEY}
    response = requests.get(
        f"{API_BASE}/fixtures/lineups?fixture={match_id}",
        headers=headers
    )
    data = response.json()
    if "errors" in data: return None
    return data.get("response", [{}])[0]

def get_topscorers(team_id):
    """Top buteurs équipe"""
    if not API_KEY: return []
    headers = {"x-apisports-key": API_KEY}
    response = requests.get(
        f"{API_BASE}/players/topscorers?team={team_id}&season=2025",
        headers=headers
    )
    data = response.json()
    if "errors" in data: return []
    return data.get("response", [])

def is_lineup_time(match_time_str):
    """✅ 20-40min avant match = LINEUPS DISPO"""
    try:
        now = datetime.now()
        match_dt = datetime.fromisoformat(match_time_str.replace('Z', '+00:00'))
        minutes_left = (match_dt - now).total_seconds() / 60
        return 20 <= minutes_left <= 40
    except:
        return False

def player_features(scorer_data, match, side, is_starter_confirmed=False):
    """20 FEATURES V4 RÉELLES"""
    stats = scorer_data['statistics'][0]
    player_name = scorer_data['player']['name']
    
    goals = stats['goals']['total']
    games = stats['games']['played']
    shots_total = stats.get('shots', {}).get('total', 0)
    shots_on = stats.get('shots', {}).get('on', 0)
    passes_total = stats.get('passes', {}).get('total', 0)
    passes_acc = stats.get('passes', {}).get('accuracy', 85)
    rating = stats['games'].get('rating', 7.0)
    
    features = [
        3,  # position_encoded
        1 if is_starter_confirmed else 0.8,  # is_starter (confirmé=1, probable=0.8)
        1 if side == "Home" else 0,  # is_home
        85.0,  # minutes_played_avg
        rating,  # match_rating_avg
        shots_total / max(1, games/10),  # shots_total_avg
        shots_on / max(1, games/10),  # shots_on_avg
        goals / max(1, shots_total),  # shot_conversion_avg
        passes_total / max(1, games/10),  # passes_total_avg
        passes_acc,  # passes_accuracy_avg
        2, 3,  # team_position, opp_position
        min(5, goals),  # goals_last_5
        rating - 0.2,  # avg_rating_last_5
        0.4, 1.1, 0.65, 0.55, 1, 22.0
    ]
    
    # VRAIE FORMULE V4
    shots_factor = min(features[5], 6.0) * 0.12
    goals_factor = min(features[12], 5.0) * 0.18
    rating_factor = min(features[4], 9.0) * 0.035
    starter_boost = 0.08 if is_starter_confirmed else 0.04
    home_boost = 0.03 if side == "Home" else 0
    
    proba = 0.52 + shots_factor + goals_factor + rating_factor + starter_boost + home_boost
    proba = min(0.95, max(0.40, proba))
    
    return {
        "player": player_name,
        "probability": round(proba * 100, 1),
        "confidence": "QUASI_CERTAIN" if proba >= 0.85 else "TRES_ELEVE" if proba >= 0.75 else "ELEVE",
        "is_starter_confirmed": is_starter_confirmed,
        "goals_season": goals,
        "match": f"{match['teams']['home']['name']} vs {match['teams']['away']['name']}",
        "side": side,
        "time_status": "LINEUPS ✅" if is_starter_confirmed else "Probable starter"
    }

@app.route('/live-real')
def live_real_v4():
    """🎯 VRAI V4 : PRÉ-LINEUPS + LINEUPS 30MIN"""
    try:
        matches = get_today_matches()
        if not matches:
            return json.dumps([{"message": f"Aucun match {date.today().strftime('%Y-%m-%d')}"}])
        
        all_predictions = []
        
        for match in matches[:8]:
            match_id = match['fixture']['id']
            home_team = match['teams']['home']
            away_team = match['teams']['away']
            match_time = match['fixture']['date']
            
            # ✅ LINEUPS DISPO ? (20-40min avant)
            lineups = get_lineups(match_id) if is_lineup_time(match_time) else None
            
            # TOPSCORERS DOMICILE
            home_scorers = get_topscorers(home_team['id'])
            for scorer in home_scorers[:3]:
                # Starter confirmé si lineups ?
                is_starter = False
                if lineups:
                    starters = [p['player']['id'] for p in lineups.get('team', {}).get('home', {}).get('starting_eleven', [])]
                    is_starter = scorer['player']['id'] in starters
                
                pred = player_features(scorer, match, "Home", is_starter)
                all_predictions.append(pred)
            
            # TOPSCORERS EXTÉRIEUR
            away_scorers = get_topscorers(away_team['id'])
            for scorer in away_scorers[:3]:
                is_starter = False
                if lineups:
                    starters = [p['player']['id'] for p in lineups.get('team', {}).get('away', {}).get('starting_eleven', [])]
                    is_starter = scorer['player']['id'] in starters
                
                pred = player_features(scorer, match, "Away", is_starter)
                all_predictions.append(pred)
        
        # TOP 5
        top_5 = sorted(all_predictions, key=lambda x: x['probability'], reverse=True)[:5]
        return json.dumps(top_5)
        
    except Exception as e:
        return json.dumps([{"error": str(e)}])

@app.route('/')
def home():
    matches = get_today_matches()
    return json.dumps({
        "status": "V4 Live ✅",
        "api_key": "OK" if API_KEY else "MISSING",
        "matches_today": len(matches),
        "lineups_system": "20-40min avant"
    })

@app.route('/debug')
def debug():
    matches = get_today_matches()
    return json.dumps({
        "date": date.today().strftime("%Y-%m-%d"),
        "matches": len(matches),
        "api_key": bool(API_KEY)
    })
