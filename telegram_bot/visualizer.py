import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
import os
import uuid
from datetime import datetime

class MarketVisualizer:
    @staticmethod
    def generate_ohlc_chart(symbol, history_data):
        """
        Generates a temporary chart for the given symbol and history.
        Returns the path to the temporary file.
        """
        if not history_data or len(history_data) < 2:
            return None

        # Convert to DataFrame
        df = pd.DataFrame(history_data)
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')

        plt.figure(figsize=(10, 6))
        plt.style.use('dark_background')
        
        # Plot Close Price
        plt.plot(df['date'], df['close'], color='#00ff88', linewidth=2, label='Close Price')
        
        # Add Title and Labels
        plt.title(f"Asetpedia Intelligence: {symbol} Performance", color='white', fontsize=14, pad=20)
        plt.grid(True, linestyle='--', alpha=0.3)
        
        # Format dates on x-axis
        plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%d %b'))
        plt.xticks(rotation=45)
        
        # Add Volume as background bars (normalized)
        ax2 = plt.gca().twinx()
        ax2.bar(df['date'], df['volume'], color='#ffffff', alpha=0.1, label='Volume')
        ax2.get_yaxis().set_visible(False)

        plt.tight_layout()

        # Save to temp file
        temp_dir = "temp_charts"
        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)
            
        file_name = f"{symbol}_{uuid.uuid4().hex[:8]}.png"
        file_path = os.path.join(temp_dir, file_name)
        plt.savefig(file_path)
        plt.close()
        
        return file_path

    @staticmethod
    def cleanup(file_path):
        """Deletes the temporary chart file."""
        try:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            print(f"Error cleaning up chart: {e}")
