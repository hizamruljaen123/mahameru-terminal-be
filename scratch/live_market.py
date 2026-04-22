import asyncio
import json
import websockets
import sys
import os
import shutil
from datetime import datetime

# UI Configuration
ROWS_TO_SHOW = 15
DEPTH_BAR_MAX = 20

# Professional Palette
C_BG = "\033[48;5;234m"
C_WHITE = "\033[38;5;255m"
C_GREEN = "\033[38;5;48m"
C_RED = "\033[38;5;196m"
C_GRAY = "\033[38;5;242m"
C_GOLD = "\033[38;5;214m"
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
CLEAR = "\033[2J\033[H"

def get_depth_bar(qty, max_qty, color):
    if max_qty == 0: return ""
    size = int((float(qty) / max_qty) * DEPTH_BAR_MAX)
    return color + "█" * size + C_RESET

async def stream_orderbook(symbol="btcusdt"):
    url = f"wss://stream.binance.com:9443/ws/{symbol.lower()}@depth20@100ms"
    
    # Enable Windows Terminal ANSI
    if os.name == 'nt': os.system('color')
    
    async with websockets.connect(url) as websocket:
        sys.stdout.write("\033[?25l") # Hide cursor
        
        while True:
            try:
                data = await websocket.recv()
                msg = json.loads(data)
                
                bids = msg.get('b', [])[:ROWS_TO_SHOW]
                asks = msg.get('a', [])[:ROWS_TO_SHOW]
                
                if not bids or not asks: continue

                # Calculate Max Qty for Scaling Bars
                max_b_qty = max([float(x[1]) for x in bids]) if bids else 1
                max_a_qty = max([float(x[1]) for x in asks]) if asks else 1
                
                # Terminal Width check
                columns, _ = shutil.get_terminal_size()
                col_width = (columns // 2) - 2

                output = [CLEAR]
                # Header
                header = f" {C_GOLD}ASETPEDIA TERMINAL {C_RESET} | {C_BOLD}{symbol.upper()}{C_RESET} | {datetime.now().strftime('%H:%M:%S.%f')[:-3]}"
                output.append(header.center(columns))
                output.append("═" * columns)

                # Table Header
                col_h = f"{C_GRAY}{'DEPTH':>10} {'AMOUNT':>12} {'BID PRICE':>12}{C_RESET}  ║  {C_GRAY}{'ASK PRICE':<12} {'AMOUNT':<12} {'DEPTH':<10}{C_RESET}"
                output.append(col_h.center(columns))
                output.append("─" * columns)

                # Rows
                for i in range(ROWS_TO_SHOW):
                    # Bid Side (Left)
                    b_p, b_q = bids[i] if i < len(bids) else ("0", "0")
                    b_bar = get_depth_bar(b_q, max_b_qty, C_GREEN)
                    bid_line = f"{b_bar:>10} {C_WHITE}{float(b_q):>12.4f}{C_RESET} {C_GREEN}{C_BOLD}{float(b_p):>12.2f}{C_RESET}"
                    
                    # Ask Side (Right)
                    # We show Asks starting from cheapest (bottom of ask list in ladder, but top row in side-by-side)
                    a_p, a_q = asks[i] if i < len(asks) else ("0", "0")
                    a_bar = get_depth_bar(a_q, max_a_qty, C_RED)
                    ask_line = f"{C_RED}{C_BOLD}{float(a_p):<12.2f}{C_RESET} {C_WHITE}{float(a_q):<12.4f}{C_RESET} {a_bar:<10}"
                    
                    row = f" {bid_line}  ║  {ask_line}"
                    output.append(row.center(columns))

                output.append("═" * columns)
                
                # Spread info
                spread = float(asks[0][0]) - float(bids[0][0])
                spread_pct = (spread / float(asks[0][0])) * 100
                footer = f"{C_GRAY}SPREAD: {C_WHITE}{spread:.2f} ({spread_pct:.4f}%){C_RESET} | {C_GRAY}LIQUIDITY: {C_GREEN}{max_b_qty:.2f}B{C_RESET}/{C_RED}{max_a_qty:.2f}A{C_RESET}"
                output.append(footer.center(columns))

                sys.stdout.write("\n".join(output) + "\n")
                sys.stdout.flush()

            except Exception as e:
                output.append(f"Error: {e}")
                sys.stdout.write("\n".join(output) + "\n")

if __name__ == "__main__":
    try:
        asyncio.run(stream_orderbook("BTCUSDT"))
    except KeyboardInterrupt:
        sys.stdout.write("\033[?25h\nStream Terminated.\n")
