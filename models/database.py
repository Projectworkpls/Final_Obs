from supabase import create_client
from config import Config
import logging
from flask_login import UserMixin
from datetime import datetime, timedelta, time
import pytz
import uuid
import re
import base64
from werkzeug.security import generate_password_hash
import secrets
import time as time_module
import socket
import requests
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Global supabase client
supabase = None


def test_network_connectivity():
    """Test basic network connectivity"""
    try:
        # Test DNS resolution
        socket.gethostbyname('google.com')
        logger.info("DNS resolution working")

        # Test HTTP connectivity
        response = requests.get('https://httpbin.org/get', timeout=10)
        if response.status_code == 200:
            logger.info("HTTP connectivity working")
            return True
    except Exception as e:
        logger.error(f"Network connectivity test failed: {e}")
        return False
    return False


def test_supabase_connectivity(url):
    """Test connectivity to Supabase specifically"""
    try:
        parsed_url = urlparse(url)
        hostname = parsed_url.hostname

        # Test DNS resolution for Supabase hostname
        socket.gethostbyname(hostname)
        logger.info(f"Supabase DNS resolution successful for {hostname}")

        # Test HTTPS connectivity to Supabase
        response = requests.get(f"{url}/rest/v1/", timeout=15)
        logger.info(f"Supabase connectivity test: Status {response.status_code}")
        return True
    except socket.gaierror as e:
        logger.error(f"DNS resolution failed for Supabase: {e}")
        return False
    except requests.exceptions.RequestException as e:
        logger.error(f"HTTP request to Supabase failed: {e}")
        return False
    except Exception as e:
        logger.error(f"Supabase connectivity test failed: {e}")
        return False


def init_supabase():
    global supabase
    max_retries = 3
    retry_delay = 2  # seconds

    for attempt in range(max_retries):
        try:
            logger.info(f"Supabase initialization attempt {attempt + 1}/{max_retries}")

            # Get configuration
            supabase_url = Config.SUPABASE_URL
            supabase_key = Config.SUPABASE_KEY

            if not supabase_url or not supabase_key:
                raise Exception("Supabase URL or KEY not found in configuration")

            logger.info(f"Connecting to Supabase at: {supabase_url}")

            # Test network connectivity first
            if not test_network_connectivity():
                raise Exception("Basic network connectivity failed")

            # Test Supabase-specific connectivity
            if not test_supabase_connectivity(supabase_url):
                raise Exception("Supabase connectivity test failed")

            # Create Supabase client with timeout settings
            supabase = create_client(supabase_url, supabase_key)

            # Test connection with a simple query
            logger.info("Testing Supabase connection...")
            test = supabase.table('users').select("count", count="exact").execute()
            logger.info(f"Supabase connected successfully. Found {test.count} users.")
            return supabase

        except Exception as e:
            logger.error(f"Supabase initialization attempt {attempt + 1} failed: {str(e)}")

            if attempt < max_retries - 1:
                logger.info(f"Retrying in {retry_delay} seconds...")
                time_module.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
            else:
                logger.error("All Supabase initialization attempts failed")
                raise Exception(f"Failed to initialize Supabase after {max_retries} attempts: {str(e)}")


def get_supabase_client():
    """Get the initialized supabase client with retry logic"""
    global supabase
    if supabase is None:
        logger.info("Supabase client not initialized, attempting initialization...")
        init_supabase()
    return supabase


# Test function to verify connection
def test_supabase_connection():
    """Test Supabase connection and return status"""
    try:
        client = get_supabase_client()
        result = client.table('users').select("count", count="exact").execute()
        return True, f"Connection successful. Users count: {result.count}"
    except Exception as e:
        return False, f"Connection failed: {str(e)}"


