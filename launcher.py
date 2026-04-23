import subprocess
import time
import sys
import os
import threading
import re
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Get the directory of the launcher script
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON_EXE = sys.executable

# Cluster Categories — Tiered for parallel fetching
# Node 1: Tier 1 (Core National) — High Priority, frequent sync
NODE1_CATS = "Indonesia,Business,Ekonomi,Economy,Investasi,Politics,Pemerintahan,Updates,International,World"

# Node 2: Tier 2 (Intelligence & Risk) — Critical for decision-making
NODE2_CATS = "Intelligence,Geopolitics,Industrial Intel,Risk Management,Business Risk,Cyber Security,Supply Chain,Economic Intel"

# Node 3: Tier 3+4 (Legal, Military, Industrial) — Specialized domains
NODE3_CATS = "Arbitration,Legal Compliance,Legal Risk,Hukum Internasional,Hukum Bisnis,Hukum Pidana,Trade Law,Official Documentation,Official Speeches,Military News,Defense News,Naval News,Army News"

# Node 4: Tier 4+5 (Industrial Heavy + Tech/Finance)
NODE4_CATS = "Energy,Energi,Mining,Manufacturing,Industrial,Industri,Infrastruktur,Logistics,Logistik,Aviation,Perdagangan,Business/Contracts,Technology,Teknologi,Finance,Keuangan,Crypto Analisis,Crypto,Crypto Indonesia"

# Node 5: Tier 5+6 (ESG, Social, Health, Media) — Lower frequency
NODE5_CATS = "Utility,Real Estate,Property,Agriculture,ESG Compliance,Environmental,Environment,Lingkungan,Science,Healthcare,Health,Health Law,Social Risk,Sosial,Tenaga Kerja,Human Resources,Press Releases,Information,Press,Documentation,Magazine,Consumer Goods,Consumer,Retail,Service,History,Podcast,Sports,Entertainment,Gallery"

def get_p(filename):
    return os.path.join(BASE_DIR, filename)

# Unified Service List
# TIER 0: Core News Ingestion — 5 parallel nodes (each handles a category tier)
TIER0 = [
    [PYTHON_EXE, get_p("news_service.py"), "--port", "5101", "--categories", NODE1_CATS],  # Core National
    [PYTHON_EXE, get_p("news_service.py"), "--port", "5102", "--categories", NODE2_CATS],  # Intel & Risk
    [PYTHON_EXE, get_p("news_service.py"), "--port", "5103", "--categories", NODE3_CATS],  # Legal & Military
    [PYTHON_EXE, get_p("news_service.py"), "--port", "5104", "--categories", NODE4_CATS],  # Industrial & Tech
    [PYTHON_EXE, get_p("news_service.py"), "--port", "5105", "--categories", NODE5_CATS],  # ESG & Social
    [PYTHON_EXE, get_p("backup_service.py")],                                              # Port 5004
]

# TIER 1: Intelligence & AI Engines
TIER1 = [
    [PYTHON_EXE, get_p("sentiment_service.py")],      # Port 5008
    [PYTHON_EXE, get_p("entity_service.py")],         # Port 5005
    [PYTHON_EXE, get_p("ta_service.py")],             # Port 5007
    [PYTHON_EXE, get_p("deep_ta_service.py")],        # Port 5200
]

