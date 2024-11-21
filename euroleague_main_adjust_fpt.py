import logging

import os

import pandas as pd

from datetime import datetime

from itertools import combinations

import concurrent.futures

import heapq

# Configure logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# File paths and constants

data_file = "euroleague_data_players_week_10.xlsx"

timestamp_file = "data_timestamp.txt"

coach_data_file = "coach.xlsx"

defense_data_file = "euroleague_data_def_vs_pos_all.xlsx"

avg_data_file = "euroleague_data_players_average.xlsx"

# Constraints

credit_limit = 100

max_players_per_team = 11

positions_needed = {'C': 2, 'F': 4, 'G': 4, 'HC': 1}

max_unique_teams = 1

# Track unique teams

unique_teams = set()

def create_team_identifier(team):

    """Creates a unique identifier for a team based on player names to ensure no duplicate teams."""

    return tuple(sorted(player.Player for player in team))

def load_data():

    data_mapping = {

        "FC Bayern Munich": "BAY",

        "FC Barcelona": "BAR",

        "Zalgiris Kaunas": "ZAL",

        "Panathinaikos AKTOR Athens": "PAO",

        "Real Madrid": "RMB",

        "ALBA Berlin": "BER",

        "EA7 Emporio Armani Milan": "EA7",

        "Maccabi Playtika Tel Aviv": "MTA",

        "Olympiacos Piraeus": "OLY",

        "Baskonia Vitoria-Gasteiz": "BKN",

        "Crvena Zvezda Meridianbet Belgrade": "CZV",

        "Partizan Mozzart Bet Belgrade": "PAR",

        "AS Monaco": "ASM",

        "LDLC ASVEL Villeurbanne": "ASV",

        "Anadolu Efes Istanbul": "EFS",

        "Paris Basketball": "PBB",

        "Virtus Segafredo Bologna": "VIR",

        "Fenerbahce Beko Istanbul": "FBB"

    }

    # Load data and add coach data if available

    if os.path.exists(data_file):

        df = pd.read_excel(data_file)

    else:

        raise FileNotFoundError("Player data file is missing.")
    # Load and add avf_FPT and avg_CR to table
    
    if os.path.exists(avg_data_file):
        # Load the average data
        avg_df = pd.read_excel(avg_data_file)
        
        # Rename columns for clarity
        avg_df.rename(columns={'FPT': 'avg_FPT', 'CR': 'avg_CR', 'PLUS': 'avg_PLUS'}, inplace=True)
        
        # Log the contents of avg_df before merging
        logging.info(f'Avg before adding: \n{avg_df}')
        
        # Select only necessary columns from avg_df
        avg_columns_to_merge = avg_df[['Player', 'Pos', 'Team', 'avg_PLUS', 'avg_FPT']]
        
        # Perform the merge
        df = pd.merge(
            df,
            avg_columns_to_merge,
            on=['Player', 'Pos', 'Team'],  # Ensure these columns exist in both DataFrames
            how='left'
        )
        
        # Log the contents of df after merging
        logging.info(f'Data after merging avg_FPT: \n{df.head()}')


    # Load and concatenate coach data if available

    if os.path.exists(coach_data_file):

        coach_df = pd.read_excel(coach_data_file)

        coach_df.rename(columns={'coach_name': 'Player', 'team_name': 'Team', 'fantasy_pts': 'FPT', 'quotation': 'CR', 'avg_fpt': 'avg_FPT'}, inplace=True)

        coach_df['Pos'] = 'HC'

        df = pd.concat([df, coach_df], ignore_index=True)

        logging.info("Coach data added to player data.")

    # Apply team abbreviation mapping to the 'Team' column after concatenation

    df['Team'] = df['Team'].map(data_mapping).fillna(df['Team']) # Keeps original name if not in mapping

    logging.info(df["Team"])

    # Convert FPT and CR to numeric and filter by calculated FPT/CR

    df['FPT'] = pd.to_numeric(df['FPT'], errors='coerce')

    df['CR'] = pd.to_numeric(df['CR'], errors='coerce')

    df['FPT/CR'] = df['FPT'] / df['CR']

    return df

def filter_players(df):

    min_fpt = 10

    player_ratio_threshold = 0.5

    coach_ratio_threshold = 0.2

    df = df[((df['Pos'] != 'HC') & (df['FPT'] >= min_fpt) & (df['CR'] >= 4) & (df['FPT/CR'] > player_ratio_threshold)) |

            ((df['Pos'] == 'HC') & (df['FPT'] >= min_fpt) & (df['CR'] >= 4) & (df['FPT/CR'] > coach_ratio_threshold))]

    logging.info(f"Initial number of players after filtering: {len(df)}")

    return df

