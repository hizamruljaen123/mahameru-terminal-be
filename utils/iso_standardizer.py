import sys
import os

# Add parent dir to path to import db_utils
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db_utils import execute_query, get_db_connection

# Mapping dictionary for common EIA country names to ISO3
EIA_TO_ISO3 = {
    "Afghanistan": "AFG", "Albania": "ALB", "Algeria": "DZA", "Angola": "AGO", 
    "Argentina": "ARG", "Australia": "AUS", "Austria": "AUT", "Bahrain": "BHR", 
    "Bangladesh": "BGD", "Belgium": "BEL", "Bolivia": "BOL", "Brazil": "BRA", 
    "Brunei": "BRN", "Bulgaria": "BGR", "Canada": "CAN", "Chad": "TCD", 
    "Chile": "CHL", "China": "CHN", "Colombia": "COL", "Congo-Brazzaville": "COG", 
    "Congo-Kinshasa": "COD", "Cote d'Ivoire": "CIV", "Croatia": "HRV", "Cyprus": "CYP", 
    "Czech Republic": "CZE", "Denmark": "DNK", "Ecuador": "ECU", "Egypt": "EGY", 
    "Equatorial Guinea": "GNQ", "Estonia": "EST", "Ethiopia": "ETH", "Finland": "FIN", 
    "France": "FRA", "Gabon": "GAB", "Germany": "DEU", "Ghana": "GHA", 
    "Greece": "GRC", "Guatemala": "GTM", "Guyana": "GUY", "Hungary": "HUN", 
    "Iceland": "ISL", "India": "IND", "Indonesia": "IDN", "Iran": "IRN", 
    "Iraq": "IRQ", "Ireland": "IRL", "Israel": "ISR", "Italy": "ITA", 
    "Japan": "JPN", "Jordan": "JOR", "Kazakhstan": "KAZ", "Kenya": "KEN", 
    "Kuwait": "KWT", "Latvia": "LVA", "Libya": "LBY", "Lithuania": "LTU", 
    "Luxembourg": "LUX", "Malaysia": "MYS", "Mexico": "MEX", "Morocco": "MAR", 
    "Namibia": "NAM", "Netherlands": "NLD", "New Zealand": "NZL", "Nigeria": "NGA", 
    "Norway": "NOR", "Oman": "OMN", "Pakistan": "PAK", "Panama": "PAN", 
    "Papua New Guinea": "PNG", "Peru": "PER", "Philippines": "PHL", "Poland": "POL", 
    "Portugal": "PRT", "Qatar": "QAT", "Romania": "ROU", "Russia": "RUS", 
    "Saudi Arabia": "SAU", "Singapore": "SGP", "Slovakia": "SVK", "Slovenia": "SVN", 
    "South Africa": "ZAF", "South Korea": "KOR", "Spain": "ESP", "Sri Lanka": "LKA", 
    "Sudan": "SDN", "Sweden": "SWE", "Switzerland": "CHE", "Syria": "SYR", 
    "Taiwan": "TWN", "Thailand": "THA", "Trinidad and Tobago": "TTO", "Tunisia": "TUN", 
    "Turkey": "TUR", "Turkmenistan": "TKM", "Ukraine": "UKR", "United Arab Emirates": "ARE", 
    "United Kingdom": "GBR", "United States": "USA", "Uruguay": "URY", "Uzbekistan": "UZB", 
    "Venezuela": "VEN", "Vietnam": "VNM", "Yemen": "YEM", "Zambia": "ZMB", "Zimbabwe": "ZWE"
}

def standardize_countries():
    print("[ISO] Starting Standardization Task...")
    countries = execute_query("SELECT origin_id, origin_name FROM oil_trade_countries")
    
    updated = 0
    for c in countries:
        name = c['origin_name']
        id_code = c['origin_id']
        
        # Try to find ISO3
        iso3 = None
        for key, val in EIA_TO_ISO3.items():
            if key.lower() in name.lower():
                iso3 = val
                break
        
        if iso3:
            execute_query(
                "UPDATE oil_trade_countries SET iso3 = %s WHERE origin_id = %s", 
                (iso3, id_code), 
                commit=True
            )
            updated += 1
            
    print(f"[ISO] Task Completed. Updated {updated} countries with ISO3 codes.")

if __name__ == "__main__":
    standardize_countries()
