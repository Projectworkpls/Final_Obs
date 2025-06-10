from supabase import create_client
from config import Config
import logging
from flask_login import UserMixin
from datetime import datetime, timedelta, time
import pytz
import uuid
import re
import base64

logger = logging.getLogger(__name__)

# Global supabase client
supabase = None


def init_supabase():
    global supabase
    try:
        # Use Config class instead of direct environment variables
        supabase_url = Config.SUPABASE_URL
        supabase_key = Config.SUPABASE_KEY

        if not supabase_url or not supabase_key:
            raise Exception("Supabase URL or KEY not found in configuration")

        supabase = create_client(supabase_url, supabase_key)

        # Test connection
        test = supabase.table('users').select("count", count="exact").execute()
        logger.info(f"Supabase connected successfully. Found {test.count} users.")
        return supabase
    except Exception as e:
        logger.error(f"Supabase initialization failed: {str(e)}")
        raise


def get_supabase_client():
    """Get the initialized supabase client"""
    global supabase
    if supabase is None:
        init_supabase()
    return supabase


class User(UserMixin):
    def __init__(self, id, email, name, role, child_id=None):
        self.id = id
        self.email = email
        self.name = name
        self.role = role
        self.child_id = child_id


def get_user_by_id(user_id):
    try:
        client = get_supabase_client()
        response = client.table('users').select("*").eq('id', user_id).execute()
        if response.data:
            user_data = response.data[0]
            return User(
                id=user_data['id'],
                email=user_data['email'],
                name=user_data.get('name', ''),
                role=user_data['role'],
                child_id=user_data.get('child_id')
            )
    except Exception as e:
        logger.error(f"Error getting user by ID: {str(e)}")
    return None


def authenticate_user(email, password):
    try:
        client = get_supabase_client()
        response = client.table('users').select("*").eq('email', email).eq('password', password).execute()
        if response.data:
            user_data = response.data[0]
            return User(
                id=user_data['id'],
                email=user_data['email'],
                name=user_data.get('name', ''),
                role=user_data['role'],
                child_id=user_data.get('child_id')
            )
    except Exception as e:
        logger.error(f"Authentication error: {str(e)}")
    return None


def create_user(user_data):
    try:
        client = get_supabase_client()
        response = client.table('users').insert(user_data).execute()
        return response.data[0] if response.data else None
    except Exception as e:
        logger.error(f"Error creating user: {str(e)}")
        return None


def get_children():
    try:
        client = get_supabase_client()
        response = client.table('children').select("*").execute()
        return response.data
    except Exception as e:
        logger.error(f"Error getting children: {str(e)}")
        return []


def get_observers():
    try:
        client = get_supabase_client()
        response = client.table('users').select("*").eq('role', 'Observer').execute()
        return response.data
    except Exception as e:
        logger.error(f"Error getting observers: {str(e)}")
        return []


def get_parents():
    try:
        client = get_supabase_client()
        response = client.table('users').select("*").eq('role', 'Parent').execute()
        return response.data
    except Exception as e:
        logger.error(f"Error getting parents: {str(e)}")
        return []


def get_observer_children(observer_id):
    try:
        client = get_supabase_client()
        mappings = client.table('observer_child_mappings').select("child_id").eq("observer_id", observer_id).execute()
        child_ids = [m['child_id'] for m in mappings.data]
        if child_ids:
            children = client.table('children').select("*").in_("id", child_ids).execute()
            return children.data
        return []
    except Exception as e:
        logger.error(f"Error getting observer children: {str(e)}")
        return []


def save_observation(observation_data):
    try:
        client = get_supabase_client()
        response = client.table('observations').insert(observation_data).execute()
        return response.data[0] if response.data else None
    except Exception as e:
        logger.error(f"Error saving observation: {str(e)}")
        return None


def save_processed_data(processed_data):
    try:
        client = get_supabase_client()
        response = client.table('processed_observations').insert(processed_data).execute()
        return response.data[0] if response.data else None
    except Exception as e:
        logger.error(f"Error saving processed data: {str(e)}")
        return None


def get_observations_by_child(child_id, limit=None):
    try:
        client = get_supabase_client()
        query = client.table('observations').select("*").eq('student_id', child_id).order('date', desc=True)
        if limit:
            query = query.limit(limit)
        response = query.execute()
        return response.data
    except Exception as e:
        logger.error(f"Error getting observations: {str(e)}")
        return []