class User(UserMixin):
    def __init__(self, id, email, name, role, child_id=None, organization_id=None):
        self.id = id
        self.email = email
        self.name = name
        self.role = role
        self.child_id = child_id
        self.organization_id = organization_id


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
                child_id=user_data.get('child_id'),
                organization_id=user_data.get('organization_id')
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
                child_id=user_data.get('child_id'),
                organization_id=user_data.get('organization_id')
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
        return response.data if response.data else []
    except Exception as e:
        logger.error(f"Error getting children: {str(e)}")
        return []


def get_observers():
    try:
        client = get_supabase_client()
        response = client.table('users').select("*").eq('role', 'Observer').execute()
        return response.data if response.data else []
    except Exception as e:
        logger.error(f"Error getting observers: {str(e)}")
        return []


def get_parents():
    try:
        client = get_supabase_client()
        response = client.table('users').select("*").eq('role', 'Parent').execute()
        return response.data if response.data else []
    except Exception as e:
        logger.error(f"Error getting parents: {str(e)}")
        return []


def get_observer_children(observer_id):
    try:
        client = get_supabase_client()
        mappings = client.table('observer_child_mappings').select("child_id").eq("observer_id", observer_id).execute()
        child_ids = [m['child_id'] for m in mappings.data] if mappings.data else []

        if child_ids:
            children = client.table('children').select("*").in_("id", child_ids).execute()
            return children.data if children.data else []
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
        return response.data if response.data else []
    except Exception as e:
        logger.error(f"Error getting observations: {str(e)}")
        return []


def get_goals_by_child(child_id):
    try:
        client = get_supabase_client()
        response = client.table('goals').select("*").eq('child_id', child_id).execute()
        return response.data if response.data else []
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
        return response.data if response.data else []
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

        return response.data if response.data else []
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

        return response.data if response.data else None
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

        return response.data if response.data else None
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


# MULTI-TENANT FUNCTIONS
def create_organization(name, description=None, contact_email=None, contact_phone=None, address=None):
    """Create a new organization"""
    try:
        client = get_supabase_client()
        org_data = {
            'id': str(uuid.uuid4()),
            'name': name,
            'description': description,
            'contact_email': contact_email,
            'contact_phone': contact_phone,
            'address': address,
            'is_active': True,
            'created_at': datetime.now().isoformat()
        }

        result = client.table('organizations').insert(org_data).execute()
        logger.info(f"Created organization: {name}")
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"Error creating organization: {e}")
        return None


def get_organizations():
    """Get all active organizations"""
    try:
        client = get_supabase_client()
        result = client.table('organizations').select('*').eq('is_active', True).order('name').execute()
        logger.info(f"Found {len(result.data)} organizations")
        return result.data if result.data else []
    except Exception as e:
        logger.error(f"Error fetching organizations: {e}")
        return []


def get_organization_by_id(org_id):
    """Get organization by ID"""
    try:
        client = get_supabase_client()
        result = client.table('organizations').select('*').eq('id', org_id).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"Error fetching organization: {e}")
        return None


def submit_observer_application(applicant_name, applicant_email, applicant_phone,
                                qualifications, experience_years, motivation_text,
                                organization_id, resume_url=None):
    """Submit observer application"""
    try:
        client = get_supabase_client()
        app_data = {
            'id': str(uuid.uuid4()),
            'applicant_name': applicant_name,
            'applicant_email': applicant_email,
            'applicant_phone': applicant_phone,
            'qualifications': qualifications,
            'experience_years': experience_years,
            'motivation_text': motivation_text,
            'organization_id': organization_id,
            'resume_url': resume_url,
            'application_status': 'pending',
            'created_at': datetime.now().isoformat()
        }

        result = client.table('observer_applications').insert(app_data).execute()
        logger.info(f"Observer application submitted for {applicant_name} to organization {organization_id}")
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"Error submitting application: {e}")
        return None