def load_defense_data(player_df):

    # Dynamically calculate alpha values based on league defense data

    defense_data = {}

    data_mapping = {

        "FC Bayern Munich": "BAY",

        "FC Barcelona": "BAR",

        "Zalgiris Kaunas": "ZAL",

        "Panathinaikos AKTOR Athens": "PAO",

        "Real Madrid": "RMB",

        "ALBA Berlin": "BER",

        "EA7 Emporio Armani Milan": "EA7",

        "Maccabi Playtika Tel Aviv": "MTA",

        "Olympiacos Piraeus": "OLY",

        "Baskonia Vitoria-Gasteiz": "BKN",

        "Crvena Zvezda Meridianbet Belgrade": "CZV",

        "Partizan Mozzart Bet Belgrade": "PAR",

        "AS Monaco": "ASM",

        "LDLC ASVEL Villeurbanne": "ASV",

        "Anadolu Efes Istanbul": "EFS",

        "Paris Basketball": "PBB",

        "Virtus Segafredo Bologna": "VIR",

        "Fenerbahce Beko Istanbul": "FBB"

    }

    for position, pos_label in zip(['Guards', 'Forwards', 'Centers'], ['G', 'F', 'C']):

        # Load defense data for each position

        df = pd.read_excel(defense_data_file, sheet_name=position)

        # Apply the team abbreviation mapping to the "Team Name" column

        df['Team Name'] = df['Team Name'].map(data_mapping)

        # Calculate league average and standard deviation for the defensive 'Average' column

        avg_defense = df['Average'].mean()

        std_defense = df['Average'].std()

        # Calculate average fantasy points for the position from player data

        avg_fantasy_points = player_df[player_df['Pos'] == pos_label]['FPT'].mean()

        # Estimate the impact ratio dynamically

        alpha = (3 * std_defense / avg_defense) / avg_fantasy_points

        # Store the alpha value and team-based defense data for the position

        defense_data[position] = {'data': df.set_index('Team Name')['Average'].to_dict(), 'alpha': alpha}

    logging.info(f"Defense data: {defense_data}")

    return defense_data

def adjust_fantasy_points(player, opponent_team, defense_data):

    # Adjust FPT based on the opponent's defensive strength against the player's position

    position_map = {'G': 'Guards', 'F': 'Forwards', 'C': 'Centers'}

    position = position_map.get(player.Pos)

    home_away = player.Home_Away

    raw_fpt = player.FPT

    if home_away == 'home':

        logging.info(f'First adjustment FPT: {raw_fpt}')

        adjusted_fpt = raw_fpt * 1.12

        logging.info(f'Second adjustment FPT: {adjusted_fpt}')

    else:

        logging.info(f'First adjustment FPT: {raw_fpt}')

        adjusted_fpt = raw_fpt * 0.88

        logging.info(f'Second adjustment FPT: {adjusted_fpt}')

    if not position:

        return adjusted_fpt # No adjustment if position is not among G, F, C

    opponent_defense = defense_data[position]['data'].get(opponent_team, 0)

    # logging.info(f"Opponent defense: {defense_data[position]['data'].get(opponent_team, 0)}")

    alpha = defense_data[position]['alpha']

    league_avg_defense = sum(defense_data[position]['data'].values()) / len(defense_data[position]['data'].values())

    # Adjust based on whether opponent defense is above or below league average

    if opponent_defense > league_avg_defense:

        # Opponent is weaker in defending this position, boost FPT

        adjusted_fpt = adjusted_fpt * (1 + alpha * (opponent_defense - league_avg_defense) / league_avg_defense)

    else:

        # Opponent is stronger in defending this position, reduce FPT

        adjusted_fpt = adjusted_fpt * (1 - alpha * (league_avg_defense - opponent_defense) / league_avg_defense)

    # Logging for validation

    logging.info(f"Adjusted FPT for {player.Player} (Pos: {player.Pos}, Opponent: {opponent_team}): "

                 f"Raw FPT={raw_fpt}, Opponent Defense={opponent_defense}, Alpha={alpha}, "

                 f"Adjusted FPT={adjusted_fpt}")

    return adjusted_fpt

# Save dataframe with Adjusted FPT and adjusted FPT/CR and added average FPT and CR columns

def select_top_players(df, defense_data):

    max_player_per_pos = 8

    max_coach_per_pos = 5

    # Use 'Upcoming_Opponent' to adjust FPT and filter top players

    df['Adjusted_FPT'] = round(df.apply(lambda x: adjust_fantasy_points(x, x.Upcoming_Opponent, defense_data), axis=1), 2)

    df['Adj_FPT/CR'] = df['Adjusted_FPT'] / df['CR']

    centers = df[df['Pos'] == 'C'].nlargest(max_player_per_pos, 'Adj_FPT/CR')

    forwards = df[df['Pos'] == 'F'].nlargest(max_player_per_pos, 'Adj_FPT/CR')

    guards = df[df['Pos'] == 'G'].nlargest(max_player_per_pos, 'Adj_FPT/CR')

    head_coaches = df[df['Pos'] == 'HC'].nlargest(max_coach_per_pos, 'Adj_FPT/CR')

    logging.info(f"Players after filtering: Centers={len(centers)}, Forwards={len(forwards)}, Guards={len(guards)}, Coaches={len(head_coaches)}")

    df.to_excel("euroleague_data_players_filtered_adjusted_average.xlsx")

    logging.info("Saved adjfpt")

    return centers, forwards, guards, head_coaches

# Main script execution

df = load_data()

# df = filter_players(df)

defense_data = load_defense_data(df)

centers, forwards, guards, head_coaches = select_top_players(df, defense_data)