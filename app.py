from flask import Flask, render_template, session, redirect, url_for, jsonify, send_from_directory, flash, request
from flask_login import LoginManager, login_required, current_user
from flask_session import Session
import os
from datetime import timedelta, datetime
from config import Config
from models.database import init_supabase, check_database_health
from routes.auth import auth_bp
from routes.admin import admin_bp
from routes.observer import observer_bp
from routes.parent import parent_bp
from routes.messages import messages_bp
from routes.principal import principal_bp
import logging
import sys

# Fix Unicode encoding for Windows
if sys.platform.startswith('win'):
    import codecs

    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
    os.environ['PYTHONIOENCODING'] = 'utf-8'

# Configure logging with UTF-8 encoding
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('app.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Register datetimeformat filter for Jinja2 templates
    def datetimeformat(value, format='%Y-%m-%d %H:%M'):
        from datetime import datetime
        if not value:
            return ''
        try:
            if isinstance(value, str):
                dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
            else:
                dt = value
            return dt.strftime(format)
        except Exception:
            return str(value)

    app.jinja_env.filters['datetimeformat'] = datetimeformat

    # CRITICAL FIX: Configure server-side sessions to handle large data
    app.config['SESSION_TYPE'] = 'filesystem'
    app.config['SESSION_PERMANENT'] = True
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)
    app.config['SESSION_USE_SIGNER'] = True
    app.config['SESSION_KEY_PREFIX'] = 'learning_observer:'
    app.config['SESSION_FILE_DIR'] = os.path.join(os.getcwd(), 'flask_session')

    # Initialize server-side session
    Session(app)

    # CRITICAL FIX: Add session refresh logic to prevent expiration
    @app.before_request
    def refresh_session():
        if 'user_id' in session:
            session.permanent = True
            session.modified = True

    # Ensure upload folder exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    # Ensure session folder exists
    os.makedirs(app.config['SESSION_FILE_DIR'], exist_ok=True)

    # Initialize Login Manager
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'

    @login_manager.user_loader
    def load_user(user_id):
        from models.database import get_user_by_id
        return get_user_by_id(user_id)

    # Initialize database with better error handling
    try:
        logger.info("Initializing Supabase connection...")
        init_supabase()
        logger.info("Supabase initialization successful")
    except Exception as e:
        logger.error(f"Failed to initialize Supabase: {e}")
        logger.warning("Application starting without database connection")
        # Don't exit - allow app to start for debugging

    # Register blueprints
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(observer_bp, url_prefix='/observer')
    app.register_blueprint(parent_bp, url_prefix='/parent')
    app.register_blueprint(messages_bp, url_prefix='/messages')
    app.register_blueprint(principal_bp, url_prefix='/principal')

    # FIX: Add favicon route to prevent 404 errors
    @app.route('/favicon.ico')
    def favicon():
        return send_from_directory(os.path.join(app.root_path, 'static'),
                                   'favicon.ico', mimetype='image/vnd.microsoft.icon')

    # Health check endpoint
    @app.route('/health')
    def health_check():
        db_health = check_database_health()
        return jsonify({
            'app_status': 'running',
            'database': db_health,
            'timestamp': datetime.now().isoformat()
        })

    # Database connection test endpoint
    @app.route('/test-db')
    def test_db():
        try:
            from models.database import test_supabase_connection
            success, message = test_supabase_connection()
            return jsonify({
                'success': success,
                'message': message,
                'timestamp': datetime.now().isoformat()
            })
        except Exception as e:
            return jsonify({
                'success': False,
                'message': f'Database test failed: {str(e)}',
                'timestamp': datetime.now().isoformat()
            })

    # --- LANDING PAGE ---
    @app.route('/')
    def landing():
        if 'user_id' in session:
            role = session.get('role')
            if role == 'Admin':
                return redirect(url_for('admin.dashboard'))
            elif role == 'Principal':
                return redirect(url_for('principal.dashboard'))
            elif role == 'Observer':
                return redirect(url_for('observer.dashboard'))
            elif role == 'Parent':
                return redirect(url_for('parent.dashboard'))
        return render_template('landing.html')

    # --- PARENT SIGNUP PAGE ---
    @app.route('/parent/signup', methods=['GET', 'POST'])
    def parent_signup():
        if 'user_id' in session:
            role = session.get('role')
            if role == 'Admin':
                return redirect(url_for('admin.dashboard'))
            elif role == 'Principal':
                return redirect(url_for('principal.dashboard'))
            elif role == 'Observer':
                return redirect(url_for('observer.dashboard'))
            elif role == 'Parent':
                return redirect(url_for('parent.dashboard'))

        try:
            from models.database import get_children, get_organizations
            return render_template('auth/register.html',
                                   children=get_children(),
                                   organizations=get_organizations())
        except Exception as e:
            logger.error(f"Error loading signup page: {e}")
            return render_template('auth/register.html',
                                   children=[],
                                   organizations=[])

    # --- OBSERVER SIGNUP PAGE ---
    @app.route('/observer/signup', methods=['GET', 'POST'])
    def observer_signup():
        if 'user_id' in session:
            role = session.get('role')
            if role == 'Admin':
                return redirect(url_for('admin.dashboard'))
            elif role == 'Principal':
                return redirect(url_for('principal.dashboard'))
            elif role == 'Observer':
                return redirect(url_for('observer.dashboard'))
            elif role == 'Parent':
                return redirect(url_for('parent.dashboard'))

        return redirect(url_for('observer.apply'))

    # --- OBSERVER LANDING PAGE ---
    @app.route('/observer_landing')
    def observer_landing():
        return render_template('landing_pages/observer_landing.html')

    # --- PRINCIPAL LANDING PAGE ---
    @app.route('/principal_landing')
    def principal_landing():
        return render_template('landing_pages/principal_landing.html')

    # --- PARENT LANDING PAGE ---
    @app.route('/parent_landing')
    def parent_landing():
        return render_template('landing_pages/parent_landing.html')

    # --- PAYMENT FORM PAGE ---
    @app.route('/payment_form')
    def payment_form():
        return render_template('form.html')

    # --- TRIAL SUBMISSION ---
    @app.route('/submit-trial', methods=['POST'])
    def submit_trial():
        # Process form data here in the future
        parent_name = request.form.get('parent_name')
        logger.info(f"Received trial submission from: {parent_name}")
        flash('Thank you for starting your free trial! Our team will contact you shortly.', 'success')
        return redirect(url_for('landing'))

    # Error handlers
    @app.errorhandler(500)
    def internal_error(error):
        logger.error(f"Internal server error: {error}")
        return render_template('errors/500.html'), 500

    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('errors/404.html'), 404

    return app


if __name__ == '__main__':
    try:
        app = create_app()
        logger.info("Starting Flask application...")
        app.run(debug=True, host='0.0.0.0', port=5000)
    except Exception as e:
        logger.error(f"Failed to start application: {e}")
        print(f"Application startup failed: {e}")
