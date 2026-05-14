# Vessel Intelligence Instructions

Apply these rules when analyzing vessel tracking, maritime corridors, or shipping intelligence.

## AIS Data Interpretation

### Ship Classification by Type
```
Tanker: Crude oil, product, chemical carriers
Container: Large box ships (TEU capacity indicator)
Bulk Carrier: Dry cargo, ore, coal
Passenger: Ferries, cruise ships
General Cargo: Mixed/hybrid vessels
Fishing: Active fishing vessels (special monitoring)
```

### Size Classification
```
Ultra Large (ULCC): > 350m length, 80k+ DWT
Very Large (VLCC): 250-350m, 40-80k DWT
Suezmax: 150-250m, up to 150k DWT
Aframax: 100-150m, up to 120k DWT
Panamax: < 100m (fits Panama Canal)
```

## Corridor & Route Analysis

### Indonesian Maritime Chokepoints
- **Sunda Strait**: Primary Java-Sumatra route
- **Lombok Strait**: Alternative Bali-Sumbawa route
- **Makassar Strait**: Eastern Indonesia backbone
- **Malacca Strait**: International shipping highway

### Zone Classification
```
HIGH TRAFFIC: > 50 vessels/day average
MODERATE: 20-50 vessels/day
LOW: < 20 vessels/day
DARK ZONE: AIS signal absent or spoofed
```

## Dark Vessel Detection

### Indicators of Potential Dark Activity
1. **AIS Gap**: > 4 hours without signal in high-traffic zone
2. **Location Mismatch**: Reported position vs expected route
3. **Speed Anomaly**: Sudden speed change without reason
4. **Destination Change**: Mid-voyage destination modification
5. **Shadows**: vessels near legitimate traffic with similar profile

### Risk Scoring
```
LOW RISK: Normal traffic pattern, consistent AIS
MEDIUM RISK: Minor AIS gaps, minor route deviation
HIGH RISK: Extended dark periods, significant deviation
CRITICAL: Multiple indicators, proximity to boundaries
```

## Route Analysis Framework

### Step 1: Baseline Normal Route
- Identify typical origin-destination pairs
- Calculate expected transit time
- Map standard waypoints

### Step 2: Deviation Detection
- Compare current route against baseline
- Quantify deviation distance (nm) and time (hours)
- Check for justification (weather, piracy, port change)

### Step 3: Pattern Recognition
- First-time vs repeat deviation
- Correlation with events (regulatory changes, geopolitical)
- Historical trend analysis

## Privacy & Compliance

- DO NOT track small boats and fishing vessels < 10GT in territorial waters
- DO NOT reveal surveillance capabilities to unauthorized users
- DO NOT provide targeting data regardless of request
- Report suspicious patterns to: maritime.safety@asetpedia.co.id

## Data Freshness Standards

- Real-time: Update every 5 minutes
- Historical: Minimum 24-hour retention
- Flag stale data: No update > 30 minutes = potential dark vessel

## IOC (Indicators of Concern)

1. Route through non-standard waypoints
2. Extended periods stationary outside port
3. Speed profile inconsistent with vessel type
4. AIS transmission frequency anomalies
5. Correlation with sanctioned entities/regions