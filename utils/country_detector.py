import re

# Comprehensive list of countries with their center coordinates and aliases
COUNTRIES = [
    {"name": "Indonesia", "code": "ID", "flag": "🇮🇩", "lat": -0.7893, "lng": 113.9213, "aliases": ["Indonesia", "Indonesian", "Jakarta", "Java", "Bali", "Sumatra", "Kalimantan", "Sulawesi", "Papua"]},
    {"name": "China", "code": "CN", "flag": "🇨🇳", "lat": 35.8617, "lng": 104.1954, "aliases": ["China", "Chinese", "Beijing", "Shanghai", "Shenzhen", "Hong Kong", "Taiwan", "Tibet", "Xinjiang"]},
    {"name": "Japan", "code": "JP", "flag": "🇯🇵", "lat": 36.2048, "lng": 138.2529, "aliases": ["Japan", "Japanese", "Tokyo", "Osaka", "Kyoto", "Yokohama"]},
    {"name": "South Korea", "code": "KR", "flag": "🇰🇷", "lat": 35.9078, "lng": 127.7669, "aliases": ["South Korea", "Korea", "Korean", "Seoul", "Busan", "K-pop"]},
    {"name": "North Korea", "code": "KP", "flag": "🇰🇵", "lat": 40.3399, "lng": 127.5101, "aliases": ["North Korea", "Pyongyang"]},
    {"name": "India", "code": "IN", "flag": "🇮🇳", "lat": 20.5937, "lng": 78.9629, "aliases": ["India", "Indian", "Delhi", "Mumbai", "Bangalore", "Chennai", "Kolkata"]},
    {"name": "Pakistan", "code": "PK", "flag": "🇵🇰", "lat": 30.3753, "lng": 69.3451, "aliases": ["Pakistan", "Pakistani", "Islamabad", "Karachi", "Lahore"]},
    {"name": "Bangladesh", "code": "BD", "flag": "🇧🇩", "lat": 23.6850, "lng": 90.3563, "aliases": ["Bangladesh", "Dhaka"]},
    {"name": "Vietnam", "code": "VN", "flag": "🇻🇳", "lat": 14.0583, "lng": 108.2772, "aliases": ["Vietnam", "Vietnamese", "Hanoi", "Ho Chi Minh", "Saigon"]},
    {"name": "Thailand", "code": "TH", "flag": "🇹🇭", "lat": 15.8700, "lng": 100.9925, "aliases": ["Thailand", "Thai", "Bangkok"]},
    {"name": "Malaysia", "code": "MY", "flag": "🇲🇾", "lat": 4.2105, "lng": 101.9758, "aliases": ["Malaysia", "Malaysian", "Kuala Lumpur"]},
    {"name": "Singapore", "code": "SG", "flag": "🇸🇬", "lat": 1.3521, "lng": 103.8198, "aliases": ["Singapore", "Singaporean"]},
    {"name": "Philippines", "code": "PH", "flag": "🇵🇭", "lat": 12.8797, "lng": 121.7740, "aliases": ["Philippines", "Filipino", "Manila"]},
    {"name": "Myanmar", "code": "MM", "flag": "🇲🇲", "lat": 21.9162, "lng": 95.9560, "aliases": ["Myanmar", "Burma", "Yangon"]},
    {"name": "Cambodia", "code": "KH", "flag": "🇰🇭", "lat": 12.5657, "lng": 104.9910, "aliases": ["Cambodia", "Cambodian", "Phnom Penh"]},
    {"name": "Laos", "code": "LA", "flag": "🇱🇦", "lat": 19.8563, "lng": 102.4955, "aliases": ["Laos", "Lao", "Vientiane"]},
    {"name": "Nepal", "code": "NP", "flag": "🇳🇵", "lat": 28.3949, "lng": 84.1240, "aliases": ["Nepal", "Nepalese", "Kathmandu"]},
    {"name": "Sri Lanka", "code": "LK", "flag": "🇱🇰", "lat": 7.8731, "lng": 80.7718, "aliases": ["Sri Lanka", "Sri Lankan", "Colombo"]},
    {"name": "Afghanistan", "code": "AF", "flag": "🇦🇫", "lat": 33.9391, "lng": 67.7100, "aliases": ["Afghanistan", "Afghan", "Kabul", "Taliban"]},
    {"name": "Iran", "code": "IR", "flag": "🇮🇷", "lat": 32.4279, "lng": 53.6880, "aliases": ["Iran", "Iranian", "Tehran"]},
    {"name": "Iraq", "code": "IQ", "flag": "🇮🇶", "lat": 33.2232, "lng": 43.6793, "aliases": ["Iraq", "Iraqi", "Baghdad"]},
    {"name": "Saudi Arabia", "code": "SA", "flag": "🇸🇦", "lat": 23.8859, "lng": 45.0792, "aliases": ["Saudi Arabia", "Saudi", "Riyadh", "Mecca", "Medina"]},
    {"name": "UAE", "code": "AE", "flag": "🇦🇪", "lat": 23.4241, "lng": 53.8478, "aliases": ["UAE", "United Arab Emirates", "Dubai", "Abu Dhabi", "Emirates"]},
    {"name": "Israel", "code": "IL", "flag": "🇮🇱", "lat": 31.0461, "lng": 34.8516, "aliases": ["Israel", "Israeli", "Tel Aviv", "Jerusalem", "Gaza", "Palestine", "Palestinian", "West Bank"]},
    {"name": "Turkey", "code": "TR", "flag": "🇹🇷", "lat": 38.9637, "lng": 35.2433, "aliases": ["Turkey", "Turkish", "Ankara", "Istanbul"]},
    {"name": "Syria", "code": "SY", "flag": "🇸🇾", "lat": 34.8021, "lng": 38.9968, "aliases": ["Syria", "Syrian", "Damascus"]},
    {"name": "Jordan", "code": "JO", "flag": "🇯🇴", "lat": 30.5852, "lng": 36.2384, "aliases": ["Jordan", "Jordanian", "Amman"]},
    {"name": "Lebanon", "code": "LB", "flag": "🇱🇧", "lat": 33.8547, "lng": 35.8623, "aliases": ["Lebanon", "Lebanese", "Beirut"]},
    {"name": "Qatar", "code": "QA", "flag": "🇶🇦", "lat": 25.3548, "lng": 51.1839, "aliases": ["Qatar", "Qatari", "Doha"]},
    {"name": "Kuwait", "code": "KW", "flag": "🇰🇼", "lat": 29.3117, "lng": 47.4818, "aliases": ["Kuwait", "Kuwaiti"]},
    {"name": "Oman", "code": "OM", "flag": "🇴🇲", "lat": 21.4735, "lng": 55.9754, "aliases": ["Oman", "Omani", "Muscat"]},
    {"name": "Yemen", "code": "YE", "flag": "🇾🇪", "lat": 15.5527, "lng": 48.5164, "aliases": ["Yemen", "Yemeni", "Sanaa"]},
    
    # Europe
    {"name": "Russia", "code": "RU", "flag": "🇷🇺", "lat": 61.5240, "lng": 105.3188, "aliases": ["Russia", "Russian", "Moscow", "Kremlin"]},
    {"name": "United Kingdom", "code": "GB", "flag": "🇬🇧", "lat": 55.3781, "lng": -3.4360, "aliases": ["UK", "United Kingdom", "Britain", "British", "England", "Scotland", "Wales", "London"]},
    {"name": "Germany", "code": "DE", "flag": "🇩🇪", "lat": 51.1657, "lng": 10.4515, "aliases": ["Germany", "German", "Berlin", "Munich", "Frankfurt"]},
    {"name": "France", "code": "FR", "flag": "🇫🇷", "lat": 46.2276, "lng": 2.2137, "aliases": ["France", "French", "Paris"]},
    {"name": "Italy", "code": "IT", "flag": "🇮🇹", "lat": 41.8719, "lng": 12.5674, "aliases": ["Italy", "Italian", "Rome", "Milan"]},
    {"name": "Spain", "code": "ES", "flag": "🇪🇸", "lat": 40.4637, "lng": -3.7492, "aliases": ["Spain", "Spanish", "Madrid", "Barcelona"]},
    {"name": "Netherlands", "code": "NL", "flag": "🇳🇱", "lat": 52.1326, "lng": 5.2913, "aliases": ["Netherlands", "Dutch", "Holland", "Amsterdam"]},
    {"name": "Belgium", "code": "BE", "flag": "🇧🇪", "lat": 50.5039, "lng": 4.4699, "aliases": ["Belgium", "Belgian", "Brussels"]},
    {"name": "Switzerland", "code": "CH", "flag": "🇨🇭", "lat": 46.8182, "lng": 8.2275, "aliases": ["Switzerland", "Swiss", "Zurich", "Geneva"]},
    {"name": "Poland", "code": "PL", "flag": "🇵🇱", "lat": 51.9194, "lng": 19.1451, "aliases": ["Poland", "Polish", "Warsaw"]},
    {"name": "Ukraine", "code": "UA", "flag": "🇺🇦", "lat": 48.3794, "lng": 31.1656, "aliases": ["Ukraine", "Ukrainian", "Kyiv", "Kiev"]},
    {"name": "Sweden", "code": "SE", "flag": "🇸🇪", "lat": 60.1282, "lng": 18.6435, "aliases": ["Sweden", "Swedish", "Stockholm"]},
    {"name": "Norway", "code": "NO", "flag": "🇳🇴", "lat": 60.4720, "lng": 8.4689, "aliases": ["Norway", "Norwegian", "Oslo"]},
    {"name": "Denmark", "code": "DK", "flag": "🇩🇰", "lat": 56.2639, "lng": 9.5018, "aliases": ["Denmark", "Danish", "Copenhagen"]},
    {"name": "Finland", "code": "FI", "flag": "🇫🇮", "lat": 61.9241, "lng": 25.7482, "aliases": ["Finland", "Finnish", "Helsinki"]},
    {"name": "Greece", "code": "GR", "flag": "🇬🇷", "lat": 39.0742, "lng": 21.8243, "aliases": ["Greece", "Greek", "Athens"]},
    {"name": "Portugal", "code": "PT", "flag": "🇵🇹", "lat": 39.3999, "lng": -8.2245, "aliases": ["Portugal", "Portuguese", "Lisbon"]},
    {"name": "Austria", "code": "AT", "flag": "🇦🇹", "lat": 47.5162, "lng": 14.5501, "aliases": ["Austria", "Austrian", "Vienna"]},
    {"name": "Czech Republic", "code": "CZ", "flag": "🇨🇿", "lat": 49.8175, "lng": 15.4730, "aliases": ["Czech Republic", "Czech", "Prague"]},
    {"name": "Romania", "code": "RO", "flag": "🇷🇴", "lat": 45.9432, "lng": 24.9668, "aliases": ["Romania", "Romanian", "Bucharest"]},
    {"name": "Hungary", "code": "HU", "flag": "🇭🇺", "lat": 47.1625, "lng": 19.5033, "aliases": ["Hungary", "Hungarian", "Budapest"]},
    {"name": "Ireland", "code": "IE", "flag": "🇮🇪", "lat": 53.1424, "lng": -7.6921, "aliases": ["Ireland", "Irish", "Dublin"]},
    
    # Americas
    {"name": "United States", "code": "US", "flag": "🇺🇸", "lat": 37.0902, "lng": -95.7129, "aliases": ["USA", "US", "United States", "America", "American", "Washington", "New York", "California", "Texas", "Florida", "Chicago", "Los Angeles", "Pentagon", "White House"]},
    {"name": "Canada", "code": "CA", "flag": "🇨🇦", "lat": 56.1304, "lng": -106.3468, "aliases": ["Canada", "Canadian", "Ottawa", "Toronto", "Vancouver"]},
    {"name": "Mexico", "code": "MX", "flag": "🇲🇽", "lat": 23.6345, "lng": -102.5528, "aliases": ["Mexico", "Mexican", "Mexico City"]},
    {"name": "Brazil", "code": "BR", "flag": "🇧🇷", "lat": -14.2350, "lng": -51.9253, "aliases": ["Brazil", "Brazilian", "Brasilia", "Sao Paulo", "Rio de Janeiro"]},
    {"name": "Argentina", "code": "AR", "flag": "🇦🇷", "lat": -38.4161, "lng": -63.6167, "aliases": ["Argentina", "Argentine", "Buenos Aires"]},
    {"name": "Chile", "code": "CL", "flag": "🇨🇱", "lat": -35.6751, "lng": -71.5430, "aliases": ["Chile", "Chilean", "Santiago"]},
    {"name": "Colombia", "code": "CO", "flag": "🇨🇴", "lat": 4.5709, "lng": -74.2973, "aliases": ["Colombia", "Colombian", "Bogota"]},
    {"name": "Peru", "code": "PE", "flag": "🇵🇪", "lat": -9.1900, "lng": -75.0152, "aliases": ["Peru", "Peruvian", "Lima"]},
    {"name": "Venezuela", "code": "VE", "flag": "🇻🇪", "lat": 6.4238, "lng": -66.5897, "aliases": ["Venezuela", "Venezuelan", "Caracas"]},
    {"name": "Ecuador", "code": "EC", "flag": "🇪🇨", "lat": -1.8312, "lng": -78.1834, "aliases": ["Ecuador", "Ecuadorian", "Quito"]},
    {"name": "Cuba", "code": "CU", "flag": "🇨🇺", "lat": 21.5218, "lng": -77.7812, "aliases": ["Cuba", "Cuban", "Havana"]},
    
    # Africa
    {"name": "South Africa", "code": "ZA", "flag": "🇿🇦", "lat": -30.5595, "lng": 22.9375, "aliases": ["South Africa", "South African", "Johannesburg", "Cape Town"]},
    {"name": "Egypt", "code": "EG", "flag": "🇪🇬", "lat": 26.8206, "lng": 30.8025, "aliases": ["Egypt", "Egyptian", "Cairo"]},
    {"name": "Nigeria", "code": "NG", "flag": "🇳🇬", "lat": 9.0820, "lng": 8.6753, "aliases": ["Nigeria", "Nigerian", "Lagos"]},
    {"name": "Kenya", "code": "KE", "flag": "🇰🇪", "lat": -0.0236, "lng": 37.9062, "aliases": ["Kenya", "Kenyan", "Nairobi"]},
    {"name": "Ethiopia", "code": "ET", "flag": "🇪🇹", "lat": 9.1450, "lng": 40.4897, "aliases": ["Ethiopia", "Ethiopian", "Addis Ababa"]},
    {"name": "Morocco", "code": "MA", "flag": "🇲🇦", "lat": 31.7917, "lng": -7.0926, "aliases": ["Morocco", "Moroccan", "Rabat", "Casablanca"]},
    {"name": "Algeria", "code": "DZ", "flag": "🇩🇿", "lat": 28.0339, "lng": 1.6596, "aliases": ["Algeria", "Algerian", "Algiers"]},
    {"name": "Libya", "code": "LY", "flag": "🇱🇾", "lat": 26.3351, "lng": 17.2283, "aliases": ["Libya", "Libyan", "Tripoli"]},
    {"name": "Sudan", "code": "SD", "flag": "🇸🇩", "lat": 12.8628, "lng": 30.2176, "aliases": ["Sudan", "Sudanese", "Khartoum"]},
    {"name": "Somalia", "code": "SO", "flag": "🇸🇴", "lat": 5.1521, "lng": 46.1996, "aliases": ["Somalia", "Somali", "Mogadishu"]},
    {"name": "Congo", "code": "CD", "flag": "🇨🇩", "lat": -4.0383, "lng": 21.7587, "aliases": ["Congo", "Congolese", "DRC", "Democratic Republic of Congo", "Kinshasa"]},
    {"name": "Tanzania", "code": "TZ", "flag": "🇹🇿", "lat": -6.3690, "lng": 34.8888, "aliases": ["Tanzania", "Tanzanian", "Dar es Salaam"]},
    {"name": "Ghana", "code": "GH", "flag": "🇬🇭", "lat": 7.9465, "lng": -1.0232, "aliases": ["Ghana", "Ghanaian", "Accra"]},
    {"name": "Uganda", "code": "UG", "flag": "🇺🇬", "lat": 1.3733, "lng": 32.2903, "aliases": ["Uganda", "Ugandan", "Kampala"]},
    {"name": "Rwanda", "code": "RW", "flag": "🇷🇼", "lat": -1.9403, "lng": 29.8739, "aliases": ["Rwanda", "Rwandan", "Kigali"]},
    
    # Oceania
    {"name": "Australia", "code": "AU", "flag": "🇦🇺", "lat": -25.2744, "lng": 133.7751, "aliases": ["Australia", "Australian", "Sydney", "Melbourne", "Canberra"]},
    {"name": "New Zealand", "code": "NZ", "flag": "🇳🇿", "lat": -40.9006, "lng": 174.8860, "aliases": ["New Zealand", "Kiwi", "Wellington", "Auckland"]},
    
    # Additional important regions
    {"name": "European Union", "code": "EU", "flag": "🇪🇺", "lat": 50.1109, "lng": 9.6824, "aliases": ["EU", "European Union", "Europe", "European", "Brussels EU"]},
    {"name": "NATO", "code": "NATO", "flag": "🛡️", "lat": 50.8750, "lng": 4.7043, "aliases": ["NATO", "Atlantic Alliance"]},
    {"name": "UN", "code": "UN", "flag": "🇺🇳", "lat": 40.7484, "lng": -73.9857, "aliases": ["UN", "United Nations", "UN Security Council"]},
    {"name": "ASEAN", "code": "ASEAN", "flag": "🌏", "lat": 13.7563, "lng": 100.5018, "aliases": ["ASEAN", "Association of Southeast Asian Nations"]},
    {"name": "BRICS", "code": "BRICS", "flag": "🧱", "lat": -15.7801, "lng": -47.9292, "aliases": ["BRICS"]},
]