def get_goals_by_child(child_id):
    try:
        client = get_supabase_client()
        response = client.table('goals').select("*").eq('child_id', child_id).execute()
        return response.data
    except Exception as e:
        logger.error(f"Error getting goals: {str(e)}")
        return []


def save_goal(goal_data):
    try:
        client = get_supabase_client()
        response = client.table('goals').insert(goal_data).execute()
        return response.data[0] if response.data else None
    except Exception as e:
        logger.error(f"Error saving goal: {str(e)}")
        return None


def get_messages_between_users(user1_id, user2_id):
    try:
        client = get_supabase_client()
        response = client.table('messages').select("*") \
            .or_(
            f"and(sender_id.eq.{user1_id},receiver_id.eq.{user2_id}),and(sender_id.eq.{user2_id},receiver_id.eq.{user1_id})") \
            .order('timestamp', desc=False) \
            .execute()
        return response.data
    except Exception as e:
        logger.error(f"Error getting messages: {str(e)}")
        return []


def save_message(message_data):
    try:
        client = get_supabase_client()
        response = client.table('messages').insert(message_data).execute()
        return response.data[0] if response.data else None
    except Exception as e:
        logger.error(f"Error saving message: {str(e)}")
        return None


def get_signed_audio_url(file_path, bucket_name="audio-files"):
    """Get signed URL for better audio compatibility"""
    try:
        client = get_supabase_client()

        # Create signed URL with longer expiry for audio streaming
        response = client.storage.from_(bucket_name).create_signed_url(
            file_path,
            expires_in=3600  # 1 hour
        )

        if response.get('error'):
            logger.error(f"Signed URL error: {response['error']}")
            return None

        return response['signedURL']

    except Exception as e:
        logger.error(f"Signed URL creation error: {e}")
        return None


def upload_file_to_storage(file_data, file_name, file_type):
    """Upload file to Supabase storage with enhanced audio compatibility"""
    try:
        client = get_supabase_client()

        # Clean filename to avoid issues with spaces and special characters
        clean_filename = re.sub(r'[^\w\s.-]', '', file_name)
        clean_filename = clean_filename.replace(' ', '_')
        unique_filename = f"{uuid.uuid4()}_{clean_filename}"

        # Determine bucket based on file type
        if "audio" in file_type.lower():
            bucket_name = "audio-files"
        elif "image" in file_type.lower():
            bucket_name = "image-files"
        else:
            bucket_name = "image-files"

        logger.info(f"Uploading to bucket: {bucket_name}, file: {unique_filename}")

        # For audio files, use special handling for better compatibility
        if "audio" in file_type.lower():
            response = client.storage.from_(bucket_name).upload(
                unique_filename,
                file_data,
                file_options={
                    "content-type": file_type,
                    "cache-control": "public, max-age=3600",
                    "content-disposition": f"inline; filename=\"{clean_filename}\""
                }
            )
        else:
            response = client.storage.from_(bucket_name).upload(
                unique_filename,
                file_data,
                file_options={"content-type": file_type}
            )

        # Check for upload errors
        if hasattr(response, 'error') and response.error:
            logger.error(f"Storage upload error: {response.error}")
            return None

        # Get public URL
        file_url = client.storage.from_(bucket_name).get_public_url(unique_filename)

        # Verify the URL was generated
        if not file_url:
            logger.error("Failed to generate public URL")
            return None

        logger.info(f"File uploaded successfully: {file_url}")
        return file_url

    except Exception as e:
        logger.error(f"Error uploading file: {str(e)}")
        return None


def diagnose_audio_file(file_path):
    """Diagnose audio file compatibility issues"""
    try:
        client = get_supabase_client()

        # Get file metadata
        file_info = client.storage.from_('audio-files').list(path=file_path)

        if file_info:
            file_data = file_info[0]
            logger.info(f"File size: {file_data.get('metadata', {}).get('size', 'unknown')}")
            logger.info(f"Content type: {file_data.get('metadata', {}).get('mimetype', 'unknown')}")
            logger.info(f"Last modified: {file_data.get('updated_at', 'unknown')}")

            # Test file accessibility
            public_url = client.storage.from_('audio-files').get_public_url(file_path)
            logger.info(f"Public URL: {public_url}")

            return True
        else:
            logger.error("File not found")
            return False

    except Exception as e:
        logger.error(f"Diagnosis error: {e}")
        return False


