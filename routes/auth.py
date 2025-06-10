from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_user, logout_user, login_required
from models.database import authenticate_user, create_user, get_children
from config import Config
import uuid

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')

        # Removed print statements to avoid OSError

        # Check admin credentials first (case-sensitive comparison)
        if email == Config.ADMIN_USER and password == Config.ADMIN_PASS:
            # Clear any existing session data
            session.clear()

            # Set session variables for admin
            session.permanent = True
            session['user_id'] = 'admin'
            session['role'] = 'Admin'
            session['name'] = 'Admin'
            session['email'] = email
            session['logged_in'] = True
            session['is_admin'] = True

            # Removed print statements

            flash('Admin login successful!', 'success')
            return redirect(url_for('admin.dashboard'))

        # Check regular user (Observer/Parent)
        user = authenticate_user(email.lower(), password)
        if user:
            login_user(user)
            session.permanent = True
            session['user_id'] = user.id
            session['role'] = user.role
            session['name'] = user.name
            session['email'] = user.email
            session['child_id'] = user.child_id
            session['logged_in'] = True

            if user.role == 'Observer':
                return redirect(url_for('observer.dashboard'))
            elif user.role == 'Parent':
                return redirect(url_for('parent.dashboard'))
        else:
            flash('Invalid email or password', 'error')

    return render_template('auth/login.html')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        child_id = request.form.get('child_id', '')

        # Validation
        if not all([first_name, last_name, email, password, confirm_password]):
            flash('Please fill in all required fields', 'error')
            return render_template('auth/register.html', children=get_children())

        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template('auth/register.html', children=get_children())

        if len(password) < 8:
            flash('Password must be at least 8 characters', 'error')
            return render_template('auth/register.html', children=get_children())

        # Create user
        user_data = {
            "id": str(uuid.uuid4()),
            "email": email,
            "name": f"{first_name} {last_name}",
            "password": password,
            "role": "Parent",
            "child_id": child_id if child_id else None
        }

        if create_user(user_data):
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('auth.login'))
        else:
            flash('Registration failed. Email may already exist.', 'error')

    return render_template('auth/register.html', children=get_children())


@auth_bp.route('/register_observer', methods=['GET', 'POST'])
def register_observer():
    if request.method == 'POST':
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        qualification = request.form.get('qualification', '').strip()
        experience = request.form.get('experience', '')
        bio = request.form.get('bio', '').strip()

        # Validation
        if not all([first_name, last_name, email, password, confirm_password, qualification, experience, bio]):
            flash('Please fill in all required fields', 'error')
            return render_template('auth/register_observer.html')

        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template('auth/register_observer.html')

        if len(password) < 8:
            flash('Password must be at least 8 characters', 'error')
            return render_template('auth/register_observer.html')

        # Create user
        user_data = {
            "id": str(uuid.uuid4()),
            "email": email,
            "name": f"{first_name} {last_name}",
            "password": password,
            "role": "Observer",
            "qualification": qualification,
            "experience": experience,
            "bio": bio
        }

        if create_user(user_data):
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('auth.login'))
        else:
            flash('Registration failed. Email may already exist.', 'error')

    return render_template('auth/register_observer.html')


@auth_bp.route('/logout')
def logout():
    logout_user()
    session.clear()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('landing'))
