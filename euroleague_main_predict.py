import logging
import os
import pandas as pd
import numpy as np
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.ensemble import GradientBoostingRegressor
from glob import glob
import joblib

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# File paths and configurations
player_data_path = "euroleague_data_players_week_*.xlsx"
defense_data_file = "euroleague_data_def_vs_pos_{}.xlsx"
latest_week = 10
upcoming_week = 11
model_file = "euroleague_model.pkl"
scaler_file = "scaler.pkl"
output_file = f"euroleague_predictions_week_{upcoming_week}.xlsx"

# Team mapping
data_mapping = {
    "FC Bayern Munich": "BAY", "FC Barcelona": "BAR", "Zalgiris Kaunas": "ZAL",
    "Panathinaikos AKTOR Athens": "PAO", "Real Madrid": "RMB", "ALBA Berlin": "BER",
    "EA7 Emporio Armani Milan": "EA7", "Maccabi Playtika Tel Aviv": "MTA",
    "Olympiacos Piraeus": "OLY", "Baskonia Vitoria-Gasteiz": "BKN",
    "Crvena Zvezda Meridianbet Belgrade": "CZV", "Partizan Mozzart Bet Belgrade": "PAR",
    "AS Monaco": "ASM", "LDLC ASVEL Villeurbanne": "ASV", "Anadolu Efes Istanbul": "EFS",
    "Paris Basketball": "PBB", "Virtus Segafredo Bologna": "VIR", "Fenerbahce Beko Istanbul": "FBB"
}

# Helper functions
def load_historical_data():
    logging.info("Loading historical player data...")
    player_files = glob(player_data_path)
    all_data = []
    for file in player_files:
        week = int(file.split('_')[-1].split('.')[0])
        df = pd.read_excel(file)
        df['Week'] = week
        all_data.append(df)
    return pd.concat(all_data, ignore_index=True)

def load_defense_data():
    logging.info("Loading defense data...")
    defense_data = {}
    for position in ['Guards', 'Forwards', 'Centers']:
        df = pd.read_excel(defense_data_file.format(position))
        df.rename(columns={'Team Name': 'Team'}, inplace=True)
        df['Team'] = df['Team'].map(data_mapping)
        defense_data[position] = df.set_index('Team')['Average'].to_dict()
    return defense_data

def map_defense_value(row, defense_data):
    position_map = {'G': 'Guards', 'F': 'Forwards', 'C': 'Centers'}
    position = position_map.get(row['Pos'], None)
    if position and row['Upcoming_Opponent'] in defense_data[position]:
        return defense_data[position][row['Upcoming_Opponent']]
    return 0

def preprocess_data(df, defense_data, predict=False, scaler=None):
    df = df.dropna(subset=['PLUS', 'avg_PLUS', 'avg_FPT', 'Team', 'Home_Away', 'Upcoming_Opponent']).copy()

    df.loc[:, 'PLUS'] = df['PLUS'].replace({'\+': '', '−': '-'}, regex=True).astype(float)
    df.loc[:, 'avg_PLUS'] = df['avg_PLUS'].replace({'\+': '', '−': '-'}, regex=True).astype(float)
    df.loc[:, 'Home_Away'] = df['Home_Away'].map({'home': 1, 'away': 0}).astype(int)
    df.loc[:, 'Position_Defense_Avg'] = df.apply(lambda x: map_defense_value(x, defense_data), axis=1)

    label_encoders = {}
    for col in ['Team', 'Upcoming_Opponent']:
        le = LabelEncoder()
        df.loc[:, col] = le.fit_transform(df[col])
        label_encoders[col] = le

    scaled_features = ['avg_FPT', 'avg_PLUS', 'Position_Defense_Avg']
    if not predict:
        scaler = StandardScaler()
        df.loc[:, scaled_features] = scaler.fit_transform(df[scaled_features])
        joblib.dump(scaler, scaler_file)
    else:
        if scaler is None:
            scaler = joblib.load(scaler_file)
        df.loc[:, scaled_features] = scaler.transform(df[scaled_features])

    if predict and 'FPT' in df.columns:
        df['Reference_FPT'] = df['FPT']
        df.drop(columns=['FPT'], inplace=True)

    return df, label_encoders, scaler

# Load data
historical_data = load_historical_data()
defense_data = load_defense_data()

train_data = historical_data[historical_data['Week'] < latest_week]
logging.info("Preprocessing training data...")
train_data, label_encoders, scaler = preprocess_data(train_data, defense_data)

features = ['avg_FPT', 'avg_PLUS', 'Position_Defense_Avg', 'Home_Away']
target = 'FPT'

X_train, y_train = train_data[features], train_data[target]

if os.path.exists(model_file):
    logging.info("Loading saved model...")
    model = joblib.load(model_file)
else:
    logging.info("Training the prediction model...")
    model = GradientBoostingRegressor(n_estimators=500, learning_rate=0.01, max_depth=5, random_state=42)
    model.fit(X_train, y_train)
    joblib.dump(model, model_file)

# Prepare data for predictions
latest_week_data = historical_data[historical_data['Week'] == latest_week]

logging.info("Preparing data for predictions...")
latest_week_data, _, scaler = preprocess_data(latest_week_data, defense_data, predict=True, scaler=scaler)

X_pred = latest_week_data[features]

# Predict
logging.info("Predicting for upcoming week...")
latest_week_data['Predicted_FPT'] = model.predict(X_pred)

logging.info(f"Saving predictions to {output_file}...")
latest_week_data.to_excel(output_file, index=False)

comparison = latest_week_data[['Player', 'Reference_FPT', 'Predicted_FPT']]
print(comparison.head())
