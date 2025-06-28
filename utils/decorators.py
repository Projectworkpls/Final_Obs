from functools import wraps
from flask import session, redirect, url_for, flash
import logging

# Set up logging to avoid console encoding issues
logger = logging.getLogger(__name__)


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # REMOVED: Problematic print statement that causes encoding issues
        # print(f"Admin check - Session: {dict(session)}") # Debug
        # Use safe logging instead
        try:
            logger.info("Admin access check performed")
        except Exception:
            pass  # Skip logging if it fails

        if not session.get('logged_in') or session.get('role') != 'Admin':
            flash('Access denied. Admin privileges required.', 'error')
            return redirect(url_for('auth.login'))
        
        # QUICK FIX: Convert "admin" string to proper UUID
        if session.get('user_id') == 'admin':
            session['user_id'] = '00000000-0000-0000-0000-000000000001'
            session.modified = True
            
        return f(*args, **kwargs)

    return decorated_function


# NEW: Principal role decorator
def principal_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            logger.info("Principal access check performed")
        except Exception:
            pass

        if not session.get('logged_in') or session.get('role') != 'Principal':
            flash('Access denied. Principal privileges required.', 'error')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)

    return decorated_function


# ENHANCED: Support for multiple roles including Principal
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


# NEW: Multi-role access decorator (for routes accessible by multiple roles)
def multi_role_required(*allowed_roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            try:
                logger.info(f"Multi-role check for: {allowed_roles}")
            except Exception:
                pass

            if not session.get('logged_in'):
                flash('Please log in to access this page.', 'error')
                return redirect(url_for('auth.login'))

            user_role = session.get('role')
            if user_role not in allowed_roles:
                flash(f'Access denied. Required roles: {", ".join(allowed_roles)}', 'error')
                return redirect(url_for('auth.login'))
            return f(*args, **kwargs)

        return decorated_function

    return decorator


# NEW: Organization-based access decorator
def organization_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            logger.info("Organization access check performed")
        except Exception:
            pass

        if not session.get('logged_in'):
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('auth.login'))

        # Check if user has organization assigned (except Admin)
        user_role = session.get('role')
        if user_role != 'Admin' and not session.get('organization_id'):
            flash('Access denied. No organization assigned.', 'error')
            return redirect(url_for('auth.login'))

        return f(*args, **kwargs)

    return decorated_function


# NEW: Same organization access decorator (for cross-user interactions)
def same_organization_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            logger.info("Same organization access check performed")
        except Exception:
            pass

        if not session.get('logged_in'):
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('auth.login'))

        # Admin can access all organizations
        user_role = session.get('role')
        if user_role == 'Admin':
            return f(*args, **kwargs)

        # Other users must have organization assigned
        if not session.get('organization_id'):
            flash('Access denied. No organization assigned.', 'error')
            return redirect(url_for('auth.login'))

        return f(*args, **kwargs)

    return decorated_function


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


# NEW: Enhanced role-based decorator with organization support
def role_required_with_org(required_role, check_organization=True):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            try:
                logger.info(f"Enhanced role check for: {required_role}, org_check: {check_organization}")
            except Exception:
                pass

            if not session.get('logged_in'):
                flash('Please log in to access this page.', 'error')
                return redirect(url_for('auth.login'))

            user_role = session.get('role')
            if user_role != required_role:
                flash(f'Access denied. {required_role} privileges required.', 'error')
                return redirect(url_for('auth.login'))

            # Check organization assignment if required (Admin exempt)
            if check_organization and required_role != 'Admin':
                if not session.get('organization_id'):
                    flash('Access denied. No organization assigned.', 'error')
                    return redirect(url_for('auth.login'))

            return f(*args, **kwargs)

        return decorated_function

    return decorator


# NEW: Peer review access decorator (for observers reviewing other observers' work)
def peer_review_access(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            logger.info("Peer review access check performed")
        except Exception:
            pass

        if not session.get('logged_in'):
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('auth.login'))

        user_role = session.get('role')
        # Only Observers and Principals can access peer reviews
        if user_role not in ['Observer', 'Principal', 'Admin']:
            flash('Access denied. Observer or Principal privileges required.', 'error')
            return redirect(url_for('auth.login'))

        return f(*args, **kwargs)

    return decorated_function


# NEW: Application review access (for reviewing observer applications)
def application_review_access(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            logger.info("Application review access check performed")
        except Exception:
            pass

        if not session.get('logged_in'):
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('auth.login'))

        user_role = session.get('role')
        # Only Admins and Principals can review applications
        if user_role not in ['Admin', 'Principal']:
            flash('Access denied. Admin or Principal privileges required.', 'error')
            return redirect(url_for('auth.login'))

        return f(*args, **kwargs)

    return decorated_function


# NEW: Feedback access decorator (for principal-observer feedback system)
def feedback_access(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            logger.info("Feedback access check performed")
        except Exception:
            pass

        if not session.get('logged_in'):
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('auth.login'))

        user_role = session.get('role')
        # Principals can give feedback, Observers can view feedback
        if user_role not in ['Principal', 'Observer', 'Admin']:
            flash('Access denied. Principal or Observer privileges required.', 'error')
            return redirect(url_for('auth.login'))

        return f(*args, **kwargs)

    return decorated_function


# UTILITY: Check if user can access specific organization data
def can_access_organization(user_role, user_org_id, target_org_id):
    """
    Utility function to check if a user can access data from a specific organization
    """
    # Admin can access all organizations
    if user_role == 'Admin':
        return True

    # Other users can only access their own organization
    return user_org_id == target_org_id


# UTILITY: Get accessible organization IDs for user
def get_accessible_organizations(user_role, user_org_id):
    """
    Utility function to get list of organization IDs the user can access
    """
    if user_role == 'Admin':
        # Admin can access all - return None to indicate no restriction
        return None
    else:
        # Other users can only access their own organization
        return [user_org_id] if user_org_id else []
