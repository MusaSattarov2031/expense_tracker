import mysql.connector
from mysql.connector import pooling 
from urllib.parse import urlparse
import os

DB_URL = os.getenv("DATABASE_URL")
cnx_pool = None 

def init_pool():
    """Initializes the connection pool. Returns the pool or None on failure."""
    global cnx_pool
    if not DB_URL:
        print("❌ ERROR: DATABASE_URL environment variable is missing.")
        return None
        
    try:
        url_without_query = DB_URL.split('?')[0]
        url = urlparse(url_without_query)
        
        db_config = {
            "host": url.hostname,
            "user": url.username,
            "password": url.password,
            "database": url.path[1:],
            "port": url.port,
            "ssl_disabled": False
        }
        
        # Create a pool of 5 connections
        new_pool = pooling.MySQLConnectionPool(
            pool_name="mypool",
            pool_size=5, 
            pool_reset_session=True,
            **db_config
        )
        print("✅ Database Pool Created Successfully!")
        return new_pool
        
    except Exception as e:
        print(f"❌ CRITICAL ERROR: Failed to create database pool: {e}")
        return None

def get_db_connection():
    """Gets a connection from the Pool. Initializes pool if needed."""
    global cnx_pool
    
    # 1. Try to initialize if pool is missing
    if cnx_pool is None:
        print("⚠️ Pool not found. Attempting to initialize...")
        cnx_pool = init_pool()
        
    # 2. If still None, we cannot proceed
    if cnx_pool is None:
        raise Exception("Database pool initialization failed. Check logs for details.")

    # 3. Get connection
    try:
        return cnx_pool.get_connection()
    except Exception as e:
        print(f"Error getting connection from pool: {e}")
        raise e

# --- Keep existing functions (ensure they use get_db_connection()) ---

def initialize_all_tables():
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # ACCOUNTS
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                account_id INT AUTO_INCREMENT PRIMARY KEY, 
                user_id INT NOT NULL, 
                account_name VARCHAR(100) NOT NULL, 
                account_type VARCHAR(50) NOT NULL, 
                current_balance DECIMAL(10,2) DEFAULT 0.00, 
                currency VARCHAR(3), 
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )
        """)
        # CATEGORIES
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                category_id INT AUTO_INCREMENT PRIMARY KEY, 
                user_id INT NOT NULL, 
                name VARCHAR(100) NOT NULL, 
                type VARCHAR(20) NOT NULL, 
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )
        """)
        # TRANSACTIONS
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                transaction_id INT AUTO_INCREMENT PRIMARY KEY, 
                user_id INT NOT NULL, 
                account_id INT NOT NULL, 
                category_id INT NOT NULL, 
                amount DECIMAL(10,2) NOT NULL, 
                transaction_date DATE NOT NULL, 
                note VARCHAR(255), 
                FOREIGN KEY(user_id) REFERENCES users(user_id), 
                FOREIGN KEY(account_id) REFERENCES accounts(account_id), 
                FOREIGN KEY(category_id) REFERENCES categories(category_id)
            )
        """)
        conn.commit()
        return True
    except Exception as e:
        print(f"Init Error: {e}")
        return False
    finally:
        if conn: conn.close()

def get_user_transactions(user_id):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
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
        if conn: conn.close()