def get_pending_observer_applications(organization_id=None):
    """Get pending observer applications"""
    try:
        client = get_supabase_client()
        query = client.table('observer_applications').select('*, organizations(name)')

        if organization_id:
            query = query.eq('organization_id', organization_id)

        result = query.eq('application_status', 'pending').order('created_at', desc=True).execute()
        logger.info(f"Found {len(result.data)} pending applications for org {organization_id}")
        return result.data if result.data else []
    except Exception as e:
        logger.error(f"Error fetching applications: {e}")
        return []


def review_observer_application(application_id, reviewer_id, status, review_notes=None):
    """Review observer application (approve/reject)"""
    try:
        client = get_supabase_client()
        update_data = {
            'application_status': status,
            'reviewed_by': reviewer_id,
            'review_notes': review_notes,
            'reviewed_at': datetime.now().isoformat()
        }

        result = client.table('observer_applications').update(update_data).eq('id', application_id).execute()

        # If approved, create observer account
        if status == 'approved' and result.data:
            # Get full application data
            app_result = client.table('observer_applications').select('*').eq('id', application_id).execute()
            if app_result.data:
                app = app_result.data[0]
                create_observer_from_application(app)

        logger.info(f"Application {application_id} {status} by reviewer {reviewer_id}")
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"Error reviewing application: {e}")
        return None


def create_observer_from_application(application_data):
    """Create observer user from approved application"""
    try:
        client = get_supabase_client()
        # Generate temporary password
        temp_password = secrets.token_urlsafe(12)

        user_data = {
            'id': str(uuid.uuid4()),
            'email': application_data['applicant_email'],
            'name': application_data['applicant_name'],
            'password': temp_password,  # Use plain text for now, implement hashing later
            'role': 'Observer',
            'organization_id': application_data['organization_id'],
            'created_at': datetime.now().isoformat()
        }

        result = client.table('users').insert(user_data).execute()

        if result.data:
            logger.info(f"Created observer account for {application_data['applicant_name']}")
            # Send welcome email with temporary password
            send_observer_welcome_email(application_data['applicant_email'],
                                        application_data['applicant_name'],
                                        temp_password)

        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"Error creating observer account: {e}")
        return None


def send_observer_welcome_email(email, name, temp_password):
    """Send welcome email to new observer"""
    # Implement email sending logic here
    logger.info(f"Welcome email sent to {email} with password: {temp_password}")


# MISSING PEER REVIEW FUNCTIONS - ADDED
def get_observer_review_assignments(observer_id):
    """Get peer review assignments for observer"""
    try:
        client = get_supabase_client()
        result = client.table('observer_review_assignments').select('''
            *, 
            observations(*, users(name))
        ''').eq('observer_id', observer_id).eq('is_completed', False).execute()
        return result.data if result.data else []
    except Exception as e:
        logger.error(f"Error fetching review assignments: {e}")
        return []


def assign_peer_reviews():
    """Assign peer reviews based on completed observations"""
    try:
        client = get_supabase_client()
        # Get observers who need to do reviews
        observers = client.table('users').select('id, organization_id').eq('role', 'Observer').execute()

        for observer in observers.data:
            observer_id = observer['id']
            org_id = observer['organization_id']

            # Count completed observations by this observer
            completed_obs = client.table('observations').select('id').eq('username', observer_id).execute()
            completed_count = len(completed_obs.data)

            # Count pending review assignments
            pending_reviews = client.table('observer_review_assignments').select('id').eq('observer_id',
                                                                                          observer_id).eq(
                'is_completed', False).execute()
            pending_count = len(pending_reviews.data)

            # Calculate how many more reviews needed
            reviews_needed = completed_count - pending_count

            if reviews_needed > 0:
                # Get observations from other observers in the same org that need review
                available_obs = client.table('observations').select('id').neq('username', observer_id).eq(
                    'peer_review_status', 'pending').limit(reviews_needed).execute()

                # Assign reviews
                for obs in available_obs.data:
                    assignment_data = {
                        'observer_id': observer_id,
                        'observation_to_review_id': obs['id']
                    }
                    client.table('observer_review_assignments').insert(assignment_data).execute()

    except Exception as e:
        logger.error(f"Error assigning peer reviews: {e}")


