import mysql.connector
import csv
import os
from db import get_db_connection

def setup_accident_table():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Create table
    cursor.execute("DROP TABLE IF EXISTS oil_refinery_accidents")
    cursor.execute("""
        CREATE TABLE oil_refinery_accidents (
            id INT AUTO_INCREMENT PRIMARY KEY,
            no INT,
            location VARCHAR(255),
            event_date DATE,
            facility_name VARCHAR(255),
            operator VARCHAR(255),
            ownership_type VARCHAR(100),
            capacity VARCHAR(100),
            cause TEXT,
            casualties TEXT,
            impact TEXT,
            notes TEXT
        )
    """)
    print("Table 'oil_refinery_accidents' created.")

    # Load data from CSV
    csv_file_path = '../data_accident.csv'
    with open(csv_file_path, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            sql = """
                INSERT INTO oil_refinery_accidents 
                (no, location, event_date, facility_name, operator, ownership_type, capacity, cause, casualties, impact, notes) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            
            # Handle empty or invalid dates if necessary
            date_val = row['Date']
            if not date_val or date_val.lower() == 'not reported':
                date_val = None
            
            values = (
                row['No'],
                row['Location'],
                date_val,
                row['Facility Name'],
                row['Company / Operator'],
                row['Ownership Type'],
                row['Capacity'],
                row['Cause'],
                row['Casualties'],
                row['Total Loss / Impact'],
                row['Notes']
            )
            cursor.execute(sql, values)

    conn.commit()
    print(f"Data imported successfully from {csv_file_path}.")
    
    cursor.close()
    conn.close()

if __name__ == "__main__":
    setup_accident_table()
