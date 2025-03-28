# GW2 Optimal Lister (API Version)

[![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A simple Python GUI application that utilizes the official Guild Wars 2 API to fetch Trading Post data and suggest an "optimal" listing price and quantity for items. Helps players make informed decisions when selling items on the trading post by comparing potential listing profits against instant sell profits.

![screenshot](https://github.com/user-attachments/assets/60e1225d-46a0-42e6-84c9-e11d8f7c0a78)

## Features

- **Official GW2 API:** Uses the stable and official API endpoints for reliable data fetching.
- **Item Lookup:** Search for items by their exact name (case-insensitive) or their numerical Item ID.
- **Local Caching:** Builds and uses a local cache (`item_cache.json`) of item names and IDs for significantly faster lookups after the initial run.
- **Current Market Data:** Displays the current highest buy order price and lowest sell listing price, along with associated quantities (Demand/Supply at that price point).
- **Optimal Listing Suggestion:**
  - Calculates a suggested listing price by undercutting the current lowest seller by 1 copper.
  - Suggests a quantity to list (up to the amount currently available at the lowest price).
- **Profit Analysis:** Compares the estimated profit (after tax) from listing at the suggested price versus instant selling to the highest buy order.
- **Simple GUI:** Built with Python's standard `tkinter` library for cross-platform compatibility.
- **Cache Management:** Includes a menu option to manually force an update of the local item cache.
- **Tooltips:** Provides helpful hints for buy/sell quantity labels.

## Prerequisites

- **Python:** Version 3.8 or higher recommended. ([Download Python](https://www.python.org/downloads/))
- **pip:** Python's package installer (usually comes with Python).
- **Libraries:** The `requests` library is required.

## Installation

1.  **Clone or Download:**

    - Clone the repository:
      ```bash
      git clone https://github.com/your-username/your-repo-name.git
      cd your-repo-name
      ```
    - Or, download the ZIP file from GitHub and extract it.

2.  **Navigate to Directory:**
    Open your terminal or command prompt and change into the project directory:

    ```bash
    cd path/to/gw2-optimal-lister
    ```

3.  **Install Dependencies:**
    Install the required dependencies using the `requirements.txt` file:
    ```bash
    pip install -r requirements.txt
    ```

## Usage

1.  **Run the Application:**
    Execute the Python script from your terminal:

    ```bash
    python gw2_api_lister_v2.py
    ```

2.  **Initial Cache Build (First Run Only):**

    - The first time you run the application, it needs to build a local cache of item names and IDs by querying the GW2 API.
    - This process can take **several minutes**. Please be patient.
    - The status bar at the bottom will show progress messages like "Building item cache...", "Fetching price list IDs...", "Fetching item details batch X/Y...".
    - Once complete, the status bar will show "Item cache built and saved. Ready." and the search input will become active. The cache is saved as `item_cache.json` in the same directory.

3.  **Subsequent Runs:**

    - On future runs, the application will load the cache from `item_cache.json`, which is much faster. The status bar will show "Cache loaded. Ready." almost immediately.

4.  **Enter Item Name or ID:**

    - Type the **exact name** of the Guild Wars 2 item (case-insensitive) _or_ its numerical **Item ID** into the input field.

5.  **Search:**

    - Press `Enter` or click the "Find Optimal Listing" button.

6.  **View Results:**

    - **Item:** Confirms the item name found.
    - **Highest Buy:** Shows the highest buy order price and the total quantity demanded at that price.
    - **Lowest Sell:** Shows the lowest sell listing price and the quantity available at that specific price.
    - **Suggested Price:** The calculated price if you undercut the lowest seller by 1 copper.
    - **Suggested Qty:** The quantity available at the current lowest sell price (a guideline for how many you might list to match/beat the current lowest offer).
    - **Profit Info:** Explains whether listing at the suggested price is estimated to be more or less profitable (after tax) than instant selling.

7.  **Update Cache (Optional):**
    - If new items have been added to the game or you suspect the cache is outdated, go to the menu `Options -> Update Item Cache`.
    - Confirm the prompt. The cache will be rebuilt, which will take several minutes.

## How It Works

- **API Interaction:** Instead of fragile web scraping, this tool uses official Guild Wars 2 API endpoints (`/v2/commerce/prices`, `/v2/commerce/listings`, `/v2/items`).
- **Name/ID Cache:** To avoid needing to query the `/v2/items` endpoint excessively for name lookups, it builds a local JSON file (`item_cache.json`) mapping lower-case item names to their IDs. This file is loaded on startup or built on the first run/manual update.
- **Data Fetching:** When you search:
  1.  It finds the Item ID (using the cache if a name is provided).
  2.  It fetches current price data (highest buy, lowest sell) from `/v2/commerce/prices`.
  3.  It fetches listing details (including quantity at lowest sell) from `/v2/commerce/listings`.
- **Calculation:** The "optimal" suggestion is a simple heuristic: `Suggested Price = Lowest Sell Price - 1 copper`. It then compares the profit from selling at this price (after 15% tax) with the profit from selling instantly to the highest buy order (after 15% tax).

## Limitations & Disclaimer

- **"Optimal" is Simplified:** The definition of "optimal" used here is a basic undercutting strategy. Real market dynamics involve velocity, supply depth, demand depth, player psychology, and timing. This tool provides a _suggestion_, **not guaranteed financial advice**.
- **API Data Delay:** While generally up-to-date, the official API data might have a slight delay (seconds to minutes) compared to the absolute live trading post visible in-game.
- **API Changes:** ArenaNet can change their API structure or endpoints, which could break this application until it's updated. However, this is generally much less frequent than website layout changes.
- **Cache Updates:** The item cache (`item_cache.json`) only updates when manually triggered via the "Options" menu or if the file is deleted. It does not automatically detect new items added to the game.
- **Rate Limits:** The GW2 API has rate limits. While unlikely to be hit with normal use of this tool, extremely rapid consecutive searches _could_ potentially trigger temporary limits (HTTP 429 errors).

## Contributing

Contributions are welcome! Feel free to:

- Report bugs or issues via GitHub Issues.
- Suggest new features or improvements.
- Submit Pull Requests (please discuss significant changes via an issue first).

Potential areas for improvement include:

- More sophisticated analysis (e.g., considering supply/demand volume).
- Graphing price history.
- UI enhancements (using more advanced GUI toolkits).
- Automatic cache refreshing options.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
