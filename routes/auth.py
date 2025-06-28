from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from flask_login import login_user, logout_user, login_required
from models.database import (
    authenticate_user, create_user, get_children, get_supabase_client,
    get_organizations, submit_observer_application
)
from config import Config
import uuid
from datetime import datetime
import json
import logging

# Create logger
logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__)



@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')

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
            session['organization_id'] = None  # Admin has no specific organization

            flash('Admin login successful!', 'success')
            return redirect(url_for('admin.dashboard'))

        # Check regular user (Observer/Parent/Principal)
        user = authenticate_user(email.lower(), password)
        if user:
            login_user(user)
            session.permanent = True
            session['user_id'] = user.id
            session['role'] = user.role
            session['name'] = user.name
            session['email'] = user.email
            session['child_id'] = user.child_id
            session['organization_id'] = user.organization_id  # CRITICAL: Store organization_id
            session['logged_in'] = True

            flash(f'Welcome, {user.name}!', 'success')

            # Redirect based on role
            if user.role == 'Observer':
                if not user.organization_id:
                    flash('No organization assigned to your account. Please contact administrator.', 'error')
                    session.clear()
                    return redirect(url_for('auth.login'))
                return redirect(url_for('observer.dashboard'))
            elif user.role == 'Parent':
                if not user.organization_id:
                    flash('No organization assigned to your account. Please contact administrator.', 'error')
                    session.clear()
                    return redirect(url_for('auth.login'))
                return redirect(url_for('parent.dashboard'))
            elif user.role == 'Principal':
                # Principal role support
                if not user.organization_id:
                    flash('No organization assigned to your account. Please contact administrator.', 'error')
                    session.clear()
                    return redirect(url_for('auth.login'))
                return redirect(url_for('principal.dashboard'))
            elif user.role == 'Admin':
                session['organization_id'] = None
                return redirect(url_for('admin.dashboard'))
            else:
                flash('Unknown role. Please contact administrator.', 'error')
                session.clear()
                return redirect(url_for('auth.login'))
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
        organization_id = request.form.get('organization_id', '')

        # Validation
        if not all([first_name, last_name, email, password, confirm_password]):
            flash('Please fill in all required fields', 'error')
            return render_template('auth/register.html',
                                   children=get_children(),
                                   organizations=get_organizations())

        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template('auth/register.html',
                                   children=get_children(),
                                   organizations=get_organizations())

        if len(password) < 8:
            flash('Password must be at least 8 characters', 'error')
            return render_template('auth/register.html',
                                   children=get_children(),
                                   organizations=get_organizations())

        # Create user
        user_data = {
            "id": str(uuid.uuid4()),
            "email": email,
            "name": f"{first_name} {last_name}",
            "password": password,
            "role": "Parent",
            "child_id": child_id if child_id else None,
            "organization_id": organization_id if organization_id else None,
            "created_at": datetime.now().isoformat()
        }

        if create_user(user_data):
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('auth.login'))
        else:
            flash('Registration failed. Email may already exist.', 'error')

    try:
        children = get_children()
        organizations = get_organizations()
    except Exception as e:
        children = []
        organizations = []

    return render_template('auth/register.html',
                           children=children,
                           organizations=organizations)


@auth_bp.route('/register_observer', methods=['GET', 'POST'])
def register_observer():
    """Observer registration - now redirects to application system"""
    flash(
        'Observer registration has been moved to the application system. Please apply through the Observer Application form.',
        'info')
    return redirect(url_for('observer.apply'))