# TIER 2: Geo-Sensing & Special Data
TIER2 = [
    [PYTHON_EXE, get_p("sky_service.py")],            # Port 5002
    [PYTHON_EXE, get_p("ais_service.py")],            # Port 8080
    [PYTHON_EXE, get_p("geo_data_service.py")],       # Port 8091
    [PYTHON_EXE, get_p("submarine_cable_service.py")],# Port 8120
    [PYTHON_EXE, get_p("satellite_visual_service.py")],# Port 8130
    [PYTHON_EXE, get_p("crypto_service.py")],         # Port 8085
    [PYTHON_EXE, get_p("forex_service.py")],          # Port 8086
    [PYTHON_EXE, get_p("commodity_service.py")],      # Port 8087
    [PYTHON_EXE, get_p("market_service.py")],         # Port 8088
    [PYTHON_EXE, get_p("oil_refinery_service.py")],   # Port 8089
    [PYTHON_EXE, get_p("disaster_service.py")],       # Port 8095
    [PYTHON_EXE, get_p("tv_service.py")],             # Port 5003
    [PYTHON_EXE, get_p("infrastructure_service.py")], # Port 8097
    [PYTHON_EXE, get_p("port_service.py")],           # Port 8098
    [PYTHON_EXE, get_p("industrial_zone_service.py")],# Port 8094
    [PYTHON_EXE, get_p("datacenter_service.py")],     # Port 8110
    [PYTHON_EXE, get_p("rail_station_service.py")],    # Port 8111
    [PYTHON_EXE, get_p("conflict_service.py")],        # Port 8140
    [PYTHON_EXE, get_p("government_facility_service.py")],# Port 8150
    [PYTHON_EXE, get_p("military_service.py")],        # Port 8160
    [PYTHON_EXE, get_p("crypto_stream_service.py")],   # Port 8092
]

# TIER 3: Strategic Assets & Ops
TIER3 = [
    [PYTHON_EXE, get_p("mines_service.py")],          # Port 8082
    [PYTHON_EXE, get_p(os.path.join("data", "power_plant_service.py"))], # Port 8093
    [PYTHON_EXE, get_p("oil_trade_service.py")],      # Port 8090
    [PYTHON_EXE, get_p("gnews_service.py")],          # Port 5006
    [PYTHON_EXE, get_p("vessel_intelligence_service.py")], # Port 8100 — Phase 4/5 Signal Engine
]

# TIER 4: DASHBOARD AGGREGATOR (Final Layer)
TIER4 = [
    [PYTHON_EXE, get_p("dashboard_service.py")],     # Port 8000
]

# TIER 5: EXTERNAL CONNECTORS (Telegram, Webhook, etc.)
TIER5 = [
    [PYTHON_EXE, get_p(os.path.join("telegram_bot", "main.py"))],
]

SERVICE_PORTS = {
    "news_service.py": [5101, 5102, 5103, 5104, 5105],
    "backup_service.py": [5004],
    "sentiment_service.py": [5008],
    "entity_service.py": [5005],
    "ta_service.py": [5007],
    "deep_ta_service.py": [5200],
    "sky_service.py": [5002],
    "ais_service.py": [8080],
    "geo_data_service.py": [8091],
    "submarine_cable_service.py": [8120],
    "satellite_visual_service.py": [8130],
    "crypto_service.py": [8085],
    "forex_service.py": [8086],
    "commodity_service.py": [8087],
    "market_service.py": [8088],
    "oil_refinery_service.py": [8089],
    "disaster_service.py": [8095],
    "tv_service.py": [5003],
    "infrastructure_service.py": [8097],
    "port_service.py": [8098],
    "mines_service.py": [8082],
    "power_plant_service.py": [8093],
    "oil_trade_service.py": [8090],
    "gnews_service.py": [5006],
    "vessel_intelligence_service.py": [8100],
    "industrial_zone_service.py": [8094],
    "datacenter_service.py": [8110],
    "rail_station_service.py": [8111],
    "conflict_service.py": [8140],
    "government_facility_service.py": [8150],
    "military_service.py": [8160],
    "crypto_stream_service.py": [8092],
    "dashboard_service.py": [8000]
}

def clean_port(port):
    if not port: return
    try:
        if os.name == 'nt':
            # Windows implementation
            cmd = f'netstat -ano | findstr LISTENING | findstr :{port}'
            output = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT).decode()
            
            pids_to_kill = set()
            for line in output.splitlines():
                line = line.strip()
                if f':{port} ' in line or f':{port}\t' in line:
                    parts = line.split()
                    if len(parts) >= 5:
                        pid = parts[-1]
                        if pid != '0': pids_to_kill.add(pid)
            
            for pid in pids_to_kill:
                print(f"[SYSTEM] PORT_{port} CONFLICT! FORCING SHUTDOWN PID_{pid}...")
                subprocess.run(f'taskkill /F /PID {pid}', shell=True, capture_output=True)
                time.sleep(1.2)
        else:
            # Linux/Ubuntu implementation
            try:
                # Using 'ss' or 'lsof' to find PID on Linux
                cmd = f"lsof -t -i:{port}"
                output = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT).decode().strip()
                if output:
                    pids = output.split('\n')
                    for pid in pids:
                        if pid:
                            print(f"[SYSTEM] PORT_{port} CONFLICT! FORCING SHUTDOWN PID_{pid}...")
                            subprocess.run(f'kill -9 {pid}', shell=True, capture_output=True)
                            time.sleep(0.5)
            except subprocess.CalledProcessError:
                pass # Port is clean
            
    except Exception as e:
        print(f"[SYSTEM] ERROR CLEANING PORT {port}: {e}")