def submit_peer_review(reviewer_id, observation_id, review_score, review_comments,
                       suggested_improvements, requires_changes):
    """Submit peer review"""
    try:
        client = get_supabase_client()
        review_data = {
            'reviewer_id': reviewer_id,
            'reviewed_observation_id': observation_id,
            'review_score': review_score,
            'review_comments': review_comments,
            'suggested_improvements': suggested_improvements,
            'requires_changes': requires_changes
        }

        result = client.table('observer_peer_reviews').insert(review_data).execute()

        # Mark assignment as completed
        client.table('observer_review_assignments').update({
            'is_completed': True,
            'completed_at': datetime.now().isoformat()
        }).eq('observer_id', reviewer_id).eq('observation_to_review_id', observation_id).execute()

        # Update observation peer review count
        obs_result = client.table('observations').select('peer_reviews_completed').eq('id', observation_id).execute()
        if obs_result.data:
            current_count = obs_result.data[0]['peer_reviews_completed']
            client.table('observations').update({
                'peer_reviews_completed': current_count + 1
            }).eq('id', observation_id).execute()

        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"Error submitting peer review: {e}")
        return None


def get_users_by_organization(organization_id, role=None):
    """Get users by organization and optionally by role - FIXED"""
    try:
        client = get_supabase_client()

        if not organization_id:
            logger.warning("No organization_id provided")
            return []

        query = client.table('users').select('*').eq('organization_id', organization_id)
        if role:
            query = query.eq('role', role)

        result = query.order('name').execute()
        logger.info(f"Found {len(result.data)} users with role {role} in org {organization_id}")
        return result.data if result.data else []
    except Exception as e:
        logger.error(f"Error fetching users by organization: {e}")
        return []


def create_principal_feedback(principal_id, observer_id, feedback_text, feedback_type):
    """Create feedback from principal to observer"""
    try:
        client = get_supabase_client()
        feedback_data = {
            'id': str(uuid.uuid4()),
            'principal_id': principal_id,
            'observer_id': observer_id,
            'feedback_text': feedback_text,
            'feedback_type': feedback_type,
            'created_at': datetime.now().isoformat()
        }

        result = client.table('principal_feedback').insert(feedback_data).execute()
        logger.info(f"Created feedback from principal {principal_id} to observer {observer_id}")
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"Error creating principal feedback: {e}")
        return None


def get_principal_feedback_for_observer(observer_id):
    """Get feedback for observer from principal"""
    try:
        client = get_supabase_client()
        result = client.table('principal_feedback').select('''
            *, users!principal_id(name)
        ''').eq('observer_id', observer_id).order('created_at', desc=True).execute()
        return result.data if result.data else []
    except Exception as e:
        logger.error(f"Error fetching principal feedback: {e}")
        return []


def get_peer_reviews_for_organization(organization_id):
    """Get all feedback for observers in an organization - FIXED"""
    try:
        client = get_supabase_client()

        if not organization_id:
            logger.warning("No organization_id provided")
            return []

        # Get observers for this organization
        observers = get_users_by_organization(organization_id, 'Observer')
        observer_ids = [obs['id'] for obs in observers]

        if not observer_ids:
            logger.info(f"No observers found in organization {organization_id}")
            return []

        # Get feedback for these observers
        reviews = client.table('principal_feedback').select('*').in_('observer_id', observer_ids).order('created_at',
                                                                                                        desc=True).execute()
        logger.info(f"Found {len(reviews.data)} reviews for organization {organization_id}")
        return reviews.data if reviews.data else []
    except Exception as e:
        logger.error(f"Error fetching peer reviews for organization: {e}")
        return []


