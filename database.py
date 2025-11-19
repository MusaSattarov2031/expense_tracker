#---Creating Accounts, Categories, Transaction Tables---
import mysql.connector
from urllib.parse import urlparse
import os

DB_URL=os.getenv("DATABASE_URL")

def get_db_connection():
    if not DB_URL:
        raise ValueError("DATABASE_URL environment variable is not set.")
    url_without_query=DB_URL.split('?')[0]
    url=urlparse(url_without_query)

    return mysql.connector.connect(
        host=url.hostname,
        user=url.username,
        password=url.password,
        database=url.path[1:],
        port=url.port,
        ssl_disabled=False
    )

def initialize_all_tables():
    try:
        conn=get_db_connection()
        cursor=conn.cursor()
        #ACCOUNTS TABLE
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS accounts(
                account_id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                account_name VARCHAR(100) NOT NULL,
                account_type VARCHAR(50) NOT NULL,
                current_balance DECIMAL(10, 2) DEFAULT 0.00,
                FOREIGN KEY (user_id) REFERENCES  users(user_id)
            );
        """)
        #CATEGORIES
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                category_id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                name VARCHAR(100) NOT NULL,
                type VARCHAR(20) NOT NULL, -- e.g., 'Expense', 'Income'
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );
        """)
        # 3. TRANSACTIONS Table: The main data table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                transaction_id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                account_id INT NOT NULL,
                category_id INT NOT NULL,
                amount DECIMAL(10, 2) NOT NULL,
                transaction_date DATE NOT NULL,
                note VARCHAR(255),
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (account_id) REFERENCES accounts(account_id),
                FOREIGN KEY (category_id) REFERENCES categories(category_id)
            );
        """)

        conn.commit()
        return True
    except mysql.connector.Error as err:
        print(f"Database Initialization Error: {err}")
        return False
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()
            

#Run once to create a tables
def creating():
    pass