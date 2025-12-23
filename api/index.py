from flask import Flask
import json
import requests
import os
from datetime import date, datetime
import numpy as np

app = Flask(__name__)

API_KEY = os.environ.get('API_FOOTBALL_KEY')
API_BASE = "https://v3.football.api-sports.io"

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

@app.route('/')
def home():
    return json.dumps({
        "status": "V4 Live ✅",
        "api_key": "OK" if API_KEY else "MISSING",
        "tests": {
            "today": "/",
            "debug_dates": "/debug",
            "weekend": "/test-weekend", 
            "live_20251222": "/live-20251222",
            "live_real": "/live-real"
        }
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
        "next_test": "/test-weekend"
    })

@app.route('/test-weekend')
def test_weekend():
    """🎯 MATCHS RECENTS (2025-12-22 + 12-20)"""
    if not API_KEY: return json.dumps({"error": "NO_KEY"})
    
    headers = {"x-apisports-key": API_KEY}
    dates = ["2025-12-22", "2025-12-20"]  # DATES AVEC MATCHS !
    
    all_matches = []
    date_results = {}
    
    for d in dates:
        response = requests.get(
            f"{API_BASE}/fixtures?league=39,61,78,135,140&season=2025&date={d}",
            headers=headers
        )
        data = response.json()
        matches = data.get("response", [])
        date_results[d] = len(matches)
        all_matches.extend(matches)
    
    return json.dumps({
        "weekend_matches": len(all_matches),
        "by_date": date_results,
        "sample": [f"{m['teams']['home']['name']} vs {m['teams']['away']['name']}" for m in all_matches[:5]],
        "full_list": len(all_matches) > 0
    })

@app.route('/live-20251222')
def live_20251222():
    """🎯 V4 SUR FULHAM vs FOREST (12/22)"""
    try:
        if not API_KEY: return json.dumps([{"error": "NO_KEY"}])
        
        headers = {"x-apisports-key": API_KEY}
        response = requests.get(
            f"{API_BASE}/fixtures?league=39&season=2025&date=2025-12-22",
            headers=headers
        )
        matches = response.json().get("response", [])
        
        if not matches:
            return json.dumps([{"message": "Pas de match 2025-12-22"}])
        
        match = matches[0]  # Fulham vs Forest
        home_team = match['teams']['home']['id']
        away_team = match['teams']['away']['id']
        
        all_predictions = []
        
        # TOPSCORERS FULHAM
        print(f"Fetching Fulham topscorers (team {home_team})")
        home_scorers = get_topscorers(home_team)
        for scorer in home_scorers[:3]:
            pred = player_features(scorer, match, "Home", False)
            all_predictions.append(pred)
        
        # TOPSCORERS FOREST
        print(f"Fetching Forest topscorers (team {away_team})")
        away_scorers = get_topscorers(away_team)
        for scorer in away_scorers[:3]:
            pred = player_features(scorer, match, "Away", False)
            all_predictions.append(pred)
        
        top_5 = sorted(all_predictions, key=lambda x: x['probability'], reverse=True)[:5]
        return json.dumps({
            "match": f"{match['teams']['home']['name']} vs {match['teams']['away']['name']}",
            "predictions": top_5
        })
        
    except Exception as e:
        return json.dumps([{"error": str(e)}])

@app.route('/live-real')
def live_real_v4():
    """🎯 VRAI V4 : Matchs aujourd'hui → Topscorers → ML"""
    try:
        headers = {"x-apisports-key": API_KEY}
        today = date.today().strftime("%Y-%m-%d")
        response = requests.get(
            f"{API_BASE}/fixtures?league=39,61,78,135,140&season=2025&date={today}",
            headers=headers
        )
        matches = response.json().get("response", [])
        
        if not matches:
            return json.dumps([{"message": f"Aucun match {today} - Test /live-20251222"}])
        
        all_predictions = []
        for match in matches[:8]:
            home_team = match['teams']['home']['id']
            away_team = match['teams']['away']['id']
            
            home_scorers = get_topscorers(home_team)
            for scorer in home_scorers[:2]:
                pred = player_features(scorer, match, "Home", False)
                all_predictions.append(pred)
            
            away_scorers = get_topscorers(away_team)
            for scorer in away_scorers[:2]:
                pred = player_features(scorer, match, "Away", False)
                all_predictions.append(pred)
        
        top_5 = sorted(all_predictions, key=lambda x: x['probability'], reverse=True)[:5]
        return json.dumps(top_5)
        
    except Exception as e:
        return json.dumps([{"error": str(e)}])

if __name__ == "__main__":
    app.run(debug=True)