@auth_bp.route('/apply_observer', methods=['GET', 'POST'])
def apply_observer():
    """Observer application form"""
    if request.method == 'POST':
        applicant_name = request.form.get('applicant_name', '').strip()
        applicant_email = request.form.get('applicant_email', '').strip().lower()
        applicant_phone = request.form.get('applicant_phone', '').strip()
        qualifications = request.form.get('qualifications', '').strip()
        experience_years = request.form.get('experience_years', '')
        motivation_text = request.form.get('motivation_text', '').strip()
        organization_id = request.form.get('organization_id', '')

        # Validation
        if not all(
                [applicant_name, applicant_email, qualifications, experience_years, motivation_text, organization_id]):
            flash('Please fill in all required fields', 'error')
            return render_template('observer/apply.html', organizations=get_organizations())

        try:
            experience_years = int(experience_years)
            if experience_years < 0:
                flash('Experience years must be a positive number', 'error')
                return render_template('observer/apply.html', organizations=get_organizations())
        except ValueError:
            flash('Experience years must be a valid number', 'error')
            return render_template('observer/apply.html', organizations=get_organizations())

        # Submit application
        try:
            result = submit_observer_application(
                applicant_name=applicant_name,
                applicant_email=applicant_email,
                applicant_phone=applicant_phone,
                qualifications=qualifications,
                experience_years=experience_years,
                motivation_text=motivation_text,
                organization_id=organization_id
            )

            if result:
                flash(
                    'Observer application submitted successfully! You will be notified once reviewed by the Principal or Administrator.',
                    'success')
                return redirect(url_for('landing'))
            else:
                flash('Application submission failed. Please try again.', 'error')

        except Exception as e:
            if 'duplicate key' in str(e) or '23505' in str(e):
                flash('An application with this email already exists.', 'error')
            else:
                flash(f'Application submission failed: {str(e)}', 'error')

    try:
        organizations = get_organizations()
    except Exception as e:
        organizations = []
        flash('Error loading organizations. Please try again later.', 'error')

    return render_template('observer/apply.html', organizations=organizations)


@auth_bp.route('/register_principal', methods=['GET', 'POST'])
def register_principal():
    """Principal registration - restricted to admin or specific access"""
    # Check if user is admin or has special access
    if not session.get('is_admin') and not request.args.get('admin_access'):
        flash('Access denied. Principal registration requires administrator approval.', 'error')
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        organization_id = request.form.get('organization_id', '')

        # Validation
        if not all([first_name, last_name, email, password, confirm_password, organization_id]):
            flash('Please fill in all required fields', 'error')
            return render_template('auth/register_principal.html', organizations=get_organizations())

        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template('auth/register_principal.html', organizations=get_organizations())

        if len(password) < 8:
            flash('Password must be at least 8 characters', 'error')
            return render_template('auth/register_principal.html', organizations=get_organizations())

        # Create principal user
        user_data = {
            "id": str(uuid.uuid4()),
            "email": email,
            "name": f"{first_name} {last_name}",
            "password": password,
            "role": "Principal",
            "organization_id": organization_id,
            "created_at": datetime.now().isoformat()
        }

        try:
            supabase = get_supabase_client()
            result = supabase.table('users').insert(user_data).execute()

            if result.data:
                flash('Principal registration successful! Please login.', 'success')
                return redirect(url_for('auth.login'))
            else:
                flash('Registration failed. Please try again.', 'error')

        except Exception as e:
            if 'duplicate key' in str(e) or '23505' in str(e):
                flash('Email already exists. Please use a different email.', 'error')
            else:
                flash(f'Registration failed: {str(e)}', 'error')

    try:
        organizations = get_organizations()
    except Exception as e:
        organizations = []

    return render_template('auth/register_principal.html', organizations=organizations)