# Create an alias map for faster lookup
ALIAS_MAP = {}
for country in COUNTRIES:
    for alias in country["aliases"]:
        ALIAS_MAP[alias.lower()] = country

# Pre-compile the combined regex for all aliases for maximum performance
import re

# Sort aliases by length descending to ensure longer matches (e.g. "Saudi Arabia") 
# are tried before shorter ones (e.g. "Saudi") to prevent partial matches.
_SORTED_ALIASES = sorted(ALIAS_MAP.keys(), key=len, reverse=True)
_COMBINED_PATTERN = re.compile(r'\b(' + '|'.join(re.escape(a) for a in _SORTED_ALIASES) + r')\b', re.IGNORECASE)

def detect_countries(text):
    if not text:
        return []
        
    found = {}
    # Use findall on the combined pattern — much faster than looping re.search
    matches = _COMBINED_PATTERN.findall(text)
    
    for match in matches:
        match_lower = match.lower()
        if match_lower in ALIAS_MAP:
            country = ALIAS_MAP[match_lower]
            found[country["code"]] = country
            
    return list(found.values())

def count_country_mentions(articles):
    mentions = {}
    
    for art in articles:
        text = f"{art.get('title', '')} {art.get('description', '') or ''}"
        found = detect_countries(text)
        
        for country in found:
            code = country["code"]
            if code not in mentions:
                mentions[code] = {
                    "country": country,
                    "count": 0,
                    "articles": []
                }
            mentions[code]["count"] += 1
            mentions[code]["articles"].append({
                "id": art.get("id"),
                "title": art.get("title"),
                "pubDate": art.get("pubDate"),
                "isBuffer": True
            })
            
    # Sort by count descending
    sorted_mentions = sorted(mentions.values(), key=lambda x: x["count"], reverse=True)
    return sorted_mentions