def test_storage_upload():
    """Test function to verify storage upload is working"""
    try:
        # Test audio upload
        test_audio_content = b"fake audio content for testing"
        audio_url = upload_file_to_storage(test_audio_content, "test_audio.mp3", "audio/mpeg")

        # Test image upload
        test_image_content = b"fake image content for testing"
        image_url = upload_file_to_storage(test_image_content, "test_image.jpg", "image/jpeg")

        logger.info(f"Storage test results - Audio: {audio_url}, Image: {image_url}")
        return audio_url and image_url

    except Exception as e:
        logger.error(f"Storage test failed: {e}")
        return False


# SCHEDULED REPORTING SYSTEM FUNCTIONS

def get_scheduled_reports_for_observer(observer_id):
    """Get all scheduled reports for an observer with child details"""
    try:
        client = get_supabase_client()

        # Get scheduled reports with child information
        response = client.table('scheduled_reports') \
            .select("""
                *,
                children:child_id (
                    id,
                    name,
                    grade,
                    birth_date
                )
            """) \
            .eq('observer_id', observer_id) \
            .eq('is_active', True) \
            .execute()

        return response.data
    except Exception as e:
        logger.error(f"Error getting scheduled reports: {e}")
        return []


def get_next_scheduled_time_for_child(child_id, observer_id):
    """Get the next scheduled time for a child's report"""
    try:
        client = get_supabase_client()

        # Get scheduled time
        schedule_response = client.table('scheduled_reports') \
            .select('scheduled_time') \
            .eq('child_id', child_id) \
            .eq('observer_id', observer_id) \
            .eq('is_active', True) \
            .execute()

        if not schedule_response.data:
            return None

        scheduled_time = schedule_response.data[0]['scheduled_time']

        # Calculate next occurrence
        now = datetime.now()
        today = now.date()

        # Parse scheduled time
        time_parts = scheduled_time.split(':')
        scheduled_hour = int(time_parts[0])
        scheduled_minute = int(time_parts[1])

        # Create today's scheduled datetime
        today_scheduled = datetime.combine(today, time(scheduled_hour, scheduled_minute))

        # If today's time has passed, schedule for tomorrow
        if now >= today_scheduled:
            next_scheduled = today_scheduled + timedelta(days=1)
        else:
            next_scheduled = today_scheduled

        return next_scheduled

    except Exception as e:
        logger.error(f"Error getting next scheduled time: {e}")
        return None


def check_if_report_processed_today(child_id, observer_id):
    """Check if a report was already processed today for this child"""
    try:
        client = get_supabase_client()

        # Get today's date range
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)

        response = client.table('report_processing_log') \
            .select('id') \
            .eq('child_id', child_id) \
            .eq('observer_id', observer_id) \
            .gte('processed_at', today_start.isoformat()) \
            .lt('processed_at', today_end.isoformat()) \
            .execute()

        return len(response.data) > 0

    except Exception as e:
        logger.error(f"Error checking if report processed today: {e}")
        return False


def save_scheduled_report(observer_id, child_id, scheduled_time):
    """Save or update a scheduled report time for a child"""
    try:
        client = get_supabase_client()

        # Check if schedule already exists
        existing = client.table('scheduled_reports') \
            .select('id') \
            .eq('observer_id', observer_id) \
            .eq('child_id', child_id) \
            .execute()

        if existing.data:
            # Update existing schedule
            response = client.table('scheduled_reports') \
                .update({
                'scheduled_time': scheduled_time,
                'updated_at': datetime.now().isoformat()
            }) \
                .eq('observer_id', observer_id) \
                .eq('child_id', child_id) \
                .execute()
        else:
            # Create new schedule
            response = client.table('scheduled_reports') \
                .insert({
                'observer_id': observer_id,
                'child_id': child_id,
                'scheduled_time': scheduled_time
            }) \
                .execute()

        return response.data

    except Exception as e:
        logger.error(f"Error saving scheduled report: {e}")
        return None


