import os
from flask import Flask, render_template, request, redirect, url_for, flash 
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from database import get_db_connection, initialize_all_tables, get_user_transactions
import mysql.connector
from urllib.parse import urlparse


app=Flask(__name__)
app.secret_key="MEN BU YERDE YA;ALMADIM" #Essential for security

#---Login Manager Setup---
login_manager=LoginManager()
login_manager.init_app(app)
login_manager.login_view='login'

class User(UserMixin):
    def __init__(self, id, username, password_hash):
        self.id=id
        self.username=username
        self.password_hash=password_hash

@login_manager.user_loader
def load_user(user_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
        user_data = cursor.fetchone()
        cursor.close()
        conn.close()
        if user_data:
            return User(user_data['user_id'], user_data['username'], user_data['password_hash'])
    except Exception as e:
        print(f"DB Error: {e}")
    return None     

def seed_data(user_id):
    """Creates default Account and Categories if they don't exist."""
    conn = get_db_connection()
    
    # FIX: Add buffered=True to prevent 'Unread result found' errors
    cursor = conn.cursor(buffered=True) 
    
    # 1. Create a default 'Cash' account
    cursor.execute("SELECT * FROM accounts WHERE user_id = %s", (user_id,))
    if not cursor.fetchone():
        cursor.execute("INSERT INTO accounts (user_id, account_name, account_type, current_balance) VALUES (%s, 'Cash', 'Cash', 0)", (user_id,))
        cursor.execute("INSERT INTO accounts (user_id, account_name, account_type, current_balance) VALUES (%s, 'Bank', 'Bank', 0)", (user_id,))
        conn.commit() # Commit changes immediately after inserting

    # 2. Create default Categories
    cursor.execute("SELECT * FROM categories WHERE user_id = %s", (user_id,))
    if not cursor.fetchone():
        defaults = [('Food', 'Expense'), ('Rent', 'Expense'), ('Salary', 'Income'), ('Fun', 'Expense')]
        for name, type in defaults:
            cursor.execute("INSERT INTO categories (user_id, name, type) VALUES (%s, %s, %s)", (user_id, name, type))
        conn.commit() # Commit changes immediately after inserting
    
    cursor.close()
    conn.close()



# --- ROUTES ---
@app.route('/')
@login_required
def home():
    seed_data(current_user.id)

    # 1. Get the filter from the URL (e.g., /?account_id=2)
    filter_account_id = request.args.get('account_id')

    # 2. Fetch ALL transactions first
    all_transactions = get_user_transactions(current_user.id)

    # 3. Filter the list if a specific account is selected
    if filter_account_id and filter_account_id != 'all':
        # We use str() because URL parameters are always strings
        transactions = [t for t in all_transactions if str(t['account_id']) == filter_account_id]
    else:
        transactions = all_transactions
        filter_account_id = 'all' # Default state

    # 4. Calculate Totals based on the FILTERED list
    total_balance = 0
    income = 0
    expense = 0
    
    for t in transactions:
        if t['category_type'] == 'Income':
            income += t['amount']
            total_balance += t['amount']
        else:
            expense += t['amount']
            total_balance -= t['amount']

    # 5. Fetch Accounts/Categories for dropdowns
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM accounts WHERE user_id = %s", (current_user.id,))
    accounts = cursor.fetchall()
    cursor.execute("SELECT * FROM categories WHERE user_id = %s", (current_user.id,))
    categories = cursor.fetchall()
    conn.close()

    return render_template('index.html', 
                           name=current_user.username,
                           transactions=transactions, # This is now the filtered list
                           total_balance=total_balance,
                           income=income,
                           expense=expense,
                           accounts=accounts,
                           categories=categories,
                           selected_account_id=filter_account_id)

@app.route('/add_transaction', methods=['POST'])
@login_required
def add_transaction():
    # 1. Get data from HTML Form
    amount = float(request.form.get('amount'))
    category_id = request.form.get('category_id')
    account_id = request.form.get('account_id')
    note = request.form.get('note')
    
    # 2. Insert into DB
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO transactions (user_id, account_id, category_id, amount, transaction_date, note)
        VALUES (%s, %s, %s, %s, NOW(), %s)
    """, (current_user.id, account_id, category_id, amount, note))
    
    conn.commit()
    conn.close()
    
    flash("Transaction Added!")
    return redirect(url_for('home'))
@app.route('/transactions')
@login_required
def transactions_page():
    # 1. Fetch full transaction history for the current user
    # We use the helper function we imported from database.py
    transactions = get_user_transactions(current_user.id)
    
    # 2. Render the separate Transactions page
    return render_template('transactions.html', 
                           name=current_user.username, 
                           transactions=transactions)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        user_data = cursor.fetchone()
        conn.close()
        
        if user_data and check_password_hash(user_data['password_hash'], password):
            user = User(user_data['user_id'], user_data['username'], user_data['password_hash'])
            login_user(user)
            return redirect(url_for('home'))
        else:
            flash('Invalid username or password')
            
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        hashed_password = generate_password_hash(password)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO users (username, password_hash) VALUES (%s, %s)", (username, hashed_password))
            conn.commit()
            flash('Registration successful! Please log in.')
            return redirect(url_for('login'))
        except mysql.connector.Error as err:
            flash(f"Error: {err}")
        finally:
            conn.close()
            
    return render_template('register.html')


@app.route('/settings')
@login_required
def settings():
    return render_template("settings.html", name=current_user.username)

@app.route('/add_account', methods=['POST'])
@login_required
def add_account():
    try:
        name = request.form.get('account_name')
        acc_type = request.form.get('account_type') # 'Bank', 'Cash', etc.
        balance = float(request.form.get('initial_balance', 0))
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO accounts (user_id, account_name, account_type, current_balance)
            VALUES (%s, %s, %s, %s)
        """, (current_user.id, name, acc_type, balance))
        conn.commit()
        conn.close()
        flash(f"Account '{name}' created!")
    except Exception as e:
        flash(f"Error adding account: {e}")
        
    return redirect(url_for('settings'))

@app.route('/add_category', methods=['POST'])
@login_required
def add_category():
    try:
        name = request.form.get('category_name')
        cat_type = request.form.get('category_type') # 'Income' or 'Expense'
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO categories (user_id, name, type)
            VALUES (%s, %s, %s)
        """, (current_user.id, name, cat_type))
        conn.commit()
        conn.close()
        flash(f"Category '{name}' added!")
    except Exception as e:
        flash(f"Error adding category: {e}")
        
    return redirect(url_for('settings'))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))
@app.route('/init_db')
def init_db():
    if initialize_all_tables():
        # You need to temporarily run the Users table creation as well, 
        # as it was previously inside this route.
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(50) NOT NULL UNIQUE,
                password_hash VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
        conn.close()

        return "Database Tables (Users, Accounts, Categories, Transactions) Created Successfully!"
    return "Database Initialization Failed. Check logs."
# app.py - Add this temporary migration route

@app.route('/migrate_currency')
@login_required
def migrate_currency():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 1. Add 'default_currency' to Users table
        cursor.execute("ALTER TABLE users ADD COLUMN default_currency VARCHAR(3) DEFAULT 'TRY'")
        
        # 2. Add 'currency' to Accounts table
        cursor.execute("ALTER TABLE accounts ADD COLUMN currency VARCHAR(3) DEFAULT 'TRY'")
        
        conn.commit()
        return "Migration Successful: Added currency columns!"
    except Exception as e:
        return f"Migration Failed (Maybe columns exist?): {e}"
    finally:
        conn.close()

if __name__=='__main__':
    app.run(host="0.0.0.0", port=5000)