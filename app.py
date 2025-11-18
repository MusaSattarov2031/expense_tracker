import os
from flask import Flask, render_template, request, redirect, url_for, flash 
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import mysql.connector
from urllib.parse import urlparse


app=Flask(__name__)
app.secret_key="MEN BU YERDE YA;ALMADIM" #Essential for security

# --- DATABASE CONFIGURATION ---
# This grabs the URL from Render's environment variables.
# If running locally, replace the string below with your actual Aiven URL for testing.
DB_URL= os.getenv("DATABASE_URL")#Fix since Git Push protection dont allow to pass a password placeholder


def get_db_connection():
    # 1. Split the URL to remove query parameters (like ?ssl-mode=REQUIRED)
    url_without_query = DB_URL.split('?')[0]
    
    # 2. Parse the clean URL
    url = urlparse(url_without_query)
    
    # 3. Establish connection
    # NOTE: We manually add the required SSL configuration here for Aiven.
    return mysql.connector.connect(
        host=url.hostname,
        user=url.username,
        password=url.password,
        database=url.path[1:],
        port=url.port,
        ssl_mode='REQUIRED'  # Passed as a separate keyword argument
    )
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



# --- ROUTES ---
@app.route('/')
@login_required
def home():
    return render_template("index.html", name=current_user.username)
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

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- TEMPORARY SETUP ROUTE (Run once then delete) ---
@app.route('/init_db')
def init_db():
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
    return "Database Tables Created Successfully!"
if __name__=='__main__':
    app.run(host="0.0.0.0", port=5000)