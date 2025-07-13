import requests
from bs4 import BeautifulSoup
import json
import time
from datetime import datetime
from urllib.parse import urljoin

BASE_URL = "https://www.adfg.alaska.gov"
START_URL = "https://www.adfg.alaska.gov/sf/FishingReports/"

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

        # Scrape current season tabs
        tab_menu_div = area_soup.select_one('div.oneleveltabs')
        if tab_menu_div:
            for a in tab_menu_div.find_all('a', href=True):
                report_url = urljoin(BASE_URL, a['href'])
                master_report_list.append({'url': report_url, 'date': a.text.strip()})

        # Scrape archived reports for the last two years
        archive_form = area_soup.find('form', attrs={'name': 'CFForm_1'})
        if archive_form:
            archive_base_url = urljoin(BASE_URL, archive_form['action'])
            for year in years_to_scrape:
                archive_year_url = f"{archive_base_url}&year={year}"
                print(f"  -> Fetching archives for {year} from {archive_year_url}")
                archive_soup = get_soup(archive_year_url)
                if not archive_soup: continue
                
                # Find the table with all the dated links
                archive_table = archive_soup.find('div', id='EONRarchives').find('table')
                if not archive_table: continue

                for a in archive_table.find_all('a', href=True):
                    report_url = urljoin(archive_base_url, a['href'])
                    master_report_list.append({'url': report_url, 'date': a.text.strip()})

    print(f"✅ Discovered a master list of {len(master_report_list)} total reports to scrape.")

    # --- STAGE 3: SCRAPING ---
    all_reports_data = []
    report_id_counter = 1
    
    # Remove duplicate URLs before scraping
    unique_reports = {item['url']: item for item in master_report_list}.values()
    print(f"✅ After de-duplication, scraping {len(unique_reports)} reports.")
    
    for report_info in sorted(list(unique_reports), key=lambda x: x['url']): 
        time.sleep(1) 
        page_url = report_info['url']
        report_date = report_info['date']
        
        print(f"-> Scraping: {report_date} - {page_url}")
        page_soup = get_soup(page_url)
        if not page_soup: continue
        
        report_content_div = page_soup.find('div', class_='afterpadder')
        if not report_content_div:
            print(f"  - Warning: Could not find 'afterpadder' content on {page_url}")
            continue

        try:
            area_name_tag = page_soup.select_one('h1.temph1 span.h1subheader')
            area_name = area_name_tag.text.strip() if area_name_tag else "Unknown Area"
            
            full_text = report_content_div.text.strip()
            
            all_reports_data.append({
                "reportId": f"ADFG-{report_id_counter}",
                "area": area_name,
                "title": report_date, # Use the link text as the title (e.g., "Jul 10, 2025")
                "date": report_date, # Add a dedicated date field
                "full_text": full_text
            })
            report_id_counter += 1
        except Exception as e:
            print(f"   - Could not parse report content. Error: {e}")
            continue
    
    # --- Step 4: Save the final JSON file ---
    output_filename = 'reports.json'
    with open(output_filename, 'w', encoding='utf-8') as f:
        json.dump(all_reports_data, f, indent=2, ensure_ascii=False)
        
    print(f"\n✅ All finished! Scraping complete. Saved {len(all_reports_data)} reports to {output_filename}.")

if __name__ == '__main__':
    main()