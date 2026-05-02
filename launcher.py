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
    [PYTHON_EXE, get_p("entity_correlation_service.py")], # Port 8200
    [PYTHON_EXE, get_p("ta_service.py")],             # Port 5007
    [PYTHON_EXE, get_p("deep_ta_service.py")],        # Port 5200
    [PYTHON_EXE, get_p("research_service.py"), "--port", "5202"], # Port 5202
    [PYTHON_EXE, get_p("copilot_gateway.py")],        # Port 8500 — LLM Agentic Gateway
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
    # NEW TIER 2 SERVICES (OSINT Expansion)
    [PYTHON_EXE, get_p("bond_service.py")],             # Port 8145
    [PYTHON_EXE, get_p("volatility_service.py")],       # Port 8155
    [PYTHON_EXE, get_p("options_service.py")],          # Port 8165
    [PYTHON_EXE, get_p("capital_flow_service.py")],     # Port 8175
    [PYTHON_EXE, get_p("corporate_intel_service.py")],  # Port 8185
]

# TIER 3: Strategic Assets & Ops
TIER3 = [
    [PYTHON_EXE, get_p("mines_service.py")],          # Port 8082
    [PYTHON_EXE, get_p(os.path.join("data", "power_plant_service.py"))], # Port 8093
    [PYTHON_EXE, get_p("oil_trade_service.py")],      # Port 8090
    [PYTHON_EXE, get_p("gnews_service.py")],          # Port 5006
    [PYTHON_EXE, get_p("vessel_intelligence_service.py")], # Port 8100 — Phase 4/5 Signal Engine
    [PYTHON_EXE, get_p("price_intelligence_service.py")], # Port 8170
    # NEW TIER 3 SERVICES (OSINT Expansion)
    [PYTHON_EXE, get_p("regime_service.py")],          # Port 8195
    [PYTHON_EXE, get_p("esg_service.py")],             # Port 8190
    [PYTHON_EXE, get_p("macro_economics_service.py")], # Port 8205
    [PYTHON_EXE, get_p("supply_chain_service.py")],    # Port 8210
]

# TIER 4: DASHBOARD AGGREGATOR (Final Layer)
TIER4 = [
    [PYTHON_EXE, get_p("dashboard_service.py")],     # Port 8000
]

# TIER 5: EXTERNAL CONNECTORS (None)
TIER5 = []

SERVICE_PORTS = {
    "news_service.py": [5101, 5102, 5103, 5104, 5105],
    "backup_service.py": [5004],
    "sentiment_service.py": [5008],
    "entity_service.py": [5005],
    "ta_service.py": [5007],
    "deep_ta_service.py": [5200],
    "research_service.py": [5202],
    "copilot_gateway.py": [8500],
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
    "price_intelligence_service.py": [8170],
    "industrial_zone_service.py": [8094],
    "datacenter_service.py": [8110],
    "rail_station_service.py": [8111],
    "conflict_service.py": [8140],
    "government_facility_service.py": [8150],
    "military_service.py": [8160],
    "crypto_stream_service.py": [8092],
    "entity_correlation_service.py": [8200],
    "dashboard_service.py": [8000],
    # NEW TIER 1 SERVICES (OSINT Expansion)
    "bond_service.py": [8145],
    "volatility_service.py": [8155],
    "options_service.py": [8165],
    # NEW TIER 2 SERVICES
    "capital_flow_service.py": [8175],
    "corporate_intel_service.py": [8185],
    # NEW TIER 3 SERVICES
    "regime_service.py": [8195],
    "esg_service.py": [8190],
    "macro_economics_service.py": [8205],
    "supply_chain_service.py": [8210],
    # Telegram handled by price_intelligence_service.py

}

def clean_port(port):
    if not port: return
    try:
        if os.name == 'nt':
            # Windows implementation
            cmd = f'netstat -ano | findstr LISTENING | findstr :{port}'
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            output = res.stdout
            
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

PROCESS_REGISTRY = [] # List of { 'file': str, 'cmd': list, 'proc': Popen, 'mtime': float }

def log_relay(name, pipe):
    LOGS_DIR = os.path.join(BASE_DIR, 'logs')
    if not os.path.exists(LOGS_DIR):
        os.makedirs(LOGS_DIR, exist_ok=True)
    
    log_file = os.path.join(LOGS_DIR, name.replace('.py', '.log'))
    try:
        # Append mode to keep history, or 'w' to reset on each launch
        with open(log_file, 'a', encoding='utf-8') as f:
            for line in iter(pipe.readline, b''):
                msg = line.decode('utf-8', errors='ignore').strip()
                if msg:
                    print(f"[{name.upper():16}] {msg}")
                    f.write(f"{msg}\n")
                    f.flush()
    except Exception as e:
        print(f"LOG ERROR for {name}: {e}")

