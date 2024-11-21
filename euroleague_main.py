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
data_file = "euroleague_data_players_week_10.xlsx"
timestamp_file = "data_timestamp.txt"
coach_data_file = "coach.xlsx"
defense_data_file = "euroleague_data_def_vs_pos_all.xlsx"

# Constraints
credit_limit = 100
max_players_per_team = 10
positions_needed = {'C': 2, 'F': 4, 'G': 4, 'HC': 1}
max_unique_teams = 7

# Track unique teams
unique_teams = set()

def create_team_identifier(team):
    """Creates a unique identifier for a team based on player names to ensure no duplicate teams."""
    return tuple(sorted(player.Player for player in team))

def load_data():
    # Load or scrape data
    data_up_to_date = False
    if os.path.exists(data_file) and os.path.exists(timestamp_file):
        with open(timestamp_file, 'r') as f:
            timestamp_str = f.read().strip()
            last_update = datetime.strptime(timestamp_str, "%Y-%m-%d")
            if last_update.date() == datetime.today().date():
                data_up_to_date = True
                logging.info("Found existing, up-to-date filtered data file for today.")

    if data_up_to_date:
        df = pd.read_excel(data_file)
    else:
        # Web scraping logic omitted for brevity
        pass  # Replace with actual scraping logic as needed

    # Update timestamp file
    with open(timestamp_file, 'w') as f:
        f.write(datetime.today().strftime("%Y-%m-%d"))
    logging.info("Data saved and timestamp updated.")

    # Load coach data from coach.xlsx
    if os.path.exists(coach_data_file):
        coach_df = pd.read_excel(coach_data_file)
        coach_df.rename(columns={'coach_name': 'Player', 'team_name': 'Team', 'fantasy_pts': 'FPT', 'quotation': 'CR', 'avg_fpt': 'FPT_avg'}, inplace=True)
        coach_df['Pos'] = 'HC'
        df = pd.concat([df, coach_df], ignore_index=True)
        logging.info("Coach data added to player data.")

    # Convert FPT and CR to numeric and apply filters
    df['FPT'] = pd.to_numeric(df['FPT'], errors='coerce')
    df['CR'] = pd.to_numeric(df['CR'], errors='coerce')
    df['FPT/CR'] = df['FPT'] / df['CR']
    print(df.head)
    return df

def filter_players(df):
    min_fpt = 8
    player_ratio_threshold = 0.2
    coach_ratio_threshold = 0.2
    df = df[((df['Pos'] != 'HC') & (df['FPT'] >= min_fpt) & (df['CR'] >= 4) & (df['FPT/CR'] > player_ratio_threshold)) |
            ((df['Pos'] == 'HC') & (df['FPT'] >= min_fpt) & (df['CR'] >= 4) & (df['FPT/CR'] > coach_ratio_threshold))]
    logging.info(f"Initial number of players after filtering: {len(df)}")
    return df

def load_defense_data(player_df):
    """Load defense vs position data and calculate alpha values for each position dynamically."""
    defense_data = {}
    for position, pos_label in zip(['Guards', 'Forwards', 'Centers'], ['G', 'F', 'C']):
        # Load defense data for each position
        df = pd.read_excel(defense_data_file, sheet_name=position)
        
        # Calculate league average and standard deviation for the defensive 'Average' column
        league_avg_defense = df['Average'].mean()
        league_std_defense = df['Average'].std()
        
        # Calculate average fantasy points for the position from player data
        avg_fantasy_points = player_df[player_df['Pos'] == pos_label]['FPT'].mean()
        
        # Estimate the impact ratio dynamically
        impact_ratio = (league_std_defense / league_avg_defense) / avg_fantasy_points

        # Store the alpha value for this position based on the calculated impact ratio
        alpha = impact_ratio * league_std_defense / league_avg_defense
        defense_data[position] = {
            'data': df.set_index('Team Name')['Average'].to_dict(),
            'alpha': alpha
        }
    return defense_data

def adjust_fantasy_points(player, opponent_team, defense_data):
    position_map = {'G': 'Guards', 'F': 'Forwards', 'C': 'Centers'}
    position = position_map.get(player.Pos)
    
    if not position:
        return player.FPT
    
    raw_fpt = player.FPT
    opponent_defense = defense_data[position]['data'].get(opponent_team, 0)
    alpha = defense_data[position]['alpha']
    league_avg_defense = sum(defense_data[position]['data'].values()) / len(defense_data[position]['data'].values())
    adjusted_fpt = raw_fpt * (1 - alpha * opponent_defense / league_avg_defense)
    
    # Logging for validation
    logging.info(f"Adjusting FPT for {player.Player} (Pos: {player.Pos}, Opponent: {opponent_team}): "
                 f"Raw FPT={raw_fpt}, Opponent Defense={opponent_defense}, Alpha={alpha}, "
                 f"Adjusted FPT={adjusted_fpt}")
    
    return adjusted_fpt

