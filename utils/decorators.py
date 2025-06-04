from functools import wraps
from flask import session, redirect, url_for, flash
from flask_login import current_user


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        print(f"Admin check - Session: {dict(session)}")  # Debug

        # Check for admin session
        if not session.get('is_admin') or session.get('role') != 'Admin':
            flash('Admin access required', 'error')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)

    return decorated_function


def observer_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or session.get('role') != 'Observer':
            flash('Observer access required', 'error')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)

    return decorated_function


def parent_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or session.get('role') != 'Parent':
            flash('Parent access required', 'error')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)

    return decorated_function