def launch_cmd(cmd):
    try:
        file_path = cmd[1]
        name = os.path.basename(file_path)
        mtime = os.path.getmtime(file_path) if os.path.exists(file_path) else 0
        
        # Determine specific ports to clean
        target_ports = []
        if "--port" in cmd:
            try:
                idx = cmd.index("--port")
                target_ports.append(cmd[idx+1])
            except: pass
        
        if not target_ports:
            target_ports = SERVICE_PORTS.get(name, [])
        
        for p_num in target_ports:
            clean_port(p_num)

        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        
        reg_entry = {
            'file': file_path,
            'cmd': cmd,
            'proc': p,
            'mtime': mtime,
            'name': name
        }
        PROCESS_REGISTRY.append(reg_entry)
        
        threading.Thread(target=log_relay, args=(name, p.stdout), daemon=True).start()
        print(f"LAUNCHED Node: {name} on PID: {p.pid}")
        return reg_entry
    except Exception as e:
        print(f"FAILED to launch {cmd}: {e}")
        return None

def main():
    print("--- ASETPEDIA UNIFIED OPERATIONAL HUB ---")
    print(f"BOOTING COMPREHENSIVE CLUSTER FROM: {BASE_DIR}")
    
    DEV_MODE = os.getenv("DEV_MODE", "True").lower() == "true"
    
    services_to_start = []
    if DEV_MODE:
        print("[SYSTEM] !!! RUNNING IN DEVELOPMENT MODE !!!")
        services_to_start = [
            [PYTHON_EXE, get_p("gnews_service.py")],
            [PYTHON_EXE, get_p("infrastructure_service.py")],
            [PYTHON_EXE, get_p("port_service.py")],
            [PYTHON_EXE, get_p(os.path.join("data", "power_plant_service.py"))],
            [PYTHON_EXE, get_p("industrial_zone_service.py")],
            [PYTHON_EXE, get_p("geo_data_service.py")],
            [PYTHON_EXE, get_p("crypto_stream_service.py")],
            [PYTHON_EXE, get_p("backup_service.py")],
            [PYTHON_EXE, get_p("entity_correlation_service.py")],
            [PYTHON_EXE, get_p("price_intelligence_service.py")],
            [PYTHON_EXE, get_p("ta_service.py")],
            [PYTHON_EXE, get_p("research_service.py"), "--port", "5202"],
            [PYTHON_EXE, get_p("copilot_gateway.py")],  # Port 8500 — LLM Agentic Gateway
        ]
    else:
        WAVES = [TIER0, TIER1, TIER2, TIER3, TIER4, TIER5]
        for wave in WAVES:
            services_to_start.extend(wave)

    for cmd in services_to_start:
        launch_cmd(cmd)
        time.sleep(0.5)
    
    print("\nALL NODES INITIALIZED. SMART WATCHER ACTIVE.")
    
    try:
        while True:
            time.sleep(3)
            # Check for crashes and file changes
            for i, entry in enumerate(PROCESS_REGISTRY):
                file_path = entry['file']
                proc = entry['proc']
                
                # 1. Check for Crash
                if proc.poll() is not None:
                    print(f"[RECOVERY] Service {entry['name']} died (PID: {proc.pid}). Restarting...")
                    PROCESS_REGISTRY.pop(i)
                    launch_cmd(entry['cmd'])
                    break # Break to avoid list mutation issues in loop

                # 2. Check for File Changes (Hot Reload)
                if os.path.exists(file_path):
                    current_mtime = os.path.getmtime(file_path)
                    if current_mtime > entry['mtime']:
                        print(f"[WATCHER] File Change Detected: {entry['name']}. Performing Selective Restart...")
                        
                        # Kill the specific process
                        try:
                            proc.terminate()
                            proc.wait(timeout=5)
                        except:
                            try: proc.kill()
                            except: pass
                        
                        # Restart
                        PROCESS_REGISTRY.pop(i)
                        launch_cmd(entry['cmd'])
                        break # Break to avoid list mutation issues
                        
    except KeyboardInterrupt:
        print("\nSHUTTING DOWN ALL NODES...")
        for entry in PROCESS_REGISTRY:
            try:
                entry['proc'].terminate()
            except: pass

if __name__ == "__main__":
    main()
