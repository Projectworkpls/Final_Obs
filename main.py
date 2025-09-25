# main.py
from flask import Flask, render_template, session, redirect, url_for, jsonify, send_from_directory, flash, request
from flask_login import LoginManager, login_required, current_user
from flask_session import Session
from flask_mail import Mail, Message
import os
import sys
import logging
import pytz
from datetime import datetime, timedelta

from config import Config
from models.database import init_supabase, check_database_health, get_supabase_client
from routes.auth import auth_bp
from routes.admin import admin_bp
from routes.observer import observer_bp
from routes.parent import parent_bp
from routes.messages import messages_bp
from routes.principal import principal_bp

# ----------------------------
# Mail + Scheduler setup
# ----------------------------
mail = Mail()
scheduler = None
SCHEDULER_STARTED = False  # guard to avoid double start in the same process

try:
    from flask_apscheduler import APScheduler
    scheduler = APScheduler()
    print("✅ APScheduler imported and initialized successfully")
except ImportError as e:
    print(f"⚠️ Warning: APScheduler not available: {e}")
    print("ℹ️ Scheduler functionality will be disabled")
    scheduler = None
except Exception as e:
    print(f"⚠️ Warning: APScheduler initialization failed: {e}")
    print("ℹ️ Scheduler functionality will be disabled")
    scheduler = None

# ----------------------------
# Windows stdout/stderr UTF-8
# ----------------------------
if sys.platform.startswith('win'):
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
    os.environ['PYTHONIOENCODING'] = 'utf-8'

# ----------------------------
# Logging
# ----------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('app.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# ----------------------------
# Email helper
# ----------------------------
def send_reminder_email(to, child_name, scheduled_time):
    """Send reminder email to observer with logging"""
    if not Config.is_email_configured():
        logger.warning("[MAIL] Email configuration missing! Set EMAIL_USER and EMAIL_PASSWORD.")
        print("[MAIL] ⚠️ Email configuration missing! Please set EMAIL_USER and EMAIL_PASSWORD environment variables.")
        return False

    subject = f"Session Reminder: Observation for {child_name}"
    body = (
        f"Dear Observer,\n\n"
        f"This is a reminder: you have an upcoming observation session for {child_name} scheduled at {scheduled_time} today.\n"
        f"Please submit your report after the session.\n\n"
        f"Thank you!"
    )
    try:
        msg = Message(subject, recipients=[to], body=body)
        mail.send(msg)
        logger.info(f"[MAIL] Sent reminder to {to} for session at {scheduled_time}.")
        print(f"[MAIL] ✅ Sent reminder to {to} for session at {scheduled_time}.")
        return True
    except Exception as e:
        logger.error(f"[MAIL] Failed to send email to {to}: {e}", exc_info=True)
        print(f"[MAIL] ❌ Failed to send email to {to}: {e}")
        return False

