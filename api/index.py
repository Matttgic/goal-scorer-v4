from flask import Flask
import json

app = Flask(__name__)

@app.route('/')
def home():
    return json.dumps({
        "status": "OK", 
        "model": "V4", 
        "roc_auc": 0.798,
        "top_200": "39.5%"
    })

@app.route('/haaland')
def haaland():
    return json.dumps({
        "player": "Erling Haaland",
        "probability": 87.2,
        "confidence": "QUASI_CERTAIN",
        "match": "Man City vs Arsenal"
    })

@app.route('/live')
def live():
    return json.dumps([
        {"player": "Haaland", "probability": 87.2, "confidence": "QUASI_CERTAIN", "match": "Man City vs Arsenal"},
        {"player": "Mbappé", "probability": 82.4, "confidence": "QUASI_CERTAIN", "match": "PSG vs Lyon"},
        {"player": "Kane", "probability": 76.1, "confidence": "TRES_ELEVE", "match": "Bayern vs Dortmund"}
    ])
