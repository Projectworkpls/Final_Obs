import os
from dotenv import load_dotenv
from datetime import timedelta

load_dotenv()


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key'

    # Enhanced session configuration to prevent expiration issues
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)  # Session expires after 24 hours
    SESSION_COOKIE_SECURE = False  # Set to True in production with HTTPS
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_REFRESH_EACH_REQUEST = True  # Refresh session on each request

    # Additional session security settings
    SESSION_COOKIE_NAME = 'learning_observer_session'
    SESSION_COOKIE_DOMAIN = None  # Use default domain
    SESSION_COOKIE_PATH = '/'

    # API Keys and Database Configuration
    SUPABASE_URL = os.environ.get('SUPABASE_URL')
    SUPABASE_KEY = os.environ.get('SUPABASE_KEY')
    GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY')
    GROQ_API_KEY = os.environ.get('GROQ_API_KEY')
    OCR_API_KEY = os.environ.get('OCR_API_KEY')
    ASSEMBLYAI_API_KEY = os.environ.get('ASSEMBLYAI_API_KEY')
    EMAIL_PASSWORD = os.environ.get('EMAIL_PASSWORD')
    EMAIL_USER = os.environ.get('EMAIL_USER')
    ADMIN_USER = os.environ.get('ADMIN_USER')
    ADMIN_PASS = os.environ.get('ADMIN_PASS')

    # File Upload Configuration
    UPLOAD_FOLDER = 'static/uploads'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size

    # Mobile optimization settings
    MOBILE_USER_AGENTS = [
        'android', 'iphone', 'mobile', 'blackberry',
        'windows phone', 'opera mini', 'iemobile'
    ]