# ----------------------------
# Scheduled job
# ----------------------------
def check_and_send_observer_reminders():
    """Check for upcoming sessions and send reminders"""
    # Only run if scheduler exists (extra guard)
    if scheduler is None or not hasattr(scheduler, "app"):
        print("[SCHEDULER] Scheduler not initialized; skipping job")
        return

    with scheduler.app.app_context():
        IST = pytz.timezone('Asia/Kolkata')
        now_ist = datetime.now(IST)
        print(f"[SCHEDULER] Running reminder check at: {now_ist.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        supabase = get_supabase_client()
        schedules = supabase.table('scheduled_reports').select('*').eq('is_active', True).execute().data or []
        print(f"[SCHEDULER] Found {len(schedules)} active schedules")

        for sched in schedules:
            try:
                observer_id = sched['observer_id']
                child_id = sched['child_id']
                scheduled_time_str = sched['scheduled_time']  # e.g., "19:00:00"
                print(f"[SCHEDULER] Processing schedule: Observer {observer_id}, Child {child_id}, Time {scheduled_time_str}")

                # Parse scheduled time (IST)
                hour, minute = map(int, scheduled_time_str.split(':')[:2])
                session_dt_ist = now_ist.replace(hour=hour, minute=minute, second=0, microsecond=0)

                # If time passed today, schedule for tomorrow
                if session_dt_ist <= now_ist:
                    session_dt_ist = session_dt_ist + timedelta(days=1)

                mins_to_session = (session_dt_ist - now_ist).total_seconds() / 60.0
                print(f"[SCHEDULER] Session time: {session_dt_ist.strftime('%Y-%m-%d %H:%M:%S %Z')}")
                print(f"[SCHEDULER] Minutes to session: {mins_to_session:.1f}")

                # 29-31 minute window
                if 29.0 <= mins_to_session <= 31.0:
                    print(f"[SCHEDULER] Session within reminder window (29-31 min)")
                    today_str = now_ist.strftime('%Y-%m-%d')
                    obs_check = (
                        supabase.table('observations')
                        .select('id')
                        .eq('student_id', child_id)
                        .eq('username', observer_id)
                        .eq('date', today_str)
                        .execute()
                    )
                    print(f"[SCHEDULER] Existing observations today: {len(obs_check.data) if obs_check.data else 0}")

                    if not obs_check.data:
                        observer_response = supabase.table('users').select('email, name').eq('id', observer_id).execute()
                        child_response = supabase.table('children').select('name').eq('id', child_id).execute()

                        if observer_response.data and child_response.data:
                            observer = observer_response.data[0]
                            child = child_response.data[0]
                            print(f"[SCHEDULER] Sending email to {observer['email']} for child {child['name']}")
                            success = send_reminder_email(
                                observer['email'],
                                child['name'],
                                session_dt_ist.strftime('%I:%M %p')
                            )
                            print(f"[SCHEDULER] {'✅ Reminder sent' if success else '❌ Failed to send reminder'}")
                        else:
                            print("[SCHEDULER] Observer or child not found in database")
                    else:
                        print(f"[SCHEDULER] ℹ Observation already submitted today - no reminder needed")
                else:
                    print(f"[SCHEDULER] Outside reminder window (need 25-35 min, got {mins_to_session:.1f} min)")
            except Exception as e:
                print(f"[SCHEDULER] Error processing schedule {sched.get('id', 'unknown')}: {e}")

# ----------------------------
# App Factory
# ----------------------------
def create_app():
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
        static_url_path="/static",
    )
    app.config.from_object(Config)

    # Mail
    mail.init_app(app)

    # Scheduler: only init/start once per process
    global SCHEDULER_STARTED
    if scheduler is not None and not SCHEDULER_STARTED:
        try:
            scheduler.init_app(app)
            scheduler.start()
            SCHEDULER_STARTED = True

            scheduler.add_job(
                id='observer-reminders',
                func=check_and_send_observer_reminders,
                trigger='interval',
                minutes=2,          # reduce log spam
                max_instances=1,    # no overlap
                coalesce=True,      # collapse backlog
                misfire_grace_time=30
            )
        except Exception as e:
            logger.warning(f"APScheduler not started: {e}")

    # Jinja filter
    def datetimeformat(value, format='%Y-%m-%d %H:%M'):
        if not value:
            return ''
        try:
            dt = datetime.fromisoformat(value.replace('Z', '+00:00')) if isinstance(value, str) else value
            return dt.strftime(format)
        except Exception:
            return str(value)

    app.jinja_env.filters['datetimeformat'] = datetimeformat

    # ---- Sessions (server-side filesystem) ----
    app.config['SESSION_TYPE'] = 'filesystem'
    app.config['SESSION_PERMANENT'] = True
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)
    app.config['SESSION_USE_SIGNER'] = True
    app.config['SESSION_KEY_PREFIX'] = 'learning_observer:'
    app.config['SESSION_FILE_DIR'] = os.path.join(os.getcwd(), 'flask_session')

    Session(app)

    @app.before_request
    def refresh_session():
        if 'user_id' in session:
            session.permanent = True
            session.modified = True

    # Ensure upload folder exists (if configured)
    try:
        os.makedirs(app.config.get('UPLOAD_FOLDER', 'uploads'), exist_ok=True)
    except Exception as e:
        logger.warning(f"UPLOAD_FOLDER creation failed: {e}")

    # Ensure session folder exists (fallback to tmp if needed)
    try:
        os.makedirs(app.config['SESSION_FILE_DIR'], exist_ok=True)
        print(f"✅ Session folder created/verified: {app.config['SESSION_FILE_DIR']}")
    except Exception as e:
        print(f"⚠️ Warning: Failed to create session folder: {e}")
        import tempfile
        app.config['SESSION_FILE_DIR'] = tempfile.gettempdir()
        print(f"ℹ️ Using temporary directory for sessions: {app.config['SESSION_FILE_DIR']}")
        if Config.IS_PRODUCTION:
            print("ℹ️ Production environment detected - consider using Redis for sessions")

    # ---- Login Manager ----
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'

    @login_manager.user_loader
    def load_user(user_id):
        from models.database import get_user_by_id
        return get_user_by_id(user_id)

    # ---- Database init ----
    try:
        logger.info("Initializing Supabase connection...")
        init_supabase()
        logger.info("Supabase initialization successful")
    except Exception as e:
        logger.error(f"Failed to initialize Supabase: {e}")
        logger.warning("Application starting without database connection")

    # ---- Blueprints ----
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(observer_bp, url_prefix='/observer')
    app.register_blueprint(parent_bp, url_prefix='/parent')
    app.register_blueprint(messages_bp, url_prefix='/messages')
    app.register_blueprint(principal_bp, url_prefix='/principal')

    # ---- Routes ----
    @app.route('/favicon.ico')
    def favicon():
        return send_from_directory(os.path.join(app.root_path, 'static'),
                                   'favicon.ico', mimetype='image/vnd.microsoft.icon')

    @app.get("/healthz")
    def healthz():
        return jsonify(ok=True, ts=datetime.now().isoformat())

    @app.route('/health')
    def health_check():
        db_health = check_database_health()
        return jsonify({
            'app_status': 'running',
            'database': db_health,
            'timestamp': datetime.now().isoformat()
        })

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

    # --- SIGNUP / LANDINGS ---
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

    @app.route('/observer_landing')
    def observer_landing():
        return render_template('landing_pages/observer_landing.html')

    @app.route('/principal_landing')
    def principal_landing():
        return render_template('landing_pages/principal_landing.html')

    @app.route('/parent_landing')
    def parent_landing():
        return render_template('landing_pages/parent_landing.html')

    @app.route('/payment_form')
    def payment_form():
        return render_template('form.html')

    @app.route('/submit-trial', methods=['POST'])
    def submit_trial():
        parent_name = request.form.get('parent_name')
        logger.info(f"Received trial submission from: {parent_name}")
        flash('Thank you for starting your free trial! Our team will contact you shortly.', 'success')
        return redirect(url_for('landing'))

    # ---- Error handlers ----
    @app.errorhandler(500)
    def internal_error(error):
        logger.error(f"Internal server error: {error}")
        return render_template('errors/500.html'), 500

    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('errors/404.html'), 404

    # ---- Debug/status route for scheduler ----
    @app.route('/scheduler_status')
    def scheduler_status():
        IST = pytz.timezone('Asia/Kolkata')
        now_ist = datetime.now(IST)

        try:
            supabase = get_supabase_client()
            schedules = supabase.table('scheduled_reports').select('*').eq('is_active', True).execute().data or []
        except Exception:
            schedules = []

        status = {
            'current_time_ist': now_ist.strftime('%Y-%m-%d %H:%M:%S %Z'),
            'scheduler_available': scheduler is not None,
            'scheduler_running': getattr(scheduler, "running", False) if scheduler is not None else False,
            'active_schedules': len(schedules),
            'schedules': []
        }

        for sched in schedules:
            try:
                scheduled_time_str = sched['scheduled_time']
                hour, minute = map(int, scheduled_time_str.split(':')[:2])
                session_dt_ist = now_ist.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if session_dt_ist <= now_ist:
                    session_dt_ist = session_dt_ist + timedelta(days=1)
                mins_to_session = (session_dt_ist - now_ist).total_seconds() / 60.0

                status['schedules'].append({
                    'id': (sched.get('id') or '')[:8] + '...',
                    'scheduled_time': scheduled_time_str,
                    'minutes_to_session': round(mins_to_session, 1),
                    'in_reminder_window': 25.0 <= mins_to_session <= 35.0
                })
            except Exception:
                continue

        return jsonify(status)

    return app


# Optional: for local development runs only. Gunicorn uses wsgi.py in production.
if __name__ == "__main__":
    app = create_app()
    logger.info("Starting Flask application in development mode...")
    app.run(debug=True, host="0.0.0.0", port=5000)
