from functools import wraps
from flask import session, redirect, url_for, flash
import logging

# Set up logging to avoid console encoding issues
logger = logging.getLogger(__name__)


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # REMOVED: Problematic print statement that causes encoding issues
        # print(f"Admin check - Session: {dict(session)}")  # Debug

        # Use safe logging instead
        try:
            logger.info("Admin access check performed")
        except Exception:
            pass  # Skip logging if it fails

        if not session.get('logged_in') or session.get('role') != 'Admin':
            flash('Access denied. Admin privileges required.', 'error')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)

    return decorated_function


def login_required_role(required_role):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # SAFE: Use logging instead of print
            try:
                logger.info(f"Role check for: {required_role}")
            except Exception:
                pass

            if not session.get('logged_in'):
                flash('Please log in to access this page.', 'error')
                return redirect(url_for('auth.login'))

            user_role = session.get('role')
            if user_role != required_role:
                flash(f'Access denied. {required_role} privileges required.', 'error')
                return redirect(url_for('auth.login'))

            return f(*args, **kwargs)

        return decorated_function

    return decorator


def observer_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # SAFE: Use logging instead of print
        try:
            logger.info("Observer access check performed")
        except Exception:
            pass

        if not session.get('logged_in') or session.get('role') != 'Observer':
            flash('Access denied. Observer privileges required.', 'error')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)

    return decorated_function


def parent_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # SAFE: Use logging instead of print
        try:
            logger.info("Parent access check performed")
        except Exception:
            pass

        if not session.get('logged_in') or session.get('role') != 'Parent':
            flash('Access denied. Parent privileges required.', 'error')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)

    return decorated_function
