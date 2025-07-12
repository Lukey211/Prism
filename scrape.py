import requests
from bs4 import BeautifulSoup
import json
import time
from datetime import datetime, timedelta
from urllib.parse import urljoin

BASE_URL = "https://www.adfg.alaska.gov"
START_URL = "https://www.adfg.alaska.gov/sf/FishingReports/"

# List of common species to check for in the report text
SPECIES_KEYWORDS = [
    "king salmon", "chinook", "sockeye", "red salmon", "coho", "silver salmon",
    "pink salmon", "chum", "halibut", "lingcod", "rockfish", "dolly varden",
    "trout", "steelhead", "arctic char", "grayling", "northern pike", "burbot"
]

def get_soup(url):
    """Fetches a URL with a browser-like header and returns a BeautifulSoup object."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    try:
        response = requests.get(url, timeout=20, headers=headers)
        response.raise_for_status()
        return BeautifulSoup(response.text, 'html.parser')
    except requests.exceptions.RequestException as e:
        print(f"  - Warning: Could not fetch {url}. Error: {e}")
        return None

def scrape_fish_counts():
    """Fetches and processes structured fish count data from ADF&G."""
    print("\n--- STAGE 4: Scraping Fish Counts ---")
    fish_counts_page_url = "https://www.adfg.alaska.gov/sf/FishCounts/"
    soup = get_soup(fish_counts_page_url)
    if not soup:
        print("  - Warning: Could not fetch fish counts page.")
        return

    json_link = soup.find('a', href=lambda href: href and href.endswith('.json'))
    
    if json_link:
        json_url = urljoin(BASE_URL, json_link['href'])
        print(f"-> Found fish count JSON data at: {json_url}")
        try:
            response = requests.get(json_url, timeout=20)
            response.raise_for_status()
            fish_count_data = response.json()
            
            output_filename = 'fish_counts.json'
            with open(output_filename, 'w', encoding='utf-8') as f:
                json.dump(fish_count_data, f, indent=2, ensure_ascii=False)
            print(f"✅ Success! Saved {len(fish_count_data)} fish count records to {output_filename}.")

        except requests.exceptions.RequestException as e:
            print(f"  - Warning: Could not fetch fish count JSON. Error: {e}")
        except json.JSONDecodeError:
            print("  - Warning: Failed to parse fish count JSON.")
    else:
        print("  - Warning: Could not find a JSON download link for fish counts.")


def main():
    """Main function to discover all report pages and scrape them."""
    print("Starting ADF&G fishing report scraper...")
    
    # --- STAGE 1: Discover Initial Area Pages ---
    initial_area_pages = set()
    print(f"Fetching main report page: {START_URL}")
    main_soup = get_soup(START_URL)
    if not main_soup:
        print("FATAL: Could not fetch the main report page. Exiting.")
        return

    for a in main_soup.find_all('a', href=True):
        if 'ReportDetail' in a['href']:
            initial_area_pages.add(urljoin(BASE_URL, a['href']))
            
    print(f"✅ Found {len(initial_area_pages)} main area pages.")

    # --- STAGE 2: Discover All Current Season & Archive Report Links ---
    master_report_list = []
    current_year = datetime.now().year
    years_to_scrape = [str(current_year), str(current_year - 1)]
    print(f"Scraping reports for years: {', '.join(years_to_scrape)}")

    for area_page_url in initial_area_pages:
        time.sleep(1)
        print(f"-> Discovering reports in: {area_page_url}")
        area_soup = get_soup(area_page_url)
        if not area_soup: continue

        tab_menu_div = area_soup.select_one('div.oneleveltabs')
        if tab_menu_div:
            for a in tab_menu_div.find_all('a', href=True):
                report_url = urljoin(BASE_URL, a['href'])
                master_report_list.append({'url': report_url, 'date': a.text.strip()})

        archive_form = area_soup.find('form', attrs={'name': 'CFForm_1'})
        if archive_form:
            archive_base_url = urljoin(BASE_URL, archive_form['action'])
            for year in years_to_scrape:
                archive_year_url = f"{archive_base_url}&year={year}"
                print(f"  -> Fetching archives for {year} from {archive_year_url}")
                archive_soup = get_soup(archive_year_url)
                if not archive_soup: continue
                
                archive_table = archive_soup.find('div', id='EONRarchives').find('table')
                if not archive_table: continue

                for a in archive_table.find_all('a', href=True):
                    report_url = urljoin(archive_base_url, a['href'])
                    master_report_list.append({'url': report_url, 'date': a.text.strip()})

    print(f"✅ Discovered a master list of {len(master_report_list)} total reports to scrape.")

    # --- STAGE 3: SCRAPING ---
    all_reports_data = []
    report_id_counter = 1
    
    unique_reports = {item['url']: item for item in master_report_list}.values()
    print(f"✅ After de-duplication, scraping {len(unique_reports)} reports.")
    
    for report_info in sorted(list(unique_reports), key=lambda x: x['url']): 
        time.sleep(1) 
        page_url = report_info['url']
        
        print(f"-> Scraping: {report_info['date']} - {page_url}")
        page_soup = get_soup(page_url)
        if not page_soup: continue
        
        report_content_div = page_soup.find('div', class_='afterpadder')
        if not report_content_div:
            print(f"  - Warning: Could not find 'afterpadder' content on {page_url}")
            continue

        try:
            # Clean the content by removing unwanted navigation blocks first
            for nav_links in report_content_div.select('div.box-links'):
                nav_links.decompose()
            for ul in report_content_div.find_all('ul'):
                if "Emergency Order" in ul.text or "Press Release" in ul.text:
                    ul.decompose()

            area_name_tag = page_soup.select_one('h1.temph1 span.h1subheader')
            area_name = area_name_tag.text.strip() if area_name_tag else "Unknown Area"
            
            # More precise title/date extraction
            report_date_tag = report_content_div.find(['h4', 'h3', 'strong'])
            report_title = report_date_tag.text.strip() if report_date_tag else report_info['date']

            # Extract text only from paragraph tags for a cleaner body
            paragraphs = report_content_div.find_all('p')
            full_text_cleaned = '\n\n'.join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))

            # If paragraph extraction fails, fall back to the whole div text
            if not full_text_cleaned:
                full_text_cleaned = report_content_div.get_text(separator='\n', strip=True)

            # Identify mentioned species
            mentioned_species = []
            lower_text = full_text_cleaned.lower()
            for species in SPECIES_KEYWORDS:
                if species in lower_text and species not in mentioned_species:
                    mentioned_species.append(species)
            
            all_reports_data.append({
                "reportId": f"ADFG-{report_id_counter}",
                "area": area_name,
                "title": report_title,
                "date": report_info['date'], # Keep original link date for filtering
                "source_url": page_url,
                "species_mentioned": sorted(list(set(mentioned_species))), # Ensure unique entries
                "full_text": full_text_cleaned
            })
            report_id_counter += 1
        except Exception as e:
            print(f"   - Could not parse report content. Error: {e}")
            continue
    
    output_filename = 'reports.json'
    with open(output_filename, 'w', encoding='utf-8') as f:
        json.dump(all_reports_data, f, indent=2, ensure_ascii=False)
        
    print(f"\n✅ All finished! Scraping complete. Saved {len(all_reports_data)} reports to {output_filename}.")
    
    # --- STAGE 4: Scrape Fish Counts ---
    scrape_fish_counts()


if __name__ == '__main__':
    main()