@auth_bp.route('/apply_principal', methods=['GET', 'POST'])
def apply_principal():
    """Principal application form"""
    if request.method == 'POST':
        try:
            # Get form data
            applicant_name = request.form.get('applicant_name')
            applicant_email = request.form.get('applicant_email').strip().lower()
            applicant_phone = request.form.get('applicant_phone')
            qualifications = request.form.get('qualifications')
            experience_years = int(request.form.get('experience_years', 0))
            motivation_text = request.form.get('motivation_text')
            leadership_experience = request.form.get('leadership_experience')
            # Validation
            if not all([applicant_name, applicant_email, qualifications, motivation_text]):
                flash('Please fill in all required fields.', 'error')
                return render_template('auth/apply_principal.html')
            # Check if email already exists
            supabase = get_supabase_client()
            existing_user = supabase.table('users').select('email').eq('email', applicant_email).execute()
            if existing_user.data:
                flash('An account with this email already exists.', 'error')
                return render_template('auth/apply_principal.html')
            # Check if application already exists
            existing_app = supabase.table('principal_applications').select('email').eq('email', applicant_email).execute()
            if existing_app.data:
                flash('You have already submitted a principal application. Please wait for admin review.', 'warning')
                return render_template('auth/apply_principal.html')
            # Create principal application
            application_data = {
                'id': str(uuid.uuid4()),
                'applicant_name': applicant_name,
                'email': applicant_email,
                'phone': applicant_phone,
                'qualifications': qualifications,
                'experience_years': experience_years,
                'motivation_text': motivation_text,
                'leadership_experience': leadership_experience,
                'status': 'pending',
                'applied_at': datetime.now().isoformat(),
                'reviewed_at': None,
                'reviewed_by': None,
                'organization_id': None
            }
            result = supabase.table('principal_applications').insert(application_data).execute()
            if result.data:
                # Send notification to all admins
                send_principal_application_notification(application_data)
                flash('Principal application submitted successfully! You will be notified once reviewed by an administrator.', 'success')
                return redirect(url_for('auth.login'))
            else:
                flash('Error submitting application. Please try again.', 'error')
        except Exception as e:
            logger.error(f"Error submitting principal application: {e}")
            flash(f'Error submitting application: {str(e)}', 'error')
    return render_template('auth/apply_principal.html')


def send_principal_application_notification(application_data):
    """Send notification to all admins about new principal application"""
    try:
        supabase = get_supabase_client()

        # Get all admins
        admins = supabase.table('users').select('id, name, email').eq('role', 'Admin').execute()

        for admin in admins.data if admins.data else []:
            notification_data = {
                'id': str(uuid.uuid4()),
                'recipient_id': admin['id'],
                'sender_id': None,  # System notification
                'type': 'principal_application',
                'title': 'New Principal Application',
                'message': f'A new principal application has been submitted by {application_data["applicant_name"]} ({application_data["email"]})',
                'data': json.dumps({
                    'application_id': application_data['id'],
                    'applicant_name': application_data['applicant_name'],
                    'applicant_email': application_data['email'],
                    'experience_years': application_data['experience_years']
                }),
                'read': False,
                'created_at': datetime.now().isoformat()
            }

            supabase.table('notifications').insert(notification_data).execute()

    except Exception as e:
        logger.error(f"Error sending principal application notification: {e}")


@auth_bp.route('/logout')
def logout():
    logout_user()
    session.clear()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('landing'))


@auth_bp.route('/keepalive', methods=['POST'])
@login_required
def keepalive():
    """Session keepalive route for mobile session management"""
    session.modified = True
    return jsonify({'status': 'alive'})


@auth_bp.route('/session_status')
def session_status():
    """Check if user is logged in and return session info"""
    if session.get('logged_in'):
        return jsonify({
            'logged_in': True,
            'role': session.get('role'),
            'name': session.get('name'),
            'organization_id': session.get('organization_id')
        })
    else:
        return jsonify({'logged_in': False})


@auth_bp.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    """Password reset request"""
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()

        if not email:
            flash('Please enter your email address', 'error')
            return render_template('auth/forgot_password.html')

        # TODO: Implement password reset logic
        flash('Password reset functionality will be implemented soon. Please contact administrator.', 'info')
        return redirect(url_for('auth.login'))

    return render_template('auth/forgot_password.html')


@auth_bp.route('/verify_email/<token>')
def verify_email(token):
    """Email verification"""
    # TODO: Implement email verification logic
    flash('Email verification functionality will be implemented soon.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/check_access')
@login_required
def check_access():
    """Check user access permissions"""
    user_role = session.get('role')
    organization_id = session.get('organization_id')

    access_info = {
        'role': user_role,
        'organization_id': organization_id,
        'can_access_admin': user_role == 'Admin',
        'can_access_principal': user_role in ['Admin', 'Principal'],
        'can_access_observer': user_role in ['Admin', 'Principal', 'Observer'],
        'can_access_parent': user_role in ['Admin', 'Principal', 'Parent'],
        'has_organization': organization_id is not None
    }

    return jsonify(access_info)