def select_top_players(df, defense_data):
    """Select top players based on adjusted fantasy points, considering opponent defenses."""
    top_n_per_position = 14
    top_n_per_position_coach = 8
    # Use 'Upcoming_Opponent' column in the adjustment
    df['Adjusted FPT'] = df.apply(lambda x: adjust_fantasy_points(x, x.Upcoming_Opponent, defense_data), axis=1)
    centers = df[df['Pos'] == 'C'].nlargest(top_n_per_position, 'Adjusted FPT')
    forwards = df[df['Pos'] == 'F'].nlargest(top_n_per_position, 'Adjusted FPT')
    guards = df[df['Pos'] == 'G'].nlargest(top_n_per_position, 'Adjusted FPT')
    head_coaches = df[df['Pos'] == 'HC'].nlargest(top_n_per_position_coach, 'Adjusted FPT')
    logging.info(f"Players per position after filtering: Centers={len(centers)}, Forwards={len(forwards)}, Guards={len(guards)}, Head Coaches={len(head_coaches)}")
    return centers, forwards, guards, head_coaches

def create_optimal_fantasy_team(centers, forwards, guards, head_coaches):
    logging.info("Starting team selection using optimized heuristic approach...")
    top_teams = []
    possible_combinations = 0

    def process_combination(c_combo, f_combo, g_combo):
        nonlocal possible_combinations
        for hc in head_coaches.itertuples(index=False):
            team = list(c_combo) + list(f_combo) + list(g_combo) + [hc]
            team_id = create_team_identifier(team)

            if team_id in unique_teams:
                logging.debug("Duplicate team found, skipping...")
                continue

            unique_teams.add(team_id)
            possible_combinations += 1

            total_cr = sum(player.CR for player in team)
            if total_cr > credit_limit:
                logging.debug(f"Team exceeds credit limit (Total CR: {total_cr}), skipping...")
                continue

            total_fpt = sum(player.Adjusted_FPT for player in team)
            team_counts = {}
            for player in team:
                team_counts[player.Team] = team_counts.get(player.Team, 0) + 1

            if not all(count <= max_players_per_team for count in team_counts.values()):
                logging.debug("Team exceeds max players per team constraint, skipping...")
                continue

            if len(top_teams) < max_unique_teams:
                heapq.heappush(top_teams, (total_fpt, team))
            else:
                heapq.heappushpop(top_teams, (total_fpt, team))

            logging.info(f"Combination checked: FPT={total_fpt}, CR={total_cr}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:  # Increase workers
        for c_combo in combinations(centers.itertuples(index=False), positions_needed['C']):
            for f_combo in combinations(forwards.itertuples(index=False), positions_needed['F']):
                for g_combo in combinations(guards.itertuples(index=False), positions_needed['G']):
                    executor.submit(process_combination, c_combo, f_combo, g_combo)

    logging.info(f"Total possible team combinations checked: {possible_combinations}")
    return [team for _, team in sorted(top_teams, reverse=True)]

# Main execution
df = load_data()
df = filter_players(df)
defense_data = load_defense_data(df)
centers, forwards, guards, head_coaches = select_top_players(df, defense_data)

# Generate up to 3 unique fantasy teams
logging.info(f"Generating up to {max_unique_teams} unique optimal fantasy teams...")
fantasy_teams = create_optimal_fantasy_team(centers, forwards, guards, head_coaches)

logging.info("Saving best team data to 'best_team.xlsx'")
teams_data = []
for idx, team in enumerate(fantasy_teams):
    team_dict = {"Team Number": idx + 1, "Total FPT": sum(player.Adjusted_FPT for player in team)}
    for player in team:
        team_dict[player.Player] = {"Position": player.Pos, "Team": player.Team, "FPT": player.FPT, "Adjusted FPT": player.Adjusted_FPT, "CR": player.CR}
    teams_data.append(team_dict)

pd.DataFrame(teams_data).to_excel("best_team.xlsx", index=False)

# Display the created teams
for idx, team in enumerate(fantasy_teams, 1):
    logging.info(f"\nFantasy Team {idx} with Total Adjusted FPT: {sum(player.Adjusted_FPT for player in team):.2f}")
    for player in team:
        logging.info(f"{player.Player} | Position: {player.Pos} | Team: {player.Team} | FPT: {player.FPT:.2f} | Adjusted FPT: {player.Adjusted_FPT}")