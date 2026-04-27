import time
import requests
from db import get_db_connection

def geocode_nominatim(query):
    try:
        headers = {'User-Agent': 'AsetpediaGeocodingBot/1.0'}
        url = f"https://nominatim.openstreetmap.org/search?q={requests.utils.quote(query)}&format=json&limit=1"
        response = requests.get(url, headers=headers)
        data = response.json()
        if data:
            return float(data[0]['lat']), float(data[0]['lon'])
    except Exception as e:
        print(f"Error geocoding {query}: {e}")
    return None, None

def main():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT id, facility_name, location FROM oil_refinery_accidents WHERE latitude IS NULL")
    accidents = cursor.fetchall()
    
    print(f"Found {len(accidents)} records to geocode.")

    for acc in accidents:
        # Try facility name + location first
        query = f"{acc['facility_name']} {acc['location']}"
        lat, lon = geocode_nominatim(query)
        
        # If not found, try just location
        if lat is None:
            print(f"Retrying with location only for: {acc['facility_name']}")
            lat, lon = geocode_nominatim(acc['location'])
            
        if lat is not None:
            print(f"Updating {acc['facility_name']}: {lat}, {lon}")
            cursor.execute(
                "UPDATE oil_refinery_accidents SET latitude = %s, longitude = %s WHERE id = %s",
                (lat, lon, acc['id'])
            )
            conn.commit()
        else:
            print(f"Could not find coordinates for: {query}")
        
        # Sleep to respect Nominatim usage policy (1 request per second)
        time.sleep(1.1)

    cursor.close()
    conn.close()
    print("Geocoding complete.")

if __name__ == "__main__":
    main()
