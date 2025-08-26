# config.py
import os
from dotenv import load_dotenv
from datetime import timedelta

load_dotenv()


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key'

    # Enhanced session configuration
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
    SESSION_COOKIE_SECURE = False  # Set to True in production with HTTPS
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_REFRESH_EACH_REQUEST = True

    # Additional session security settings
    SESSION_COOKIE_NAME = 'learning_observer_session'
    SESSION_COOKIE_DOMAIN = None
    SESSION_COOKIE_PATH = '/'

    # API Keys and Database Configuration
    SUPABASE_URL = os.environ.get('SUPABASE_URL')
    SUPABASE_KEY = os.environ.get('SUPABASE_KEY')
    GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY')
    GROQ_API_KEY = os.environ.get('GROQ_API_KEY')
    OCR_API_KEY = os.environ.get('OCR_API_KEY')
    ASSEMBLYAI_API_KEY = os.environ.get('ASSEMBLYAI_API_KEY')
    
    # Email Configuration - with better error handling
    EMAIL_PASSWORD = os.environ.get('EMAIL_PASSWORD')
    EMAIL_USER = os.environ.get('EMAIL_USER')
    
    # Check if email configuration is available
    @classmethod
    def is_email_configured(cls):
        return bool(cls.EMAIL_USER and cls.EMAIL_PASSWORD)
    
    ADMIN_USER = os.environ.get('ADMIN_USER')
    ADMIN_PASS = os.environ.get('ADMIN_PASS')
    MAIL_SERVER = 'smtp.gmail.com'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = EMAIL_USER  # your email
    MAIL_PASSWORD = EMAIL_PASSWORD  # your app password
    MAIL_DEFAULT_SENDER = EMAIL_USER

    # CHANGED: File Upload Configuration - Updated from 16MB to 25MB
    UPLOAD_FOLDER = 'static/uploads'
    MAX_CONTENT_LENGTH = 25 * 1024 * 1024  # 25MB max file size (was 16MB)

    # Mobile optimization settings
    MOBILE_USER_AGENTS = [
        'android', 'iphone', 'mobile', 'blackberry',
        'windows phone', 'opera mini', 'iemobile'
    ]
