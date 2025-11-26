import requests
import os
import time
from flask import Flask, render_template, request, redirect, url_for, flash, g, jsonify
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from database import get_db_connection, initialize_all_tables, get_user_transactions
import mysql.connector
from urllib.parse import urlparse

app = Flask(__name__)
app.secret_key = "MEN BU YERDE YA;ALMADIM" 

#---Login Manager Setup---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, id, username, password_hash):
        self.id = id
        self.username = username
        self.password_hash = password_hash

# --- CONNECTION MANAGEMENT (FIXED) ---

# We don't strictly need before_request to set None if we check correctly in get_db
# But if we keep it, get_db must check 'is None'

@app.teardown_request
def teardown_request(exception):
    """Closes (returns to pool) the connection after every request."""
    # Pop 'db' from g. If it doesn't exist, return None.
    db = g.pop('db', None)
    
    if db is not None:
        try:
            # Only try to close if it's a valid connection object
            db.close() 
        except Exception as e:
            print(f"Error closing database connection: {e}")

def get_db():
    """Returns the cached pooled database connection for the current request."""
    # FIX: Check if 'db' is NOT in g OR if it is explicitly None
    if 'db' not in g or g.db is None:
        g.db = get_db_connection() 
    return g.db

@login_manager.user_loader
def load_user(user_id):
    try:
        conn = get_db() 
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
        user_data = cursor.fetchone()
        cursor.close()
        if user_data:
            return User(user_data['user_id'], user_data['username'], user_data['password_hash'])
    except Exception as e:
        print(f"DB Error in load_user: {e}")
    return None

# --- CURRENCY CACHE ---
RATE_CACHE = {}
CACHE_DURATION = 3600 * 24 

