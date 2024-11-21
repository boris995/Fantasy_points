import logging
import time
import pandas as pd
import glob
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.edge.service import Service
from selenium.webdriver.edge.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.microsoft import EdgeChromiumDriverManager

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# File paths
timestamp_file = "data_timestamp.txt"
data_file = "EL_data_players_w_"

# Set up WebDriver
logging.info("Setting up the WebDriver for scraping...")
options = Options()
options.add_argument("start-maximized")
options.add_experimental_option("detach", True)
driver = webdriver.Edge(service=Service(EdgeChromiumDriverManager().install()), options=options)

# Open the webpage
# url = "https://www.dunkest.com/en/euroleague/stats/players/table?season_id=17&mode=dunkest&stats_type=tot&weeks[]=10&rounds[]=1&rounds[]=2&teams[]=31&teams[]=32&teams[]=33&teams[]=34&teams[]=35&teams[]=36&teams[]=37&teams[]=38&teams[]=39&teams[]=40&teams[]=41&teams[]=42&teams[]=43&teams[]=44&teams[]=45&teams[]=47&teams[]=48&teams[]=60&positions[]=1&positions[]=2&positions[]=3&player_search=&min_cr=4&max_cr=35&sort_by=pdk&sort_order=desc&iframe=yes&noadv=yes"
# logging.info(f"Opening the webpage: {url}")
# driver.get(url)
# WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "#statsPagination")))

players_data = []

start_part = 'https://www.dunkest.com/en/euroleague/stats/players/table?season_id=17&mode=dunkest&stats_type=avg&'
last_part = '&rounds[]=1&rounds[]=2&rounds[]=3&teams[]=31&teams[]=32&teams[]=33&teams[]=34&teams[]=35&teams[]=36&teams[]=37&teams[]=38&teams[]=39&teams[]=40&teams[]=41&teams[]=42&teams[]=43&teams[]=44&teams[]=45&teams[]=47&teams[]=48&teams[]=60&positions[]=1&positions[]=2&positions[]=3&player_search=&min_cr=4&max_cr=35&sort_by=pdk&sort_order=desc&iframe=yes&noadv=yes'

def scrape(week):

    variable_part = '&weeks[]=' + str(week)
    url = start_part + variable_part + last_part

    driver.get(url)
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "#statsPagination")))

    number_of_pages = int(driver.find_element(By.CSS_SELECTOR, "#statsPagination .paginationjs-page.paginationjs-last.J-paginationjs-page").text)

    # # Determine the number of pages
    # try:
    #     number_of_pages = int(driver.find_element(By.CSS_SELECTOR, "#statsPagination .paginationjs-page.paginationjs-last.J-paginationjs-page").text)
    #     logging.info(f"Total pages to navigate: {number_of_pages}")
    # except Exception as e:
    #     logging.error(f"Error finding the total number of pages: {e}")
    #     # driver.quit()
    #     number_of_pages = int(driver.find_element(By.CSS_SELECTOR, "#statsPagination .paginationjs-page.paginationjs-last.J-paginationjs-page").text)

    # Scrape data from each page
    for page in range(number_of_pages):
        logging.info(f"Processing page {page + 1}/{number_of_pages}...")

        try:
            WebDriverWait(driver, 10).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".table-stats__container tbody tr")))
            player_rows = driver.find_elements(By.CSS_SELECTOR, ".table-stats__container tbody tr")

            for row in player_rows:
                try:
                    player_name = row.find_element(By.CSS_SELECTOR, ".table__col--player-link").text
                    position = row.find_element(By.CSS_SELECTOR, "td[data-sort-by='position']").text
                    team = row.find_element(By.CSS_SELECTOR, "td[data-sort-by='team']").text
                    fpt = row.find_element(By.CSS_SELECTOR, "td[data-sort-by='pdk']").text
                    cr = row.find_element(By.CSS_SELECTOR, "td[data-sort-by='cr']").text
                    plus = row.find_element(By.CSS_SELECTOR, "td[data-sort-by='plus']").text

                    players_data.append({
                        "Player": player_name,
                        "Pos": position,
                        "Team": team,
                        "FPT": fpt,
                        "CR": cr,
                        "PLUS": plus
                    })
                except Exception as e:
                    logging.warning(f"Error extracting data from row: {e}")

            # Move to the next page
            if page < number_of_pages - 1:
                next_button = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "#statsPagination .paginationjs-next.J-paginationjs-next"))
                )
                next_button.click()
                time.sleep(1)  # Small delay for page load
                WebDriverWait(driver, 10).until(EC.staleness_of(player_rows[0]))  # Wait until rows are reloaded
        except Exception as e:
            logging.error(f"Error loading page {page + 1}: {e}")
            break

    # Data aggregation
    df_initial = pd.DataFrame(players_data)


    # Save DataFrame
    logging.info("Creating DataFrame from collected data and saving to Excel...")
    df_initial.to_excel(f'{data_file}{week}.xlsx', index=False)
    # driver.quit()


scrape(1)
scrape(2)
# scrape(3)
# scrape(4)
# scrape(5)
# scrape(6)
# scrape(7)
# scrape(8)
# scrape(9)
# scrape(10)

# file_paths = glob.glob('euroleague_data_players_week_*.xlsx')  # Adjust path and file extension if necessary

# for i in range(10):

def merge():
    file_path = 'euroleague_data_players_week_'
    

    with pd.ExcelWriter('euroleague_data_players_merge.xlsx') as writer:
    # for i, file_path in enumerate(file_paths):
        # Load each file into a DataFrame
        # file_path = f'{file_path}{i+1}'
        for i in range(10):
            df = pd.read_excel(f'{file_path}{i+1}.xlsx')

            # Debugging: Check the shape of the DataFrame
            print(f"Processing {file_path} - Shape: {df.shape}")
            
            # Reset the index to prevent any index issues
            # df = df.reset_index(drop=True)

            # Name each sheet by week number
            sheet_name = f'Week {i + 1}'

            # Write the DataFrame to a new sheet in the output file
            df.to_excel(writer, sheet_name=sheet_name, index=False)

# merge()