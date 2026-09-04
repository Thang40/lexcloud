from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from app.extensions import get_users_table
import bcrypt

auth_bp = Blueprint('auth', __name__)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'email' not in session:
            flash('Please log in first.', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        if not email or not password:
            flash('Email and password are required.', 'danger')
            return redirect(url_for('auth.register'))

        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return redirect(url_for('auth.register'))

        users_table = get_users_table()
        try:
            existing = users_table.get_item(Key={'email': email})
            if 'Item' in existing:
                flash('Email already registered.', 'danger')
                return redirect(url_for('auth.register'))

            hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            users_table.put_item(Item={
                'email': email,
                'password_hash': hashed_password
            })
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('auth.login'))
        except Exception as e:
            flash(f'Registration failed: {str(e)}', 'danger')
            return redirect(url_for('auth.register'))

    return render_template('register.html')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')

        if not email or not password:
            flash('Email and password are required.', 'danger')
            return redirect(url_for('auth.login'))

        users_table = get_users_table()
        try:
            response = users_table.get_item(Key={'email': email})
            if 'Item' not in response:
                flash('Invalid email or password.', 'danger')
                return redirect(url_for('auth.login'))

            user = response['Item']
            if not bcrypt.checkpw(password.encode('utf-8'), user['password_hash'].encode('utf-8')):
                flash('Invalid email or password.', 'danger')
                return redirect(url_for('auth.login'))

            session['email'] = email
            flash(f'Welcome, {email}!', 'success')
            return redirect(url_for('main.dashboard'))
        except Exception as e:
            flash(f'Login failed: {str(e)}', 'danger')
            return redirect(url_for('auth.login'))

    return render_template('login.html')

@auth_bp.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))
