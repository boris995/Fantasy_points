#main
import logging

import os

import pandas as pd

from datetime import datetime

from selenium import webdriver

from selenium.webdriver.edge.service import Service

from selenium.webdriver.edge.options import Options

from selenium.webdriver.common.by import By

from webdriver_manager.microsoft import EdgeChromiumDriverManager

from selenium.webdriver.support.ui import WebDriverWait

from selenium.webdriver.support import expected_conditions as EC

from itertools import combinations

import concurrent.futures

import heapq

# Configure logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# File paths

data_file = "euroleague_data_players_filtered_adjusted_average.xlsx"

timestamp_file = "data_timestamp.txt"

coach_data_file = "coach.xlsx"

# Constraints

credit_limit = 97.5

max_players_per_team = 11

positions_needed = {'C': 2, 'F': 4, 'G': 4, 'HC': 1}

max_unique_teams = 3

# Track unique teams

unique_teams = set()

def create_team_identifier(team):

    """Creates a unique identifier for a team based on player names to ensure no duplicate teams."""

    return tuple(sorted(player.Player for player in team))

def load_data():

    # Load or scrape data

    data_up_to_date = False

    if os.path.exists(data_file) :
    
        df = pd.read_excel(data_file)

    # Convert FPT and CR to numeric and apply filters

    df['avg_FPT'] = pd.to_numeric(df['avg_FPT'], errors='coerce')

    df['CR'] = pd.to_numeric(df['CR'], errors='coerce')

    df['avg_FPT/CR'] = df['avg_FPT'] / df['CR']

    return df

def filter_players(df):

    # Define thresholds for players and coaches separately
    min_fpt_avg = 7
    
    min_fpt_coach_avg = 0
    
    player_ratio_threshold = 0.3
    
    coach_ratio_threshold = 0.2

    # Apply filtering with separate thresholds

    df = df[((df['Pos'] != 'HC') & (df['avg_FPT'] >= min_fpt_avg) & (df['CR'] >= 4) & (df['avg_FPT/CR'] > player_ratio_threshold)) |

            ((df['Pos'] == 'HC') & (df['avg_FPT'] >= min_fpt_coach_avg) & (df['CR'] >= 4) & (df['avg_FPT/CR'] > coach_ratio_threshold))]
    
    # Log the current player pool size

    logging.info(f"Initial number of players after filtering: {len(df)}")

    return df

def select_top_players(df):

    # Further filter by selecting top N players in each position based on FPT/CR

    top_n_per_position = 8

    top_n_per_position_coach = 5

    centers = df[df['Pos'] == 'C'].nlargest(top_n_per_position, 'avg_FPT/CR')

    forwards = df[df['Pos'] == 'F'].nlargest(top_n_per_position, 'avg_FPT/CR')

    guards = df[df['Pos'] == 'G'].nlargest(top_n_per_position, 'avg_FPT/CR')

    head_coaches = df[df['Pos'] == 'HC'].nlargest(top_n_per_position_coach, 'avg_FPT/CR')

    logging.info(f"Players per position after filtering: Centers={len(centers)}, Forwards={len(forwards)}, Guards={len(guards)}, Head Coaches={len(head_coaches)}")

    return centers, forwards, guards, head_coaches

def create_optimal_fantasy_team(centers, forwards, guards, head_coaches):

    logging.info("Starting team selection using optimized heuristic approach...")


    # Use a heap to maintain the top 3 teams

    top_teams = []

    possible_combinations = 0


    def process_combination(c_combo, f_combo, g_combo):

        nonlocal possible_combinations

        for hc in head_coaches.itertuples(index=False):

            team = list(c_combo) + list(f_combo) + list(g_combo) + [hc]

            team_id = create_team_identifier(team)

            if team_id in unique_teams:

                continue


            unique_teams.add(team_id)

            possible_combinations += 1

            total_cr = sum(player.CR for player in team)

            if total_cr > credit_limit:

                continue

            total_fpt = sum(player.FPT for player in team)

            total_adj_fpt = sum(player.Adjusted_FPT for player in team)

            team_counts = {}

            for player in team:

                team_counts[player.Team] = team_counts.get(player.Team, 0) + 1

            if all(count <= max_players_per_team for count in team_counts.values()):

                # Use a heap to keep only the top 3 teams

                if len(top_teams) < max_unique_teams:

                    heapq.heappush(top_teams, (total_fpt, team))

                else:

                    heapq.heappushpop(top_teams, (total_fpt, team))

                logging.info(f"Combination checked: AdjFP:{total_adj_fpt} FPT={total_fpt}, CR={total_cr}")

    # Parallel processing with a ThreadPoolExecutor

    with concurrent.futures.ThreadPoolExecutor() as executor:

        for c_combo in combinations(centers.itertuples(index=False), positions_needed['C']):

            for f_combo in combinations(forwards.itertuples(index=False), positions_needed['F']):

                for g_combo in combinations(guards.itertuples(index=False), positions_needed['G']):

                    executor.submit(process_combination, c_combo, f_combo, g_combo)

    logging.info(f"Total possible team combinations checked: {possible_combinations}")

    return [team for _, team in sorted(top_teams, reverse=True)]

# Main execution

df = load_data()

df = filter_players(df)

centers, forwards, guards, head_coaches = select_top_players(df)

# Generate up to 3 unique fantasy teams

logging.info("Generating up to 3 unique optimal fantasy teams...")

fantasy_teams = create_optimal_fantasy_team(centers, forwards, guards, head_coaches)

# Save best teams to file

teams_data = {}

for idx, team in enumerate(fantasy_teams, start=1):

    team_name = f"Team {idx}"

    team_details = []

    for player in team:

        team_details.append({

            "Player": player.Player,

            "Position": player.Pos,

            "Team": player.Team,

            "FPT": player.FPT,

            "CR": player.CR,

            "avg_FPT": player.avg_FPT

        })

    # Convert team details to a DataFrame for this team

    team_df = pd.DataFrame(team_details).set_index("Player")

    team_df.loc["Totals"] = {

        "Position": "N/A",

        "Team": "N/A",

        "FPT": sum(player.FPT for player in team),

        "CR": sum(player.CR for player in team),

        "avg_FPT": sum(player.avg_FPT for player in team)

    }

    teams_data[team_name] = team_df

# Write each team to a separate sheet in the Excel file

with pd.ExcelWriter("euroleague_best_team_original_average.xlsx") as writer:

    for team_name, team_df in teams_data.items():

        team_df.to_excel(writer, sheet_name=team_name)

# Display the created teams

for idx, team in enumerate(fantasy_teams, 1):

    logging.info(f"\nFantasy Team {idx} with Total FPT: {sum(player.FPT for player in team):.2f} and Total avg_FPT {sum(player.avg_FPT for player in team):.2f}")

    for player in team:

        logging.info(f"{player.Player} | Position: {player.Pos} | Team: {player.Team} | FPT: {player.avg_FPT:.2f} | CR: {player.CR}")