def get_observations_by_organization(organization_id, limit=None):
    """Get observations for an organization - FIXED"""
    try:
        client = get_supabase_client()

        if not organization_id:
            logger.warning("No organization_id provided")
            return []

        # Get all users from this organization first
        org_users = get_users_by_organization(organization_id)
        user_ids = [user['id'] for user in org_users]

        if not user_ids:
            logger.info(f"No users found in organization {organization_id}")
            return []

        # Get observations by these users
        query = client.table('observations').select('*').in_('username', user_ids).order('created_at', desc=True)

        if limit:
            query = query.limit(limit)

        result = query.execute()
        logger.info(f"Found {len(result.data)} observations for organization {organization_id}")
        return result.data if result.data else []
    except Exception as e:
        logger.error(f"Error fetching observations by organization: {e}")
        return []


def get_children_by_organization(organization_id):
    """Get children for an organization - FIXED"""
    try:
        client = get_supabase_client()

        if not organization_id:
            logger.warning("No organization_id provided")
            return []

        result = client.table('children').select('*').eq('organization_id', organization_id).order('name').execute()
        logger.info(f"Found {len(result.data)} children in org {organization_id}")
        return result.data if result.data else []
    except Exception as e:
        logger.error(f"Error fetching children by organization: {e}")
        return []


def get_observer_child_mappings_by_organization(organization_id):
    """Get observer-child mappings for an organization - FIXED"""
    try:
        client = get_supabase_client()

        if not organization_id:
            logger.warning("No organization_id provided")
            return []

        # Get all observers in this organization
        observers = get_users_by_organization(organization_id, 'Observer')
        observer_ids = [obs['id'] for obs in observers]

        if not observer_ids:
            logger.info(f"No observers found in organization {organization_id}")
            return []

        # Get mappings for these observers
        mappings = client.table('observer_child_mappings').select('*').in_('observer_id', observer_ids).order(
            'created_at', desc=True).execute()
        logger.info(f"Found {len(mappings.data)} observer mappings in org {organization_id}")
        return mappings.data if mappings.data else []
    except Exception as e:
        logger.error(f"Error fetching observer mappings by organization: {e}")
        return []


def auto_assign_parent_to_organization(child_id, organization_id):
    """Auto-assign parent to organization when child is assigned - FIXED"""
    try:
        client = get_supabase_client()
        
        # Find parent associated with this child
        parent_result = client.table('users').select('*').eq('child_id', child_id).eq('role', 'Parent').execute()
        
        if parent_result.data:
            success_count = 0
            for parent in parent_result.data:
                try:
                    # Update parent's organization
                    update_result = client.table('users').update({
                        'organization_id': organization_id
                    }).eq('id', parent['id']).execute()
                    
                    if update_result.data:
                        logger.info(f"Auto-assigned parent {parent['id']} ({parent.get('name', 'Unknown')}) to organization {organization_id}")
                        success_count += 1
                    else:
                        logger.warning(f"Failed to auto-assign parent {parent['id']} - no data returned")
                except Exception as parent_update_error:
                    logger.error(f"Error updating parent {parent['id']}: {parent_update_error}")
            
            if success_count > 0:
                logger.info(f"Successfully auto-assigned {success_count} parent(s) to organization {organization_id}")
            else:
                logger.warning(f"No parents were successfully assigned to organization {organization_id}")
        else:
            logger.info(f"No parent found for child {child_id}")
        
        return True
    except Exception as e:
        logger.error(f"Error auto-assigning parent: {e}")
        return False


# UTILITY FUNCTIONS
def check_database_health():
    """Check database connection health"""
    try:
        client = get_supabase_client()
        # Simple query to test connection
        result = client.table('users').select("id").limit(1).execute()
        return {
            'status': 'healthy',
            'message': 'Database connection is working',
            'timestamp': datetime.now().isoformat()
        }
    except Exception as e:
        return {
            'status': 'unhealthy',
            'message': f'Database connection failed: {str(e)}',
            'timestamp': datetime.now().isoformat()
        }


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
