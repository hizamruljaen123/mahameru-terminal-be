import math

def calculate_investment_score(logistics_data, public_infra):
    """
    Menghitung Asetpedia Investment Potential Index (AIPI) berdasarkan
    kepadatan dan jenis infrastruktur penunjang di sekitar kawasan industri.
    """
    
    # Kategori infrastruktur dan bobot strategis (0-10)
    WEIGHTS = {
        'port': 10,
        'airport': 9,
        'power_plant': 9,
        'hospital': 7,
        'clinic': 5,
        'police': 8,
        'fire_station': 8,
        'bank': 6,
        'hotel': 5,
        'school': 4,
        'university': 5,
        'fuel': 6,
        'restaurant': 2,
        'supermarket': 3
    }
    
    infra_counts = {}
    total_strategic_value = 0
    
    # 1. Hitung fasilitas logistik (High value) dengan pembobotan jarak
    for category in ['airports', 'ports', 'power_plants']:
        items = logistics_data.get(category, [])
        for item in items:
            dist = float(item.get('distance_km', 50))
            # Distance Weight: 1.0 at 0km, 0.2 at 100km
            dist_factor = max(0.1, 1.0 - (dist / 110))
            
            weight_key = category.rstrip('s')
            infra_counts[weight_key] = infra_counts.get(weight_key, 0) + 1
            total_strategic_value += WEIGHTS.get(weight_key, 8) * 2.0 * dist_factor
            
    # 2. Hitung fasilitas publik dari OSM data dengan pembobotan jarak
    for item in public_infra:
        t = item.get('type', '').lower()
        dist = float(item.get('distance_km', 50))
        if not t: continue
        
        # Mapping type ke weight_key
        key = 'other'
        if t in ['port', 'ferry_terminal']: key = 'port'
        elif t in ['hospital', 'clinic', 'pharmacy']: key = 'hospital'
        elif t == 'police': key = 'police'
        elif t == 'fire_station': key = 'fire_station'
        elif t in ['bank', 'atm', 'bureau_de_change']: key = 'bank'
        elif t == 'hotel': key = 'hotel'
        elif t in ['school', 'university', 'college', 'kindergarten']: key = 'school'
        elif t == 'fuel': key = 'fuel'
        elif t in ['restaurant', 'cafe', 'fast_food', 'food_court']: key = 'restaurant'
        elif t in ['supermarket', 'mall', 'marketplace', 'convenience']: key = 'supermarket'
        else: key = t
        
        # Distance Weight for Public Infra
        dist_factor = max(0.05, 1.0 - (dist / 100))
        
        infra_counts[key] = infra_counts.get(key, 0) + 1
        total_strategic_value += WEIGHTS.get(key, 1) * dist_factor

    # Base formula index (logarithmic scale to compress high density areas)
    # A score of 100 requires significant infrastructure across all domains
    raw_score = total_strategic_value
    
    # Diversity multiplier: Area is better if it has many different TYPES of infrastructure
    diversity = len([k for k, v in infra_counts.items() if v > 0])
    diversity_multiplier = 1.0 + (min(diversity, 15) / 15.0) * 0.5  # Up to 1.5x bonus for high diversity
    
    calculated_index = min(100.0, (math.log1p(raw_score) / math.log1p(500)) * 60 * diversity_multiplier)
    
    # Profitability level based on index
    if calculated_index >= 85:
        level = "PRIME_HUB"
        profitability = "Sangat Menguntungkan (Highly Profitable)"
        desc = "Lokasi memiliki ekosistem industri dan logistik kelas dunia. Risiko rantai pasok sangat rendah."
    elif calculated_index >= 65:
        level = "STRATEGIC"
        profitability = "Menguntungkan (Profitable)"
        desc = "Infrastruktur memadai untuk operasi skala besar. Konektivitas baik."
    elif calculated_index >= 40:
        level = "DEVELOPING"
        profitability = "Potensial (Moderate)"
        desc = "Fasilitas dasar tersedia, namun bergantung pada investasi infrastruktur lanjutan."
    else:
        level = "ISOLATED"
        profitability = "Risiko Tinggi (High Risk)"
        desc = "Infrastruktur minim. Biaya logistik dan risiko operasional akan tinggi."

    return {
        "investment_index": round(calculated_index, 1),
        "total_facilities": sum(infra_counts.values()),
        "facility_breakdown": infra_counts,
        "classification": level,
        "profitability_rating": profitability,
        "strategic_analysis": desc,
        "diversity_score": diversity
    }
