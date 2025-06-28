import os
import uuid
from datetime import datetime
import pandas as pd


def generate_unique_filename(original_filename):
    """Generate a unique filename to prevent collisions"""
    name, ext = os.path.splitext(original_filename)
    unique_id = str(uuid.uuid4())[:8]
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return f"{name}_{timestamp}_{unique_id}{ext}"


def validate_file_type(filename, allowed_types):
    """Validate if file type is allowed"""
    if '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower()
    return ext in allowed_types


def process_csv_upload(file, required_columns):
    """Process CSV file upload and validate columns"""
    try:
        df = pd.read_csv(file)

        # Check if all required columns exist
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            return None, f"Missing required columns: {', '.join(missing_columns)}"

        return df, None
    except Exception as e:
        return None, f"Error reading CSV file: {str(e)}"


def format_datetime(dt_string):
    """Format datetime string for display"""
    try:
        dt = datetime.fromisoformat(dt_string.replace('Z', '+00:00'))
        return dt.strftime('%Y-%m-%d %H:%M')
    except:
        return dt_string


def truncate_text(text, max_length=100):
    """Truncate text to specified length"""
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."
