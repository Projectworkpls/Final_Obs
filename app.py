from flask import Flask, render_template, session, redirect, url_for
from flask_login import LoginManager, login_required, current_user
from flask_session import Session
import os
from datetime import timedelta
from config import Config
from models.database import init_supabase
from routes.auth import auth_bp
from routes.admin import admin_bp
from routes.observer import observer_bp
from routes.parent import parent_bp
from routes.messages import messages_bp

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

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

    # Initialize database
    init_supabase()

    # Register blueprints
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(observer_bp, url_prefix='/observer')
    app.register_blueprint(parent_bp, url_prefix='/parent')
    app.register_blueprint(messages_bp, url_prefix='/messages')

    # --- LANDING PAGE ---
    @app.route('/')
    def landing():
        if 'user_id' in session:
            role = session.get('role')
            if role == 'Admin':
                return redirect(url_for('admin.dashboard'))
            elif role == 'Observer':
                return redirect(url_for('observer.dashboard'))
            elif role == 'Parent':
                return redirect(url_for('parent.dashboard'))
        return render_template('landing.html')

    # --- PARENT SIGNUP PAGE ---
    @app.route('/parent/signup', methods=['GET', 'POST'])
    def parent_signup():
        if 'user_id' in session:
            # Already logged in, redirect to dashboard
            role = session.get('role')
            if role == 'Admin':
                return redirect(url_for('admin.dashboard'))
            elif role == 'Observer':
                return redirect(url_for('observer.dashboard'))
            elif role == 'Parent':
                return redirect(url_for('parent.dashboard'))
        # Use the new card-based register.html
        from models.database import get_children
        return render_template('auth/register.html', children=get_children())

    # --- OBSERVER SIGNUP PAGE ---
    @app.route('/observer/signup', methods=['GET', 'POST'])
    def observer_signup():
        if 'user_id' in session:
            # Already logged in, redirect to dashboard
            role = session.get('role')
            if role == 'Admin':
                return redirect(url_for('admin.dashboard'))
            elif role == 'Observer':
                return redirect(url_for('observer.dashboard'))
            elif role == 'Parent':
                return redirect(url_for('parent.dashboard'))
        # Handle POST in your observer_bp or here as needed
        return render_template('observer/signup.html')

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, host='0.0.0.0', port=5000)
