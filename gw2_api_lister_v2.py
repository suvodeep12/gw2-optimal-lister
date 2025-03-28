import tkinter as tk
from tkinter import ttk, messagebox
import requests
import threading
import queue
import json
import os
import time
import math

# --- Prerequisites ---
# pip install requests

# --- Configuration ---
API_BASE_URL = "https://api.guildwars2.com"
REQUEST_TIMEOUT = 20
TAX_RATE = 0.85
CACHE_FILE = "item_cache.json"
API_BATCH_SIZE = 200

# --- Global Cache ---
item_id_cache = {}
cache_loaded = False
cache_building = False # Flag to indicate if cache build is in progress
cache_lock = threading.Lock() # Lock for accessing/modifying cache_loaded/building flags

# --- Tooltip Class ---
class ToolTip:
    """
    Simple tooltip implementation for Tkinter widgets.
    """
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip_window = None
        self.widget.bind("<Enter>", self.show_tooltip)
        self.widget.bind("<Leave>", self.hide_tooltip)

    def show_tooltip(self, event=None):
        x, y, _, _ = self.widget.bbox("insert")
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 25

        self.tooltip_window = tk.Toplevel(self.widget)
        self.tooltip_window.wm_overrideredirect(True)
        self.tooltip_window.wm_geometry(f"+{x}+{y}")

        label = tk.Label(self.tooltip_window, text=self.text, justify='left',
                         background="#ffffe0", relief='solid', borderwidth=1,
                         font=("tahoma", "8", "normal"))
        label.pack(ipadx=1)

    def hide_tooltip(self, event=None):
        if self.tooltip_window:
            self.tooltip_window.destroy()
        self.tooltip_window = None

# --- Helper Functions ---
def format_gw2_price(copper):
    if copper is None or copper < 0: return "N/A"
    copper = int(copper)
    gold = copper // 10000
    silver = (copper % 10000) // 100
    copper_rem = copper % 100
    parts = []
    if gold > 0: parts.append(f"{gold}g")
    if silver > 0: parts.append(f"{silver}s")
    if copper_rem > 0 or not parts: parts.append(f"{copper_rem}c")
    return " ".join(parts) if parts else "0c"

def load_item_cache(status_queue):
    """Loads the item ID cache from a JSON file. Reports status."""
    global item_id_cache, cache_loaded
    with cache_lock:
        if cache_loaded: return True # Already loaded

        if os.path.exists(CACHE_FILE):
            status_queue.put(("info", f"Loading cache from {CACHE_FILE}..."))
            try:
                with open(CACHE_FILE, 'r') as f:
                    item_id_cache = json.load(f)
                if isinstance(item_id_cache, dict): # Basic validation
                    cache_loaded = True
                    print(f"Loaded {len(item_id_cache)} items from cache.")
                    status_queue.put(("success", "Cache loaded. Ready."))
                    return True
                else:
                    print("Cache file content is not a dictionary. Will rebuild.")
                    item_id_cache = {} # Reset
                    status_queue.put(("info", "Invalid cache file format. Rebuilding..."))
                    return False
            except (json.JSONDecodeError, IOError) as e:
                print(f"Error loading cache file {CACHE_FILE}: {e}")
                item_id_cache = {} # Reset cache on error
                status_queue.put(("info", f"Cache load error: {e}. Rebuilding..."))
                return False
        else:
            print("Cache file not found. Will build.")
            status_queue.put(("info", "Cache file not found. Building cache..."))
            return False

def save_item_cache():
    global item_id_cache
    try:
        with open(CACHE_FILE, 'w') as f:
            json.dump(item_id_cache, f)
        print(f"Saved {len(item_id_cache)} items to cache.")
    except IOError as e:
        print(f"Error saving cache file {CACHE_FILE}: {e}")

