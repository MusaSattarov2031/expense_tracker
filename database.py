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
            
def get_user_transactions(user_id):
    """Fetches all transactions for a given user ID."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        # We join tables to get meaningful names instead of just IDs
        query = """
        SELECT t.*, a.account_name, c.name AS category_name, c.type AS category_type
        FROM transactions t
        JOIN accounts a ON t.account_id = a.account_id
        JOIN categories c ON t.category_id = c.category_id
        WHERE t.user_id = %s
        ORDER BY t.transaction_date DESC;
        """
        cursor.execute(query, (user_id,))
        transactions = cursor.fetchall()
        return transactions
    except Exception as e:
        print(f"Error fetching transactions: {e}")
        return []
    finally:
        if conn and conn.is_connected():
            conn.close()            