def log_report_processing(child_id, observer_id, observation_id=None, report_type='scheduled'):
    """Log when a report was processed"""
    try:
        client = get_supabase_client()

        log_data = {
            'child_id': child_id,
            'observer_id': observer_id,
            'report_type': report_type,
            'processed_at': datetime.now().isoformat()
        }

        if observation_id:
            log_data['observation_id'] = observation_id

        response = client.table('report_processing_log') \
            .insert(log_data) \
            .execute()

        return response.data

    except Exception as e:
        logger.error(f"Error logging report processing: {e}")
        return None


def get_child_schedule_status(observer_id):
    """Get schedule status for all children assigned to observer"""
    try:
        # Get all children for observer
        children = get_observer_children(observer_id)

        schedule_status = []
        for child in children:
            # Get scheduled time
            next_time = get_next_scheduled_time_for_child(child['id'], observer_id)

            # Check if processed today
            processed_today = check_if_report_processed_today(child['id'], observer_id)

            # Determine if report is due now
            now = datetime.now()
            is_due = False

            if next_time and not processed_today:
                # Report is due if scheduled time is within the next 30 minutes
                time_diff = next_time - now
                is_due = timedelta(minutes=-30) <= time_diff <= timedelta(minutes=30)

            schedule_status.append({
                'child': child,
                'next_scheduled_time': next_time,
                'processed_today': processed_today,
                'is_due': is_due,
                'can_process': is_due and not processed_today
            })

        return schedule_status

    except Exception as e:
        logger.error(f"Error getting child schedule status: {e}")
        return []


def get_report_processing_history(child_id, observer_id, days=30):
    """Get report processing history for a child"""
    try:
        client = get_supabase_client()

        # Get date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        response = client.table('report_processing_log') \
            .select('*') \
            .eq('child_id', child_id) \
            .eq('observer_id', observer_id) \
            .gte('processed_at', start_date.isoformat()) \
            .order('processed_at', desc=True) \
            .execute()

        return response.data

    except Exception as e:
        logger.error(f"Error getting report processing history: {e}")
        return []


def delete_scheduled_report(observer_id, child_id):
    """Delete a scheduled report"""
    try:
        client = get_supabase_client()

        response = client.table('scheduled_reports') \
            .delete() \
            .eq('observer_id', observer_id) \
            .eq('child_id', child_id) \
            .execute()

        return response.data

    except Exception as e:
        logger.error(f"Error deleting scheduled report: {e}")
        return None


def get_due_reports_for_observer(observer_id):
    """Get all reports that are currently due for an observer"""
    try:
        schedule_status = get_child_schedule_status(observer_id)
        due_reports = [status for status in schedule_status if status['can_process']]
        return due_reports

    except Exception as e:
        logger.error(f"Error getting due reports: {e}")
        return []


def update_scheduled_report_status(observer_id, child_id, is_active):
    """Enable or disable a scheduled report"""
    try:
        client = get_supabase_client()

        response = client.table('scheduled_reports') \
            .update({'is_active': is_active}) \
            .eq('observer_id', observer_id) \
            .eq('child_id', child_id) \
            .execute()

        return response.data

    except Exception as e:
        logger.error(f"Error updating scheduled report status: {e}")
        return None


# UTILITY FUNCTIONS FOR STORAGE MANAGEMENT

def list_storage_buckets():
    """List all available storage buckets"""
    try:
        client = get_supabase_client()
        buckets = client.storage.list_buckets()
        logger.info(f"Available buckets: {[bucket.name for bucket in buckets]}")
        return buckets
    except Exception as e:
        logger.error(f"Error listing buckets: {e}")
        return []


def verify_bucket_exists(bucket_name):
    """Verify if a specific bucket exists"""
    try:
        buckets = list_storage_buckets()
        bucket_names = [bucket.name for bucket in buckets]
        return bucket_name in bucket_names
    except Exception as e:
        logger.error(f"Error verifying bucket {bucket_name}: {e}")
        return False


def get_file_from_storage(bucket_name, file_path):
    """Download a file from storage"""
    try:
        client = get_supabase_client()
        response = client.storage.from_(bucket_name).download(file_path)
        return response
    except Exception as e:
        logger.error(f"Error downloading file {file_path} from {bucket_name}: {e}")
        return None


def delete_file_from_storage(bucket_name, file_path):
    """Delete a file from storage"""
    try:
        client = get_supabase_client()
        response = client.storage.from_(bucket_name).remove([file_path])
        return response
    except Exception as e:
        logger.error(f"Error deleting file {file_path} from {bucket_name}: {e}")
        return None
