import numpy as np

def generate_thermal_flux_points(lat, lon, temp=25.0, count=40, spread=0.08):
    """
    Menghasilkan titik heatmap dengan bobot yang dipengaruhi suhu riil.
    Meteo Mapping:
    - Suhu Tinggi (>30C) -> Bobot > 0.7 (Area Merah)
    - Suhu Sedang (20-30C) -> Bobot 0.4 - 0.7 (Area Hijau/Kuning)
    - Suhu Rendah (<20C) -> Bobot < 0.4 (Area Biru)
    """
    heat_data = []
    
    # Normalisasi bobot berdasarkan suhu (Range 0C - 40C)
    # Mapping sederhana: 10C -> 0.1 (Biru), 25C -> 0.5 (Hijau), 40C -> 0.9 (Merah)
    base_weight = np.clip((temp - 5) / 38, 0.1, 0.95)
    
    for _ in range(count):
        lat_off = float(lat + np.random.normal(0, spread))
        lon_off = float(lon + np.random.normal(0, spread))
        
        # Variansi random agar heatmap terlihat dinamis (streaming feel)
        weight = float(np.clip(base_weight + np.random.uniform(-0.15, 0.15), 0.05, 1.0))
        heat_data.append([lat_off, lon_off, weight])
        
    return heat_data
