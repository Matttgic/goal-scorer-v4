from flask import Flask
import json
import requests
import os
from datetime import date, datetime
import numpy as np

app = Flask(__name__)

API_KEY = os.environ.get('API_FOOTBALL_KEY')
API_BASE = "https://v3.football.api-sports.io"

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
    """20-40min avant match = LINEUPS DISPO"""
    try:
        now = datetime.now()
        match_dt = datetime.fromisoformat(match_time_str.replace('Z', '+00:00'))
        minutes_left = (match_dt - now).total_seconds() / 60
        return 20 <= minutes_left <= 40
    except:
        return False

def player_features(scorer_data, match, side, is_starter_confirmed=False):
    """20 FEATURES V4 RÉELLES → Prédiction"""
    stats = scorer_data['statistics'][0]
    player_name = scorer_data['player']['name']
    
    goals = stats['goals']['total']
    games = stats['games']['played']
    shots_total = stats.get('shots', {}).get('total', 0)
    shots_on = stats.get('shots', {}).get('on', 0)
    passes_total = stats.get('passes', {}).get('total', 0)
    passes_acc = stats.get('passes', {}).get('accuracy', 85)
    rating = stats['games'].get('rating', 7.0)
    
    # VRAIE FORMULE V4
    shots_factor = min(shots_total / max(1, games/10), 6.0) * 0.12
    goals_factor = min(goals, 5.0) * 0.18
    rating_factor = min(rating, 9.0) * 0.035
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
            
            # LINEUPS DISPO ? (20-40min avant)
            lineups = get_lineups(match_id) if is_lineup_time(match_time) else None
            
            # TOPSCORERS DOMICILE
            home_scorers = get_topscorers(home_team['id'])
            for scorer in home_scorers[:3]:
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
        "lineups_system": "20-40min avant",
        "test": "/debug"
    })

@app.route('/debug')
def debug_full():
    """🔍 DEBUG COMPLET - Toutes les dates"""
    today = date.today().strftime("%Y-%m-%d")
    headers = {"x-apisports-key": API_KEY} if API_KEY else {}
    
    test_dates = [today, "2025-12-22", "2025-12-21", "2025-12-20"]
    results = {}
    
    for d in test_dates:
        resp = requests.get(
            f"{API_BASE}/fixtures?league=39&season=2025&date={d}",
            headers=headers
        )
        data = resp.json()
        results[d] = {
            "count": len(data.get("response", [])),
            "errors": data.get("errors", None)
        }
    
    return json.dumps({
        "today": today,
        "api_key": bool(API_KEY),
        "date_tests": results,
        "next_test": "/test-weekend",
        "live_real": "/live-real"
    })

@app.route('/test-weekend')
def test_weekend():
    """🎯 MATCHS WEEK-END PROCHE"""
    if not API_KEY: return json.dumps({"error": "NO_KEY"})
    
    headers = {"x-apisports-key": API_KEY}
    dates = ["2025-12-22", "2025-12-21", "2025-12-20"]
    
    all_matches = []
    for d in dates:
        response = requests.get(
            f"{API_BASE}/fixtures?league=39,61,78,135,140&season=2025&date={d}",
            headers=headers
        )
        data = response.json()
        if "errors" not in data:
            all_matches.extend(data.get("response", []))
    
    return json.dumps({
        "weekend_matches": len(all_matches),
        "sample": [f"{m['teams']['home']['name']} vs {m['teams']['away']['name']}" for m in all_matches[:5]],
        "full_list": len(all_matches) > 0
    })

if __name__ == "__main__":
    app.run(debug=True)
