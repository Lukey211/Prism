import requests
from bs4 import BeautifulSoup
import json
import time
from datetime import datetime
from urllib.parse import urljoin
import os

BASE_URL = "https://www.adfg.alaska.gov"
FISH_COUNTS_URL = "https://www.adfg.alaska.gov/sf/FishCounts/"

# Use a persistent session with robust headers to appear more like a browser
SESSION = requests.Session()
SESSION.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
})

def get_soup(url, method='get', data=None, retries=3, backoff_factor=3):
    """
    Fetches a URL with retry logic using the global persistent session.
    """
    # Set the Referer header to the last page visited, crucial for navigation
    if SESSION.headers.get('Referer'):
        pass # The session object might handle it, but we can be explicit
    
    for i in range(retries):
        try:
            if method.lower() == 'post':
                response = SESSION.post(url, timeout=45, data=data)
            else:
                response = SESSION.get(url, timeout=45)
            
            response.raise_for_status()
            
            # Update the referer for the next request
            SESSION.headers.update({'Referer': url})
            
            return BeautifulSoup(response.text, 'html.parser')
            
        except requests.exceptions.RequestException as e:
            print(f"  - Warning (Attempt {i + 1}/{retries}): Could not fetch {url}. Error: {e}")
            if i < retries - 1:
                wait_time = backoff_factor * (2 ** i)
                print(f"    Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                print(f"  - CRITICAL: All {retries} attempts failed for {url}.")
                return None

def scrape_fish_counts():
    """
    Fetches fish count data by correctly navigating the multi-step form process.
    """
    print("\n--- STAGE 4: Scraping Fish Counts (Corrected Logic) ---")
    
    print(f"-> Fetching main fish count page: {FISH_COUNTS_URL}")
    main_soup = get_soup(FISH_COUNTS_URL)
    if not main_soup:
        print("  - ABORT: Could not fetch the main fish counts page.")
        return

    location_form = main_soup.find('form', id='selectLocation')
    if not location_form:
        print("  - ABORT: Could not find the initial location selection form.")
        return
        
    locations = [{'id': o['value'], 'name': o.text.strip()} for o in location_form.find_all('option') if o.get('value')]
    print(f"-> Found {len(locations)} potential count locations.")
    
    all_count_data = []
    loc_form_action_url = urljoin(FISH_COUNTS_URL, location_form['action'])

    for loc in locations:
        time.sleep(2)
        print(f"\n--> Processing Location: {loc['name']} (ID: {loc['id']})")
        
        # STEP 1: Submit the location to get the page with species and year selectors
        species_page_soup = get_soup(loc_form_action_url, method='post', data={'countLocationID': loc['id']})

        if not species_page_soup:
            continue

        # STEP 2: Find the second form on the new page
        species_year_form = species_page_soup.find('form', id='selectSpeciesYearLocation')
        if not species_year_form:
            print(f"    - No species/year data form found for {loc['name']}. Skipping.")
            continue
            
        species_select = species_year_form.find('select', {'name': 'SpeciesID'})
        year_select = species_year_form.find('select', {'name': 'year'})

        if not species_select or not year_select:
            print(f"    - Page for {loc['name']} is missing species or year dropdowns. Skipping.")
            continue
        
        results_form_action_url = urljoin(FISH_COUNTS_URL, species_year_form['action'])
        
        # STEP 3: Get all available years and species from the form
        available_years = [y['value'] for y in year_select.find_all('option')]
        species_list = [{'id': s['value'], 'name': s.text.strip()} for s in species_select.find_all('option') if s.get('value')]
        
        print(f"    - Found {len(species_list)} species and {len(available_years)} years of data.")

        for species in species_list:
            time.sleep(1)
            print(f"    -> Requesting data for species: {species['name']}...")
            
            # STEP 4: Build the payload with location, species, AND ALL years
            payload = {
                'countLocationID': loc['id'],
                'SpeciesID': species['id'],
                'year': available_years,
                'Submit': 'Submit'
            }
            
            # STEP 5: Submit the complete form to get the final results page
            results_page_soup = get_soup(results_form_action_url, method='post', data=payload)

            if not results_page_soup:
                continue

            # STEP 6: Find the JSON export link and download the data
            json_link = results_page_soup.find('a', href=lambda href: href and 'export.JSON' in href)
            
            if json_link:
                json_url = urljoin(FISH_COUNTS_URL, json_link['href'])
                print(f"      -> Fetching JSON data from: {json_url}")
                try:
                    # Use a fresh get from the session, which will have the correct referer
                    response = SESSION.get(json_url, timeout=45)
                    response.raise_for_status()
                    data = response.json()
                    
                    for record in data:
                        record['locationName'] = loc['name']
                        record['speciesName'] = species['name']
                    all_count_data.extend(data)
                    print(f"      ✅ Success! Added {len(data)} records for {loc['name']} - {species['name']}.")
                except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
                    print(f"      - ERROR: Failed to get or parse JSON for {species['name']}. Error: {e}")
            else:
                print(f"      - Warning: No JSON export link found for {species['name']} at this location.")

    if all_count_data:
        output_filename = 'fish_counts.json'
        with open(output_filename, 'w', encoding='utf-8') as f:
            json.dump(all_count_data, f, indent=2, ensure_ascii=False)
        print(f"\n✅ Success! Saved a total of {len(all_count_data)} fish count records to {output_filename}.")
    else:
        print("\n- No fish count data was scraped.")


def main():
    """Main function to discover all report pages and scrape them."""
    
    # --- STAGE 1, 2, 3 (Reports) are commented out to focus on Fish Counts ---
    # print("Starting ADF&G fishing report scraper...")
    # ... (rest of report scraping code remains commented out) ...
    
    # --- STAGE 4: Scrape Fish Counts ---
    scrape_fish_counts()


if __name__ == '__main__':
    main()