PROCESSES = []


def log_relay(name, pipe):
    try:
        for line in iter(pipe.readline, b''):
            msg = line.decode('utf-8', errors='ignore').strip()
            if msg:
                print(f"[{name.upper():16}] {msg}")
    except:
        pass

def launch_cmd(cmd):
    try:
        name = os.path.basename(cmd[1])
        
        # Determine specific ports to clean for this instance
        target_ports = []
        # Check for explicit --port
        if "--port" in cmd:
            try:
                idx = cmd.index("--port")
                target_ports.append(cmd[idx+1])
            except: pass
        
        # Fallback to registry if no ports found (only clean registry defaults if no specific port requested)
        if not target_ports:
            target_ports = SERVICE_PORTS.get(name, [])
        
        # Aggressively clean ports
        for p_num in target_ports:
            clean_port(p_num)

        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        PROCESSES.append(p)
        threading.Thread(target=log_relay, args=(name, p.stdout), daemon=True).start()
        print(f"LAUNCHED Node: {name} on PID: {p.pid}")
    except Exception as e:
        print(f"FAILED to launch {cmd}: {e}")

def main():
    print("--- ASETPEDIA UNIFIED OPERATIONAL HUB ---")
    print(f"BOOTING COMPREHENSIVE CLUSTER FROM: {BASE_DIR}")
    
    # --- SYSTEM MODE (Read from .env) ---
    DEV_MODE = os.getenv("DEV_MODE", "True").lower() == "true"
    
    if DEV_MODE:
        print("[SYSTEM] !!! RUNNING IN DEVELOPMENT MODE !!!")
        print("[SYSTEM] Only activating essential modules for Entity Correlation")
        DEV_SERVICES = [
            [PYTHON_EXE, get_p("gnews_service.py")],           # Port 5006 (Intelligence Provider)
            [PYTHON_EXE, get_p("infrastructure_service.py")],
            [PYTHON_EXE, get_p("port_service.py")],
            [PYTHON_EXE, get_p(os.path.join("data", "power_plant_service.py"))],
            [PYTHON_EXE, get_p("industrial_zone_service.py")],
            [PYTHON_EXE, get_p("geo_data_service.py")],
            [PYTHON_EXE, get_p("crypto_stream_service.py")],
            [PYTHON_EXE, get_p("backup_service.py")],
            [PYTHON_EXE, get_p(os.path.join("telegram_bot", "main.py"))]
        ]
        for cmd in DEV_SERVICES:
            launch_cmd(cmd)
            time.sleep(1.0)
    else:
        WAVES = [TIER0, TIER1, TIER2, TIER3, TIER4, TIER5]
        for i, wave in enumerate(WAVES):
            print(f"\n[SYSTEM] === STARTING_WAVE_{i}_{len(wave)}_SERVICES ===")
            for cmd in wave:
                launch_cmd(cmd)
                time.sleep(1.0) # Increased for stability
            time.sleep(5.0) # Wait longer for services to warm up
    
    print("\nALL NODES INITIALIZED. CONSOLIDATED LOG STREAM ACTIVE.")
    
    try:
        while True:
            time.sleep(2)
            for p in PROCESSES:
                if p.poll() is not None:
                    print(f"CRITICAL: {p.args[1]} died. Global restart recommended.")
                    # In a real environment we'd respawn, but here we just warn
    except KeyboardInterrupt:
        print("\nSHUTTING DOWN ALL NODES...")
        for p in PROCESSES:
            p.terminate()

if __name__ == "__main__":
    main()