@app.route('/api/batch_add_transactions', methods=['POST'])
@login_required
def batch_add_transactions():
    try:
        data = request.get_json() # Get the JSON list sent from frontend
        transactions = data.get('transactions', [])
        
        if not transactions:
            return jsonify({'status': 'error', 'message': 'No transactions received'}), 400

        conn = get_db()
        cursor = conn.cursor()
        
        # Prepared statement for efficiency
        sql = """
            INSERT INTO transactions (user_id, account_id, category_id, amount, transaction_date, note)
            VALUES (%s, %s, %s, %s, NOW(), %s)
        """
        
        # Create a list of tuples for executemany
        values = []
        for t in transactions:
            values.append((
                current_user.id,
                t['account_id'],
                t['category_id'],
                float(t['amount']),
                t['note']
            ))
            
        # Execute all inserts in one go (Very Fast!)
        cursor.executemany(sql, values)
        conn.commit()
        
        return jsonify({'status': 'success', 'count': len(values)})
        
    except Exception as e:
        print(f"Batch Error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


def get_live_rates(base_currency):
    current_time = time.time()
    if base_currency in RATE_CACHE:
        cached_data = RATE_CACHE[base_currency]
        if current_time - cached_data['timestamp'] < CACHE_DURATION:
            return cached_data['rates']

    try:
        url = f"https://api.frankfurter.app/latest?from={base_currency}"
        response = requests.get(url, timeout=5)
        data = response.json()
        rates = data.get('rates', {})
        rates[base_currency] = 1.0 
        RATE_CACHE[base_currency] = {'rates': rates, 'timestamp': current_time}
        return rates
    except Exception as e:
        print(f"API Error: {e}")
        if base_currency in RATE_CACHE: return RATE_CACHE[base_currency]['rates']
        return {base_currency: 1.0, 'USD': 0.03, 'EUR': 0.029, 'TRY': 1.0}

def convert_currency_with_rates(amount, from_curr, rates_dict):
    if from_curr not in rates_dict: return amount 
    rate = rates_dict.get(from_curr, 1.0)
    if rate == 0: return amount
    return round(float(amount) / rate, 2)

def seed_data(user_id):
    conn = get_db()
    cursor = conn.cursor(buffered=True, dictionary=True) 
    
    cursor.execute("SELECT * FROM accounts WHERE user_id = %s", (user_id,))
    if not cursor.fetchone():
        cursor.execute("INSERT INTO accounts (user_id, account_name, account_type, current_balance, currency) VALUES (%s, 'Cash', 'Cash', 0, 'TRY')", (user_id,))
        cursor.execute("INSERT INTO accounts (user_id, account_name, account_type, current_balance, currency) VALUES (%s, 'Bank', 'Bank', 0, 'TRY')", (user_id,))
        conn.commit() 

    cursor.execute("SELECT * FROM categories WHERE user_id = %s", (user_id,))
    if not cursor.fetchone():
        defaults = [('Initial Balance', 'Income'), ('Food', 'Expense'), ('Rent', 'Expense'), ('Salary', 'Income'), ('Fun', 'Expense')]
        for name, type in defaults:
            cursor.execute("INSERT INTO categories (user_id, name, type) VALUES (%s, %s, %s)", (user_id, name, type))
        conn.commit() 
    cursor.close()

# --- ROUTES ---

@app.route('/')
@login_required
def home():
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("SELECT default_currency FROM users WHERE user_id = %s", (current_user.id,))
    user_row = cursor.fetchone()
    user_currency = user_row['default_currency'] if user_row and user_row['default_currency'] else 'TRY'
    
    cursor.execute("SELECT * FROM accounts WHERE user_id = %s", (current_user.id,))
    accounts = cursor.fetchall()
    cursor.execute("SELECT * FROM categories WHERE user_id = %s AND name!='Initial Balance'", (current_user.id,))
    categories = cursor.fetchall()
    #conn.close() # Explicit close here is fine as it returns to pool early

    live_rates = get_live_rates(user_currency)
    all_transactions = get_user_transactions(current_user.id)
    
    filter_account_id = request.args.get('account_id')
    if filter_account_id and filter_account_id != 'all':
        transactions = [t for t in all_transactions if str(t['account_id']) == filter_account_id]
    else:
        transactions = all_transactions
        filter_account_id = 'all'

    total_balance = 0
    income = 0
    expense = 0
    acc_currency_map = {acc['account_id']: acc['currency'] for acc in accounts}
    # We initialize a dictionary to track balance for each account in its OWN currency
    account_balances = {acc['account_id']: 0.0 for acc in accounts}

    for t in all_transactions:
        # A. Update Global Stats (Converted to Default Currency)
        trans_currency = acc_currency_map.get(t['account_id'], 'TRY')
        converted_amount = convert_currency_with_rates(t['amount'], trans_currency, live_rates)
        
        if t['category_name'] == 'Initial Balance':
            total_balance += converted_amount
            # Also update the specific account's balance
            if t['account_id'] in account_balances:
                account_balances[t['account_id']] += t['amount']
                
        elif t['category_type'] == 'Income':
            income += converted_amount
            total_balance += converted_amount
            if t['account_id'] in account_balances:
                account_balances[t['account_id']] += t['amount']
        else:
            expense += converted_amount
            total_balance -= converted_amount
            if t['account_id'] in account_balances:
                account_balances[t['account_id']] -= t['amount']

    # B. Inject the calculated balance back into the accounts list
    for acc in accounts:
        # Overwrite the static DB value with the calculated real-time value
        acc['current_balance'] = round(account_balances.get(acc['account_id'], 0), 2)

    for t in transactions:
        trans_currency = acc_currency_map.get(t['account_id'], 'TRY')
        converted_amount = convert_currency_with_rates(t['amount'], trans_currency, live_rates)
        
        if t['category_name'] == 'Initial Balance':
            total_balance += converted_amount
        elif t['category_type'] == 'Income':
            income += converted_amount
            total_balance += converted_amount
        else:
            expense += converted_amount
            total_balance -= converted_amount

    return render_template('index.html', 
                           name=current_user.username,
                           transactions=transactions,
                           all_transactions=all_transactions,
                           total_balance=round(total_balance, 2),
                           income=round(income, 2),
                           expense=round(expense, 2),
                           accounts=accounts,
                           categories=categories,
                           selected_account_id=filter_account_id,
                           currency_symbol=user_currency)

# --- ACTIONS ---

@app.route('/add_transaction', methods=['POST'])
@login_required
def add_transaction():
    amount = float(request.form.get('amount'))
    category_id = request.form.get('category_id')
    account_id = request.form.get('account_id')
    note = request.form.get('note')
    
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("INSERT INTO transactions (user_id, account_id, category_id, amount, transaction_date, note) VALUES (%s, %s, %s, %s, NOW(), %s)", 
                   (current_user.id, account_id, category_id, amount, note))
    conn.commit()
    flash("Transaction Added!")
    return redirect(url_for('home'))

@app.route('/add_account', methods=['POST'])
@login_required
def add_account():
    try:
        name = request.form.get('account_name')
        acc_type = request.form.get('account_type')
        currency = request.form.get('currency') 
        balance = float(request.form.get('initial_balance', 0))
        
        conn = get_db()
        cursor = conn.cursor(buffered=True, dictionary=True)
        cursor.execute("INSERT INTO accounts (user_id, account_name, account_type, current_balance, currency) VALUES (%s, %s, %s, %s, %s)", 
                       (current_user.id, name, acc_type, balance, currency))
        new_account_id = cursor.lastrowid

        if balance > 0:
            cursor.execute("SELECT category_id FROM categories WHERE user_id = %s AND name = 'Initial Balance'", (current_user.id,))
            cat_row = cursor.fetchone()
            if cat_row: category_id = cat_row['category_id']
            else:
                cursor.execute("INSERT INTO categories (user_id, name, type) VALUES (%s, 'Initial Balance', 'Income')", (current_user.id,))
                category_id = cursor.lastrowid
            cursor.execute("INSERT INTO transactions (user_id, account_id, category_id, amount, transaction_date, note) VALUES (%s, %s, %s, %s, NOW(), 'Opening Balance')", 
                           (current_user.id, new_account_id, category_id, balance))
        conn.commit()
        flash(f"Account '{name}' created!")
    except Exception as e:
        flash(f"Error: {e}")
    return redirect(url_for('home'))

@app.route('/add_category', methods=['POST'])
@login_required
def add_category():
    name = request.form.get('category_name')
    cat_type = request.form.get('category_type')
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO categories (user_id, name, type) VALUES (%s, %s, %s)", (current_user.id, name, cat_type))
    conn.commit()
    flash(f"Category '{name}' added!")
    return redirect(url_for('home'))

@app.route('/update_user_currency', methods=['POST'])
@login_required
def update_user_currency():
    new_currency = request.form.get('default_currency')
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET default_currency = %s WHERE user_id = %s", (new_currency, current_user.id))
    conn.commit()
    flash("Currency Updated!")
    return redirect(url_for('home'))

@app.route('/delete_account/<int:id>')
@login_required
def delete_account(id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM transactions WHERE account_id = %s AND user_id = %s", (id, current_user.id))
    cursor.execute("DELETE FROM accounts WHERE account_id = %s AND user_id = %s", (id, current_user.id))
    conn.commit()
    flash("Account deleted!")
    return redirect(url_for('home'))

@app.route('/delete_category/<int:id>')
@login_required
def delete_category(id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM transactions WHERE category_id = %s AND user_id = %s", (id, current_user.id))
    cursor.execute("DELETE FROM categories WHERE category_id = %s AND user_id = %s", (id, current_user.id))
    conn.commit()
    flash("Category deleted!")
    return redirect(url_for('home'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        user_data = cursor.fetchone()
        if user_data and check_password_hash(user_data['password_hash'], password):
            user = User(user_data['user_id'], user_data['username'], user_data['password_hash'])
            login_user(user)
            seed_data(user.id)
            return redirect(url_for('home'))
        flash('Invalid username or password')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        hashed_password = generate_password_hash(password)
        conn = get_db()
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO users (username, password_hash) VALUES (%s, %s)", (username, hashed_password))
            conn.commit()
            flash('Registration successful! Please log in.')
            return redirect(url_for('login'))
        except Exception as e:
            flash(f"Error: {e}")
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/init_db')
def init_db():
    if initialize_all_tables():
        # Manually handle connection for this one-off admin task
        conn = get_db_connection() 
        try:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INT AUTO_INCREMENT PRIMARY KEY,
                    username VARCHAR(50) NOT NULL UNIQUE,
                    password_hash VARCHAR(255) NOT NULL,
                    default_currency VARCHAR(3) DEFAULT 'TRY',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.commit()
            return "Database Tables Created Successfully!"
        finally:
            conn.close()
    return "Database Initialization Failed."

@app.route('/migrate_currency')
def migrate_currency():
    return "Migration done."

if __name__=='__main__':
    app.run(host="0.0.0.0", port=5000)