def build_item_cache(status_queue, force_rebuild=False):
    """Fetches item data from API to build the name -> ID cache."""
    global item_id_cache, cache_loaded, cache_building
    with cache_lock:
        if cache_building and not force_rebuild:
            status_queue.put(("info", "Cache build already in progress."))
            return True # Don't start another build
        if cache_loaded and not force_rebuild:
             status_queue.put(("info", "Cache already loaded."))
             return True # Already done

        # Mark as building
        cache_building = True
        cache_loaded = False # Ensure it's marked as not ready during build

    print("Starting item cache build from GW2 API...")
    status_queue.put(("info", "Building item cache (this may take a few minutes)..."))
    start_time = time.time()
    success = False # Track if build succeeds

    try:
        status_queue.put(("info", "Fetching price list IDs..."))
        prices_url = f"{API_BASE_URL}/v2/commerce/prices"
        response = requests.get(prices_url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        tp_item_ids = response.json()
        print(f"Found {len(tp_item_ids)} items with price data.")
        total_items = len(tp_item_ids)
        status_queue.put(("info", f"Found {total_items} items. Fetching details..."))

        temp_cache = {} # Build in a temporary dict
        num_batches = math.ceil(total_items / API_BATCH_SIZE)
        processed_count = 0

        for i in range(num_batches):
            batch_start = i * API_BATCH_SIZE
            batch_end = min((i + 1) * API_BATCH_SIZE, total_items) # Prevent overflow
            batch_ids = tp_item_ids[batch_start:batch_end]
            if not batch_ids: continue # Skip empty batch

            ids_param = ",".join(map(str, batch_ids))
            items_url = f"{API_BASE_URL}/v2/items?ids={ids_param}"

            pct_done = int(((i + 1) / num_batches) * 100)
            # More granular status update
            status_queue.put(("info", f"Fetching details: Batch {i+1}/{num_batches} ({pct_done}%)..."))
            print(f"Fetching batch {i+1}/{num_batches} ({len(batch_ids)} IDs)")

            retries = 2 # Allow a couple of retries per batch
            for attempt in range(retries + 1):
                try:
                    item_details_resp = requests.get(items_url, timeout=REQUEST_TIMEOUT)
                    item_details_resp.raise_for_status()
                    item_details = item_details_resp.json()

                    for item in item_details:
                        if 'name' in item and item['name']:
                            temp_cache[item['name'].lower()] = item['id']
                    processed_count += len(item_details)
                    break # Success, exit retry loop
                except requests.exceptions.RequestException as batch_e:
                    print(f"Error fetching item batch {i+1} (Attempt {attempt+1}/{retries+1}): {batch_e}.")
                    if attempt < retries:
                        time.sleep(1) # Wait before retry
                    else:
                         print(f"Skipping batch {i+1} after multiple failures.")
                         status_queue.put(("info", f"Error fetching batch {i+1}. Some items may be missing."))
                         # Continue to next batch

            # Optional: Small delay
            # time.sleep(0.05)

        end_time = time.time()
        print(f"Built cache with {len(temp_cache)} items (processed {processed_count}) in {end_time - start_time:.2f} seconds.")

        if temp_cache:
            with cache_lock: # Update global cache under lock
                item_id_cache = temp_cache
            save_item_cache()
            status_queue.put(("success", "Item cache built and saved. Ready."))
            success = True
        else:
             status_queue.put(("error", "Failed to build item cache. No items retrieved."))

    except requests.exceptions.RequestException as e:
        print(f"API Error building item cache: {e}")
        status_queue.put(("error", f"API Error building cache: {e}"))
    except Exception as e:
         print(f"Unexpected error building item cache: {e}")
         status_queue.put(("error", f"Unexpected error building cache: {e}"))
    finally:
        with cache_lock: # Ensure building flag is reset
            cache_building = False
            if success:
                cache_loaded = True # Mark as loaded only if successful
            else:
                 # Keep cache_loaded as False if build failed
                 if not item_id_cache: # If cache is truly empty after failure
                     status_queue.put(("error", "Cache build failed. Try again or use Item IDs."))
                 else: # If some items were loaded before failure
                      status_queue.put(("info", "Cache build incomplete. Ready (may be missing items)."))
                      cache_loaded = True # Allow use of partial cache

        return success


def find_item_id_by_name(item_name_lower):
    global item_id_cache
    return item_id_cache.get(item_name_lower)

# --- API Fetching Logic ---

def fetch_api_data(item_identifier, result_queue):
    global item_id_cache, cache_loaded, cache_building
    item_id = None
    item_name_to_display = item_identifier

    with cache_lock: # Check cache status under lock
        if not cache_loaded and not cache_building:
            # Should have been handled by initial load, but as a safeguard
             result_queue.put(("error", "Item cache not ready. Please wait or restart."))
             return
        elif cache_building:
             result_queue.put(("info", "Cache is building. Please wait..."))
             return

    # 1. Determine Item ID
    if isinstance(item_identifier, int) or item_identifier.isdigit():
        item_id = int(item_identifier)
        item_name_to_display = f"Item ID: {item_id}"
    else:
        item_name_lower = item_identifier.lower()
        item_id = find_item_id_by_name(item_name_lower)
        if item_id:
            item_name_to_display = item_identifier # Use original casing if found
        else:
            result_queue.put(("error", f"Item name '{item_identifier}' not found in cache. Check spelling or try Item ID."))
            return

    # 2. Fetch Commerce Data
    if item_id is None:
        result_queue.put(("error", "Could not determine Item ID."))
        return

    api_data = {'confirmed_name': item_name_to_display}

    try:
        # Fetch prices
        prices_url = f"{API_BASE_URL}/v2/commerce/prices?ids={item_id}"
        prices_resp = requests.get(prices_url, timeout=REQUEST_TIMEOUT)
        prices_resp.raise_for_status()
        prices_data = prices_resp.json()

        if not prices_data:
            result_queue.put(("error", f"No price data for Item ID {item_id} (maybe not tradable?)."))
            return
        item_price_info = prices_data[0]
        highest_buy_copper = item_price_info.get('buys', {}).get('unit_price', 0)
        lowest_sell_copper = item_price_info.get('sells', {}).get('unit_price', 0)
        api_data['buy_price'] = highest_buy_copper if highest_buy_copper > 0 else None
        api_data['sell_price'] = lowest_sell_copper if lowest_sell_copper > 0 else None
        api_data['buy_qty'] = item_price_info.get('buys', {}).get('quantity', 0)

        # Fetch listings for sell quantity
        listings_url = f"{API_BASE_URL}/v2/commerce/listings?ids={item_id}"
        listings_resp = requests.get(listings_url, timeout=REQUEST_TIMEOUT)
        listings_resp.raise_for_status()
        listings_data = listings_resp.json()

        if not listings_data:
             api_data['sell_qty'] = None
        else:
            item_listing_info = listings_data[0]
            if 'sells' in item_listing_info and item_listing_info['sells']:
                api_data['sell_qty'] = item_listing_info['sells'][0].get('quantity')
            else:
                api_data['sell_qty'] = 0

        # Fetch name if ID was input
        if isinstance(item_identifier, int) or item_identifier.isdigit():
            try:
                item_details_url = f"{API_BASE_URL}/v2/items?ids={item_id}"
                item_details_resp = requests.get(item_details_url, timeout=REQUEST_TIMEOUT)
                item_details_resp.raise_for_status()
                item_details_data = item_details_resp.json()
                if item_details_data and 'name' in item_details_data[0]:
                    api_data['confirmed_name'] = item_details_data[0]['name']
                    # Add to cache if it wasn't there somehow
                    if item_details_data[0]['name'].lower() not in item_id_cache:
                         with cache_lock:
                              item_id_cache[item_details_data[0]['name'].lower()] = item_id
            except Exception as name_e: print(f"Warning: Could not fetch item name for ID {item_id}: {name_e}")

        result_queue.put(("success", api_data))

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404: result_queue.put(("error", f"API Error 404: Item ID {item_id} not found."))
        elif e.response.status_code == 429: result_queue.put(("error", f"API Error 429: Rate limit hit. Please wait."))
        else: result_queue.put(("error", f"API HTTP Error: {e}"))
    except requests.exceptions.RequestException as e: result_queue.put(("error", f"API Network Error: {e}"))
    except (IndexError, KeyError, TypeError) as e:
        print(f"Error processing API response for ID {item_id}: {e}")
        result_queue.put(("error", f"Error processing API data for ID {item_id}."))
    except Exception as e:
        print(f"Unexpected error fetching API data: {e}")
        result_queue.put(("error", f"Unexpected error during API fetch: {e}"))


# --- GUI Application ---
class OptimalListerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("GW2 Optimal Lister (Official API v2)")
        self.root.geometry("550x500") # Made slightly taller for menu

        self.result_queue = queue.Queue()
        self.status_queue = queue.Queue()

        self._setup_styles()
        self._create_menu() # Create menu bar
        self._create_widgets()
        self._bind_events()

        # Start background cache load/build check
        self.cache_check_thread = threading.Thread(target=load_item_cache, args=(self.status_queue,), daemon=True)
        self.cache_check_thread.start()

        self.root.after(100, self.process_result_queue)
        self.root.after(100, self.process_status_queue)

    def _setup_styles(self):
        style = ttk.Style()
        style.configure("TLabel", padding=5, font=('Segoe UI', 10))
        style.configure("TButton", padding=5, font=('Segoe UI', 10))
        style.configure("TEntry", padding=5, font=('Segoe UI', 10))
        style.configure("Result.TLabel", font=('Segoe UI', 10, 'bold'))
        style.configure("Header.TLabel", font=('Segoe UI', 12, 'bold'))
        style.configure("Error.TLabel", foreground='red', font=('Segoe UI', 10))
        style.configure("Success.TLabel", foreground='dark green', font=('Segoe UI', 10))
        style.configure("Info.TLabel", foreground='blue', font=('Segoe UI', 10))

    def _create_menu(self):
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        # File Menu (Optional - can add Exit later)
        # file_menu = tk.Menu(menubar, tearoff=0)
        # menubar.add_cascade(label="File", menu=file_menu)
        # file_menu.add_command(label="Exit", command=self.root.quit)

        # Options Menu
        options_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Options", menu=options_menu)
        options_menu.add_command(label="Update Item Cache", command=self.force_cache_update)

        # Help Menu
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About", command=self.show_about)

    def _create_widgets(self):
        # --- Input Frame ---
        input_frame = ttk.Frame(self.root, padding="10")
        input_frame.pack(fill=tk.X)
        ttk.Label(input_frame, text="Item Name or ID:").grid(row=0, column=0, sticky=tk.W)
        self.item_name_entry = ttk.Entry(input_frame, width=40)
        self.item_name_entry.grid(row=0, column=1, padx=5, sticky=tk.EW)
        self.search_button = ttk.Button(input_frame, text="Find Optimal Listing")
        self.search_button.grid(row=0, column=2, padx=5)
        input_frame.columnconfigure(1, weight=1)
        self.item_name_entry.config(state=tk.DISABLED) # Disabled until cache ready
        self.search_button.config(state=tk.DISABLED)

        # --- Results Frame ---
        results_frame = ttk.Frame(self.root, padding="10")
        results_frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(results_frame, text="Results", style="Header.TLabel").grid(row=0, column=0, columnspan=2, pady=(0, 10), sticky=tk.W)

        self.confirmed_name_label = ttk.Label(results_frame, text="Item:")
        self.confirmed_name_label.grid(row=1, column=0, sticky=tk.W)
        self.confirmed_name_value = ttk.Label(results_frame, text="N/A", wraplength=350)
        self.confirmed_name_value.grid(row=1, column=1, sticky=tk.W)

        self.buy_price_label = ttk.Label(results_frame, text="Highest Buy:")
        self.buy_price_label.grid(row=2, column=0, sticky=tk.W)
        self.buy_price_value = ttk.Label(results_frame, text="N/A")
        self.buy_price_value.grid(row=2, column=1, sticky=tk.W)
        ToolTip(self.buy_price_label, "Highest current buy order price and total quantity demanded at that price.")

        self.sell_price_label = ttk.Label(results_frame, text="Lowest Sell:")
        self.sell_price_label.grid(row=3, column=0, sticky=tk.W)
        self.sell_price_value = ttk.Label(results_frame, text="N/A")
        self.sell_price_value.grid(row=3, column=1, sticky=tk.W)
        ToolTip(self.sell_price_label, "Lowest current sell listing price and quantity available at that price.")

        ttk.Separator(results_frame, orient=tk.HORIZONTAL).grid(row=4, column=0, columnspan=2, sticky=tk.EW, pady=10)
        ttk.Label(results_frame, text="Suggestion", style="Header.TLabel").grid(row=5, column=0, columnspan=2, pady=(0, 10), sticky=tk.W)

        self.suggested_price_label = ttk.Label(results_frame, text="Suggested Price:")
        self.suggested_price_label.grid(row=6, column=0, sticky=tk.W)
        self.suggested_price_value = ttk.Label(results_frame, text="N/A", style="Result.TLabel")
        self.suggested_price_value.grid(row=6, column=1, sticky=tk.W)

        self.suggested_qty_label = ttk.Label(results_frame, text="Suggested Qty:")
        self.suggested_qty_label.grid(row=7, column=0, sticky=tk.W)
        self.suggested_qty_value = ttk.Label(results_frame, text="N/A", style="Result.TLabel")
        self.suggested_qty_value.grid(row=7, column=1, sticky=tk.W)

        self.profit_info_label = ttk.Label(results_frame, text="Profit Info:")
        self.profit_info_label.grid(row=8, column=0, sticky=tk.W, pady=(5,0))
        self.profit_info_value = ttk.Label(results_frame, text="N/A", wraplength=400)
        self.profit_info_value.grid(row=8, column=1, sticky=tk.W, pady=(5,0))

        # Status Bar
        status_frame = ttk.Frame(self.root, padding=(10, 5))
        status_frame.pack(fill=tk.X, side=tk.BOTTOM)
        self.status_label = ttk.Label(status_frame, text="Initializing...", style="Info.TLabel", anchor=tk.W)
        self.status_label.pack(fill=tk.X)

    def _bind_events(self):
        self.item_name_entry.bind("<Return>", self.start_search_thread)
        self.search_button.config(command=self.start_search_thread)

    def clear_results(self):
        self.confirmed_name_value.config(text="N/A")
        self.buy_price_value.config(text="N/A")
        self.sell_price_value.config(text="N/A")
        self.suggested_price_value.config(text="N/A")
        self.suggested_qty_value.config(text="N/A")
        self.profit_info_value.config(text="N/A")

    def update_status(self, message, status_type="info"):
        style_map = {"error": "Error.TLabel", "success": "Success.TLabel", "info": "Info.TLabel"}
        style = style_map.get(status_type, "Info.TLabel")
        max_len = 150
        display_message = message if len(message) <= max_len else message[:max_len-3] + "..."
        self.status_label.config(text=display_message, style=style)
        print(f"Status ({status_type}): {message}")

    def show_about(self):
        messagebox.showinfo("About GW2 Optimal Lister",
                            "Version: 2.0 (API)\n\n"
                            "Uses the official Guild Wars 2 API to fetch item prices.\n"
                            "Calculates a suggested listing price based on undercutting the lowest seller.\n\n"
                            "Disclaimer: Market data can fluctuate. This is a suggestion, not financial advice.")

    def force_cache_update(self):
         with cache_lock:
             if cache_building:
                  messagebox.showinfo("Cache Update", "Cache update is already in progress.")
                  return

         if messagebox.askyesno("Update Cache?", "This will re-download item data from the GW2 API and may take several minutes. Proceed?"):
             self.search_button.config(state=tk.DISABLED)
             self.item_name_entry.config(state=tk.DISABLED)
             # Find the menu item and disable it (more complex, skip for now or find widget path)
             self.update_status("Forcing cache update...", status_type="info")
             # Start build in a new thread
             self.cache_build_thread = threading.Thread(target=build_item_cache, args=(self.status_queue, True), daemon=True)
             self.cache_build_thread.start()


    def start_search_thread(self, event=None):
        identifier = self.item_name_entry.get().strip()
        if not identifier:
            messagebox.showwarning("Input Required", "Please enter an item name or ID.")
            return
        self.clear_results()
        self.update_status(f"Searching for '{identifier}'...", status_type="info")
        self.search_button.config(state=tk.DISABLED)
        self.item_name_entry.config(state=tk.DISABLED)
        self.search_thread = threading.Thread(target=fetch_api_data, args=(identifier, self.result_queue), daemon=True)
        self.search_thread.start()

    def process_status_queue(self):
         global cache_loaded, cache_building
         try:
             message = self.status_queue.get_nowait()
             msg_type, data = message
             self.update_status(data, status_type=msg_type)

             with cache_lock: # Check status under lock after update
                is_ready = cache_loaded and not cache_building
                is_error_state = msg_type == "error" and not cache_loaded # If build failed completely

             if is_ready:
                 self.search_button.config(state=tk.NORMAL)
                 self.item_name_entry.config(state=tk.NORMAL)
                 # Optional: Set a final "Ready" message only if it wasn't an error update
                 if msg_type != "error":
                      self.update_status("Ready. Enter item name or ID.", status_type="success")
             elif is_error_state:
                  # Keep controls disabled if cache build failed
                  self.search_button.config(state=tk.DISABLED)
                  self.item_name_entry.config(state=tk.DISABLED)

         except queue.Empty:
             pass
         finally:
             self.root.after(200, self.process_status_queue) # Check less frequently than results

    def process_result_queue(self):
        global cache_loaded # Need to check if cache is ready before re-enabling
        try:
            message = self.result_queue.get_nowait()
            msg_type, data = message

            if msg_type == "success":
                self.display_results(data)
                self.update_status("Search complete.", status_type="success")
            elif msg_type == "error":
                self.update_status(f"{data}", status_type="error")
            elif msg_type == "info": # Handle intermediate status from fetch
                 self.update_status(data, status_type="info")

            # Re-enable controls ONLY if cache is loaded and not building
            if msg_type == "success" or msg_type == "error":
                with cache_lock:
                    if cache_loaded and not cache_building:
                        self.search_button.config(state=tk.NORMAL)
                        self.item_name_entry.config(state=tk.NORMAL)
                    elif cache_building:
                        # Update status but keep disabled
                        self.update_status("Cache build in progress...", status_type="info")
                    # If !cache_loaded and !cache_building, it means build failed before, keep disabled

        except queue.Empty:
            pass
        finally:
            self.root.after(100, self.process_result_queue)

    def display_results(self, data):
        self.clear_results()
        self.confirmed_name_value.config(text=data.get('confirmed_name', "N/A"))
        buy_price = data.get('buy_price')
        buy_qty = data.get('buy_qty')
        sell_price = data.get('sell_price')
        sell_qty = data.get('sell_qty')

        buy_qty_str = f"(Demand: {buy_qty:,})" if buy_qty is not None and buy_qty > 0 else ""
        sell_qty_str = f"(Supply: {sell_qty:,})" if sell_qty is not None and sell_qty > 0 else ""
        buy_price_str = f"{format_gw2_price(buy_price)} {buy_qty_str}".strip() if buy_price is not None else "N/A"
        sell_price_str = f"{format_gw2_price(sell_price)} {sell_qty_str}".strip() if sell_price is not None else "N/A"
        self.buy_price_value.config(text=buy_price_str)
        self.sell_price_value.config(text=sell_price_str)

        if buy_price is not None and sell_price is not None:
            if sell_price <= 0:
                 self.profit_info_value.config(text="Sell price is zero or negative.") # FIX: Use text=
                 return
            if sell_price > buy_price:
                instant_profit_per = buy_price * TAX_RATE
                suggested_list_price = sell_price - 1
                if suggested_list_price <= 0:
                     self.suggested_price_value.config(text="N/A")
                     self.suggested_qty_value.config(text="N/A")
                     self.profit_info_value.config(text="Lowest sell price is 1c. Cannot undercut.") # FIX: Use text=
                     return
                list_profit_per = suggested_list_price * TAX_RATE
                if list_profit_per > instant_profit_per:
                    profit_gain_per = list_profit_per - instant_profit_per
                    self.suggested_price_value.config(text=format_gw2_price(suggested_list_price))
                    suggested_qty_str = f"{sell_qty:,}" if sell_qty is not None and sell_qty > 0 else "1+"
                    self.suggested_qty_value.config(text=f"Up to {suggested_qty_str}")
                    # FIX: Use text=
                    self.profit_info_value.config(text=
                        f"Listing at {format_gw2_price(suggested_list_price)} could yield ~{format_gw2_price(profit_gain_per)} more profit/item (after tax) "
                        f"than instant selling at {format_gw2_price(buy_price)}."
                    )
                else:
                    profit_loss_per = instant_profit_per - list_profit_per
                    self.suggested_price_value.config(text=format_gw2_price(suggested_list_price))
                    self.suggested_qty_value.config(text="Consider")
                     # FIX: Use text=
                    self.profit_info_value.config(text=
                        f"Listing at {format_gw2_price(suggested_list_price)} yields ~{format_gw2_price(profit_loss_per)} "
                        f"LESS profit/item than instant selling at {format_gw2_price(buy_price)}. "
                        f"Instant sell may be better, or list higher."
                    )
            else:
                 # FIX: Use text=
                 self.profit_info_value.config(text=f"Lowest sell ({format_gw2_price(sell_price)}) ≤ highest buy ({format_gw2_price(buy_price)}). Instant sell is likely optimal.")
        elif sell_price is None: self.profit_info_value.config(text="No sell orders found.") # FIX: Use text=
        elif buy_price is None: self.profit_info_value.config(text="No buy orders found.") # FIX: Use text=
        else: self.profit_info_value.config(text="Could not determine prices.") # FIX: Use text=


# --- Main Execution ---
if __name__ == "__main__":
    try: import requests
    except ImportError: messagebox.showerror("Dependency Missing", "'requests' not found.\npip install requests"); import sys; sys.exit(1)

    root = tk.Tk()
    app = OptimalListerApp(root)
    root.mainloop()