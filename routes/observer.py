from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session, send_file
from flask_login import login_required, current_user
from models.database import (
    get_supabase_client, get_observer_children, save_observation,
    get_observations_by_child, save_goal, get_goals_by_child,
    get_messages_between_users, save_message, save_processed_data, upload_file_to_storage,
    get_scheduled_reports_for_observer, get_next_scheduled_time_for_child,
    check_if_report_processed_today, save_scheduled_report, log_report_processing,
    get_child_schedule_status, get_signed_audio_url,
    # Multi-tenant functions
    get_observer_review_assignments, submit_observer_application, get_organizations
)
from models.observation_extractor import ObservationExtractor
from models.monthly_report_generator import MonthlyReportGenerator
from utils.decorators import observer_required
import json
from datetime import datetime, timedelta
import uuid
import io
import re
import urllib.parse
import logging

logger = logging.getLogger(__name__)

observer_bp = Blueprint('observer', __name__)


@observer_bp.route('/dashboard')
@login_required
@observer_required
def dashboard():
    observer_id = session.get('user_id')
    # Get schedule status for all children
    schedule_status = get_child_schedule_status(observer_id)

    # Get peer review assignments
    try:
        peer_review_assignments = get_observer_review_assignments(observer_id)
    except:
        peer_review_assignments = []

    # Get recent feedback from principal
    try:
        principal_feedback = get_principal_feedback_for_observer(observer_id)[:5]
    except:
        principal_feedback = []

    return render_template('observer/dashboard.html',
                           schedule_status=schedule_status,
                           peer_review_assignments=peer_review_assignments,
                           principal_feedback=principal_feedback)


@observer_bp.route('/set_schedule', methods=['POST'])
@login_required
@observer_required
def set_schedule():
    """Set or update schedule for a child's reports"""
    try:
        observer_id = session.get('user_id')
        child_id = request.form.get('child_id')
        scheduled_time = request.form.get('scheduled_time')  # Format: "HH:MM"

        if not child_id or not scheduled_time:
            return jsonify({'success': False, 'error': 'Missing required fields'})

        # Validate time format
        try:
            time_parts = scheduled_time.split(':')
            if len(time_parts) != 2:
                raise ValueError("Invalid time format")
            hour, minute = int(time_parts[0]), int(time_parts[1])
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError("Invalid time values")
        except ValueError:
            return jsonify({'success': False, 'error': 'Invalid time format. Use HH:MM'})

        # Save schedule
        result = save_scheduled_report(observer_id, child_id, scheduled_time)
        if result:
            return jsonify({'success': True, 'message': 'Schedule updated successfully'})
        else:
            return jsonify({'success': False, 'error': 'Failed to update schedule'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@observer_bp.route('/process_scheduled_report/<child_id>')
@login_required
@observer_required
def process_scheduled_report(child_id):
    """Process a scheduled report for a child"""
    try:
        observer_id = session.get('user_id')
        # Check if report can be processed
        processed_today = check_if_report_processed_today(child_id, observer_id)
        if processed_today:
            flash('Report already processed today for this child', 'warning')
            return redirect(url_for('observer.dashboard'))

        # Get child details
        supabase = get_supabase_client()
        child_data = supabase.table('children').select("*").eq('id', child_id).execute().data
        if not child_data:
            flash('Child not found', 'error')
            return redirect(url_for('observer.dashboard'))

        child = child_data[0]

        # Redirect to process observation with pre-filled data
        session['scheduled_child_id'] = child_id
        session['scheduled_child_name'] = child['name']
        session.modified = True

        flash(f'Processing scheduled report for {child["name"]}', 'info')
        return redirect(url_for('observer.process_observation'))
    except Exception as e:
        flash(f'Error processing scheduled report: {str(e)}', 'error')
        return redirect(url_for('observer.dashboard'))


@observer_bp.route('/get_schedule_status')
@login_required
@observer_required
def get_schedule_status():
    """Get current schedule status for all children (AJAX endpoint)"""
    try:
        observer_id = session.get('user_id')
        schedule_status = get_child_schedule_status(observer_id)

        # Convert datetime objects to strings for JSON serialization
        for status in schedule_status:
            if status['next_scheduled_time']:
                status['next_scheduled_time'] = status['next_scheduled_time'].isoformat()

        return jsonify({'success': True, 'data': schedule_status})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@observer_bp.route('/process_observation')
@login_required
@observer_required
def process_observation():
    observer_id = session.get('user_id')
    children = get_observer_children(observer_id)

    # Get last processed report if available
    last_report = session.get('last_report')
    last_report_id = session.get('last_report_id')

    print(f"DEBUG: Process observation - last_report_id: {last_report_id}")
    print(f"DEBUG: Session keys: {list(session.keys())}")

    return render_template('observer/process_observation.html',
                           children=children,
                           last_report=last_report,
                           last_report_id=last_report_id)


@observer_bp.route('/process_file', methods=['POST'])
@login_required
@observer_required
def process_file():
    print("Processing file with mode:", request.form.get('processing_mode'))

    observer_id = session.get('user_id')
    child_id = request.form.get('child_id')
    processing_mode = request.form.get('processing_mode')
    session_date = request.form.get('session_date')
    session_start = request.form.get('session_start')
    session_end = request.form.get('session_end')
    student_name = request.form.get('student_name')

    user_info = {
        'student_name': student_name,
        'observer_name': session.get('name'),
        'session_date': session_date,
        'session_start': session_start,
        'session_end': session_end
    }

    extractor = ObservationExtractor()

    try:
        if processing_mode == 'ocr':
            if 'file' not in request.files:
                return jsonify({
                    'success': False,
                    'error': 'No file uploaded'
                })

            file = request.files['file']

            # Extract text and process
            extracted_text = extractor.extract_text_with_ocr(file)
            structured_data = extractor.process_with_groq(extracted_text)
            observations_text = structured_data.get("observations", "")

            # Upload file to storage (handle error gracefully)
            file.seek(0)
            try:
                file_url = upload_file_to_storage(
                    file.read(),
                    file.filename,
                    f"image/{file.content_type.split('/')[1]}"
                )
            except Exception as upload_error:
                print(f"Error uploading file: {upload_error}")
                file_url = None

            # Generate formatted report
            report = extractor.generate_report_from_text(observations_text, user_info)

            # Save observation
            observation_id = str(uuid.uuid4())
            observation_data = {
                "id": observation_id,
                "student_id": child_id,
                "username": observer_id,
                "student_name": structured_data.get("studentName", student_name),
                "observer_name": session.get('name'),
                "class_name": structured_data.get("className", ""),
                "date": structured_data.get("date", session_date),
                "observations": observations_text,
                "strengths": json.dumps(structured_data.get("strengths", [])),
                "areas_of_development": json.dumps(structured_data.get("areasOfDevelopment", [])),
                "recommendations": json.dumps(structured_data.get("recommendations", [])),
                "timestamp": datetime.now().isoformat(),
                "filename": file.filename,
                "full_data": json.dumps({
                    **structured_data,
                    "formatted_report": report
                }),
                "theme_of_day": structured_data.get("themeOfDay", ""),
                "curiosity_seed": structured_data.get("curiositySeed", ""),
                "file_url": file_url,
                # Initialize peer review fields
                "peer_reviews_required": 1,
                "peer_reviews_completed": 0,
                "peer_review_status": "pending"
            }

            # Save to database
            supabase = get_supabase_client()
            supabase.table('observations').insert(observation_data).execute()

            # Check if this was a scheduled report and log it
            scheduled_child_id = session.get('scheduled_child_id')
            report_type = 'scheduled' if scheduled_child_id == child_id else 'manual'

            # Log the processing
            log_report_processing(child_id, observer_id, observation_id, report_type)

            # CRITICAL FIX: Clear large session data and store only essentials
            # Remove large custom report to free space
            if 'last_custom_report' in session:
                del session['last_custom_report']

            # Clear scheduled session data
            if 'scheduled_child_id' in session:
                del session['scheduled_child_id']
            if 'scheduled_child_name' in session:
                del session['scheduled_child_name']

            # Store minimal session data
            session['last_report'] = report[:1500]  # Truncate to save space
            session['last_report_id'] = observation_id
            session['last_student_name'] = structured_data.get("studentName", student_name)
            session['last_date'] = structured_data.get("date", session_date)
            session.permanent = True
            session.modified = True  # CRITICAL: Force session save

            print(f"Updated session data - report_id: {observation_id}")

            return jsonify({
                'success': True,
                'message': 'OCR observation processed and saved successfully!',
                'report': report,
                'download_urls': {
                    'word': url_for('observer.download_report'),
                    'pdf': url_for('observer.download_pdf')
                }
            })

        elif processing_mode == 'audio':
            if 'file' not in request.files:
                return jsonify({
                    'success': False,
                    'error': 'No file uploaded'
                })

            file = request.files['file']

            # Validate audio file
            if not file.filename.lower().endswith(('.mp3', '.wav', '.m4a', '.ogg', '.flac')):
                return jsonify({
                    'success': False,
                    'error': 'Invalid audio format. Please upload MP3, WAV, M4A, OGG, or FLAC files.'
                })

            # Check file size (limit to 25MB for audio)
            file.seek(0, 2)  # Seek to end
            file_size = file.tell()
            file.seek(0)  # Reset to beginning

            if file_size > 25 * 1024 * 1024:  # 25MB limit
                return jsonify({
                    'success': False,
                    'error': 'Audio file too large. Please upload files smaller than 25MB.'
                })

            # Upload file to storage first
            file.seek(0)
            try:
                file_url = upload_file_to_storage(
                    file.read(),
                    file.filename,
                    f"audio/{file.content_type.split('/')[1] if '/' in file.content_type else 'mp3'}"
                )
            except Exception as upload_error:
                print(f"Error uploading file: {upload_error}")
                return jsonify({
                    'success': False,
                    'error': f'Failed to upload audio file: {str(upload_error)}'
                })

            # Reset file pointer for transcription
            file.seek(0)

            # Transcribe audio with better error handling
            try:
                transcript = extractor.transcribe_with_assemblyai(file)

                # Check if transcription was successful
                if not transcript or transcript.strip() == "" or "error" in transcript.lower():
                    return jsonify({
                        'success': False,
                        'error': 'Audio transcription failed. Please ensure the audio is clear and contains speech.'
                    })

                # Check for common transcription errors
                if len(transcript.strip()) < 10:
                    return jsonify({
                        'success': False,
                        'error': 'Audio transcription too short. Please ensure the audio contains sufficient speech content.'
                    })
            except Exception as transcription_error:
                print(f"Transcription error: {transcription_error}")
                return jsonify({
                    'success': False,
                    'error': f'Audio transcription failed: {str(transcription_error)}'
                })

            # Generate formatted report from transcript with validation
            try:
                if transcript and len(transcript.strip()) > 10:
                    report = extractor.generate_report_from_text(transcript, user_info)
                else:
                    return jsonify({
                        'success': False,
                        'error': 'Insufficient audio content for report generation.'
                    })
            except Exception as report_error:
                print(f"Report generation error: {report_error}")
                return jsonify({
                    'success': False,
                    'error': f'Failed to generate report: {str(report_error)}'
                })

            # Save observation only if everything succeeded
            observation_id = str(uuid.uuid4())
            observation_data = {
                "id": observation_id,
                "student_id": child_id,
                "username": observer_id,
                "student_name": student_name,
                "observer_name": session.get('name'),
                "class_name": "",
                "date": session_date,
                "observations": transcript,
                "strengths": json.dumps([]),
                "areas_of_development": json.dumps([]),
                "recommendations": json.dumps([]),
                "timestamp": datetime.now().isoformat(),
                "filename": file.filename,
                "full_data": json.dumps({
                    "transcript": transcript,
                    "report": report,
                    "formatted_report": report,
                    "file_size": file_size,
                    "transcription_length": len(transcript)
                }),
                "theme_of_day": "",
                "curiosity_seed": "",
                "file_url": file_url,
                # Initialize peer review fields
                "peer_reviews_required": 1,
                "peer_reviews_completed": 0,
                "peer_review_status": "pending"
            }

            # Save to database
            supabase = get_supabase_client()
            supabase.table('observations').insert(observation_data).execute()

            # Log processing and update session
            scheduled_child_id = session.get('scheduled_child_id')
            report_type = 'scheduled' if scheduled_child_id == child_id else 'manual'
            log_report_processing(child_id, observer_id, observation_id, report_type)

            # Clear session data
            if 'last_custom_report' in session:
                del session['last_custom_report']
            if 'scheduled_child_id' in session:
                del session['scheduled_child_id']
            if 'scheduled_child_name' in session:
                del session['scheduled_child_name']

            # Store minimal session data
            session['last_report'] = report[:1500]
            session['last_report_id'] = observation_id
            session['last_student_name'] = student_name
            session['last_date'] = session_date
            session.permanent = True
            session.modified = True

            return jsonify({
                'success': True,
                'message': 'Audio observation processed and saved successfully!',
                'report': report,
                'transcript_length': len(transcript),
                'download_urls': {
                    'word': url_for('observer.download_report'),
                    'pdf': url_for('observer.download_pdf')
                }
            })

    except Exception as e:
        print(f"Error in process_file: {e}")
        return jsonify({
            'success': False,
            'error': f'Error processing observation: {str(e)}'
        })


# Cross-Organization Peer Review Routes - FIXED

@observer_bp.route('/peer_reviews')
@login_required
@observer_required
def peer_reviews():
    """View peer review assignments - Limited to observer's own report count, 24hrs old, and unreviewd"""
    try:
        observer_id = session.get('user_id')

        supabase = get_supabase_client()

        # First, get count of observations this observer has made
        observer_reports_count = supabase.table('observations').select("id", count="exact").eq('username',
                                                                                               observer_id).execute()
        max_reviews_allowed = observer_reports_count.count if observer_reports_count.count else 0

        # Calculate 24 hours ago
        twenty_four_hours_ago = (datetime.now() - timedelta(hours=24)).isoformat()

        # Get ALL observations from OTHER observers (any organization) for review
        # Only from last 24 hours and exclude own reports
        observations_response = supabase.table('observations').select("""
            id, student_name, observer_name, date, timestamp, filename,
            file_url, full_data, username, observations, processed_by_admin
        """).neq('username', observer_id).gte('timestamp', twenty_four_hours_ago).order('timestamp',
                                                                                        desc=True).execute()

        all_observations = observations_response.data if observations_response.data else []

        # Get all observation IDs that have already been reviewed by ANY observer
        reviewed_observations = supabase.table('peer_reviews').select('observation_id').execute()
        reviewed_observation_ids = [review['observation_id'] for review in
                                    reviewed_observations.data] if reviewed_observations.data else []

        # Filter out observations that have already been reviewed by anyone
        unreviewed_observations = [obs for obs in all_observations if obs['id'] not in reviewed_observation_ids]

        # Process observations similar to admin dashboard
        processed_observations = []
        for obs in unreviewed_observations:
            processed_obs = {
                'id': obs.get('id'),
                'student_name': obs.get('student_name', 'N/A'),
                'observer_name': obs.get('observer_name', 'N/A'),
                'date': obs.get('date', 'N/A'),
                'timestamp': obs.get('timestamp', 'N/A'),
                'filename': obs.get('filename', 'N/A'),
                'file_url': obs.get('file_url'),
                'processed_by_admin': obs.get('processed_by_admin', False),
                'has_formatted_report': False,
                'formatted_report': None,
                'file_type': None,
                'signed_url': None
            }

            # Process file URL for audio/media
            if processed_obs['file_url']:
                processed_obs['file_url'] = urllib.parse.quote(processed_obs['file_url'], safe=':/?#[]@!$&\'()*+,;=')

                # Determine file type from URL or filename
                file_url_lower = processed_obs['file_url'].lower()
                if any(ext in file_url_lower for ext in ['.mp3', '.wav', '.m4a', '.ogg']):
                    processed_obs['file_type'] = 'audio'
                    # Create signed URL for audio files for better compatibility
                    filename = processed_obs['file_url'].split('/')[-1]
                    signed_url = get_signed_audio_url(filename)
                    if signed_url:
                        processed_obs['signed_url'] = signed_url
                elif any(ext in file_url_lower for ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp']):
                    processed_obs['file_type'] = 'image'

            # Extract formatted report from full_data
            if obs.get('full_data'):
                try:
                    full_data = json.loads(obs['full_data'])
                    if full_data.get('formatted_report'):
                        processed_obs['has_formatted_report'] = True
                        processed_obs['formatted_report'] = full_data['formatted_report']
                except:
                    pass

            processed_observations.append(processed_obs)

        # Limit to the number of reports this observer has made
        pending_reviews = processed_observations[:max_reviews_allowed]

        # Get completed reviews by this observer
        completed_reviews = []
        try:
            completed_reviews_response = supabase.table('peer_reviews').select("""
                *, observations(student_name, observer_name, date)
            """).eq('reviewer_id', observer_id).order('created_at', desc=True).execute()
            completed_reviews = completed_reviews_response.data if completed_reviews_response.data else []
        except Exception as e:
            logger.warning(f"Could not fetch completed reviews: {e}")
            completed_reviews = []

        logger.info(
            f"Observer {observer_id} has made {max_reviews_allowed} reports, can review {len(pending_reviews)} observations, completed {len(completed_reviews)} reviews")

        return render_template('observer/peer_reviews.html',
                               pending_reviews=pending_reviews,
                               completed_reviews=completed_reviews,
                               observer_name=session.get('name'),
                               max_reviews_allowed=max_reviews_allowed,
                               observer_reports_count=max_reviews_allowed)
    except Exception as e:
        logger.error(f'Error loading peer reviews: {str(e)}')
        flash(f'Error loading peer reviews: {str(e)}', 'error')
        return render_template('observer/peer_reviews.html',
                               pending_reviews=[],
                               completed_reviews=[],
                               observer_name=session.get('name'),
                               max_reviews_allowed=0,
                               observer_reports_count=0)


@observer_bp.route('/review_observation/<observation_id>')
@login_required
@observer_required
def review_observation(observation_id):
    """Review a specific observation - ANY organization - FIXED"""
    try:
        observer_id = session.get('user_id')
        supabase = get_supabase_client()

        # Get the observation to review - FIXED QUERY (no join with users)
        observation_response = supabase.table('observations').select("""
            id, student_name, observer_name, date, timestamp, filename,
            file_url, full_data, username, observations
        """).eq('id', observation_id).execute()

        if not observation_response.data:
            flash('Observation not found', 'error')
            return redirect(url_for('observer.peer_reviews'))

        observation = observation_response.data[0]

        # Verify it's not own observation
        if observation['username'] == observer_id:
            flash('You cannot review your own observation', 'error')
            return redirect(url_for('observer.peer_reviews'))

        # Check if already reviewed
        try:
            existing_review = supabase.table('peer_reviews').select('id').eq('observation_id', observation_id).eq(
                'reviewer_id', observer_id).execute()
            if existing_review.data:
                flash('You have already reviewed this observation', 'warning')
                return redirect(url_for('observer.peer_reviews'))
        except Exception as e:
            logger.warning(f"Could not check existing review: {e}")

        # Process file URL for audio/media
        if observation.get('file_url'):
            observation['file_url'] = urllib.parse.quote(observation['file_url'], safe=':/?#[]@!$&\'()*+,;=')

            # Create signed URL for audio files
            if any(ext in observation['file_url'].lower() for ext in ['.mp3', '.wav', '.m4a', '.ogg']):
                filename = observation['file_url'].split('/')[-1]
                signed_url = get_signed_audio_url(filename)
                if signed_url:
                    observation['signed_url'] = signed_url

        # Extract formatted report from full_data
        formatted_report = None
        if observation.get('full_data'):
            try:
                full_data = json.loads(observation['full_data'])
                formatted_report = full_data.get('formatted_report')
            except:
                pass

        return render_template('observer/review_observation.html',
                               observation=observation,
                               formatted_report=formatted_report)
    except Exception as e:
        logger.error(f'Error loading observation for review: {str(e)}')
        flash(f'Error loading observation: {str(e)}', 'error')
        return redirect(url_for('observer.peer_reviews'))


# FIXED: Use service role client to bypass RLS completely
def insert_peer_review_with_service_role(review_data):
    """Insert peer review using service role client to bypass RLS completely"""
    try:
        from supabase import create_client
        from config import Config

        # Use service role key to bypass RLS completely
        service_key = getattr(Config, 'SUPABASE_SERVICE_KEY', None)

        if service_key:
            service_client = create_client(Config.SUPABASE_URL, service_key)
            # Use returning='minimal' to prevent automatic SELECT after INSERT
            result = service_client.table('peer_reviews').insert(review_data, returning='minimal').execute()
            # Check status code instead of data (since data will be empty with minimal)
            return result.status_code == 201
        else:
            # Fallback: try with regular client and returning='minimal'
            supabase = get_supabase_client()
            result = supabase.table('peer_reviews').insert(review_data, returning='minimal').execute()
            return result.status_code == 201

    except Exception as e:
        logger.error(f"Service role insert failed: {e}")
        return False


@observer_bp.route('/submit_peer_review/<observation_id>', methods=['POST'])
@login_required
@observer_required
def submit_peer_review_route(observation_id):
    """Submit peer review feedback - COMPLETELY FIXED with RLS bypass"""
    try:
        reviewer_id = session.get('user_id')

        # Get form data
        review_score = request.form.get('review_score')
        review_comments = request.form.get('review_comments')
        suggested_improvements = request.form.get('suggested_improvements')
        requires_changes = request.form.get('requires_changes') == 'on'

        if not all([review_score, review_comments]):
            flash('Review score and comments are required', 'error')
            return redirect(url_for('observer.review_observation', observation_id=observation_id))

        supabase = get_supabase_client()

        # Get observation details - SIMPLIFIED QUERY
        observation = supabase.table('observations').select("""
            id, username, student_name, observer_name
        """).eq('id', observation_id).execute()

        if not observation.data:
            flash('Observation not found', 'error')
            return redirect(url_for('observer.peer_reviews'))

        obs_data = observation.data[0]
        observed_by = obs_data['username']

        # Get the observed user's organization - SEPARATE QUERY
        observed_user = supabase.table('users').select('organization_id, name').eq('id', observed_by).execute()
        observed_user_org_id = observed_user.data[0]['organization_id'] if observed_user.data else None

        # Create peer review record - ENSURE ALL REQUIRED FIELDS
        review_data = {
            'id': str(uuid.uuid4()),  # Add explicit ID
            'observation_id': observation_id,
            'reviewer_id': reviewer_id,
            'observed_by': observed_by,
            'review_score': int(review_score),
            'review_comments': review_comments,
            'suggested_improvements': suggested_improvements or '',
            'requires_changes': requires_changes,
            'created_at': datetime.now().isoformat()
        }

        # FIXED: Use service role client to completely bypass RLS
        success = insert_peer_review_with_service_role(review_data)

        if success:
            # Send notification to the CORRECT principal
            if observed_user_org_id:
                send_peer_review_notification_to_principal(observation_id, reviewer_id, observed_by,
                                                           observed_user_org_id, review_data)

            flash('Peer review submitted successfully! This observation has been removed from all review lists.',
                  'success')
        else:
            flash('Error submitting peer review. Please try again.', 'error')

    except Exception as e:
        logger.error(f'Error submitting peer review: {str(e)}')
        flash('Error submitting peer review. Please try again.', 'error')

    return redirect(url_for('observer.peer_reviews'))


def send_peer_review_notification_to_principal(observation_id, reviewer_id, observed_by, observed_user_org_id,
                                               review_data):
    """Send notification to the CORRECT principal based on observed user's organization"""
    try:
        supabase = get_supabase_client()

        # Get principal for the OBSERVED USER's organization
        principal = supabase.table('users').select('id, name').eq('organization_id', observed_user_org_id).eq('role',
                                                                                                              'Principal').execute()

        # Get reviewer details
        reviewer = supabase.table('users').select('name, organization_id').eq('id', reviewer_id).execute()
        reviewer_name = reviewer.data[0]['name'] if reviewer.data else 'Unknown Reviewer'

        # Get observed user details
        observed_user = supabase.table('users').select('name').eq('id', observed_by).execute()
        observed_user_name = observed_user.data[0]['name'] if observed_user.data else 'Unknown Observer'

        if principal.data:
            principal_id = principal.data[0]['id']
            principal_name = principal.data[0]['name']

            # Create notification record
            notification_data = {
                'id': str(uuid.uuid4()),
                'recipient_id': principal_id,
                'sender_id': reviewer_id,
                'type': 'peer_review',
                'title': 'Peer Review Received',
                'message': f'A peer review has been submitted by {reviewer_name} for {observed_user_name}\'s observation. Review Score: {review_data["review_score"]}/5',
                'data': json.dumps({
                    'observation_id': observation_id,
                    'reviewer_id': reviewer_id,
                    'reviewer_name': reviewer_name,
                    'observed_by': observed_by,
                    'observed_user_name': observed_user_name,
                    'review_score': review_data['review_score'],
                    'requires_changes': review_data['requires_changes'],
                    'review_comments': review_data['review_comments']
                }),
                'read': False,
                'created_at': datetime.now().isoformat()
            }

            # Use returning='minimal' for notifications too
            try:
                supabase.table('notifications').insert(notification_data, returning='minimal').execute()
                logger.info(
                    f"Sent peer review notification to principal {principal_name} ({principal_id}) for observation by {observed_user_name}")
            except Exception as notif_error:
                logger.warning(f"Failed to send notification: {notif_error}")

        else:
            logger.warning(f"No principal found for organization {observed_user_org_id}")

    except Exception as e:
        logger.error(f'Error sending notification to principal: {e}')


def get_principal_feedback_for_observer(observer_id):
    """Get feedback for observer from principal"""
    try:
        supabase = get_supabase_client()
        result = supabase.table('principal_feedback').select('''
            *, users!principal_id(name)
        ''').eq('observer_id', observer_id).order('created_at', desc=True).execute()
        return result.data if result.data else []
    except Exception as e:
        logger.error(f"Error fetching principal feedback: {e}")
        return []


# ALL EXISTING ROUTES BELOW REMAIN UNCHANGED

@observer_bp.route('/download_report')
@login_required
@observer_required
def download_report():
    print(f"Session data in download_report: {dict(session)}")

    try:
        report_id = session.get('last_report_id')
        print(f"DEBUG: Download report - session report_id: {report_id}")

        if not report_id:
            print("No report_id in session")
            flash('No report available for download', 'error')
            return redirect(url_for('observer.process_observation'))

        # Get the report from database
        supabase = get_supabase_client()
        report_data = supabase.table('observations').select("*").eq('id', report_id).execute().data

        print(f"DEBUG: Database query result: {len(report_data)} records found")

        if not report_data:
            flash('Report not found', 'error')
            return redirect(url_for('observer.process_observation'))

        report = report_data[0]

        # Get formatted report from full_data
        formatted_report = None
        if report.get('full_data'):
            try:
                full_data = json.loads(report['full_data'])
                formatted_report = full_data.get('formatted_report')
                print(f"DEBUG: Formatted report found: {bool(formatted_report)}")
            except Exception as e:
                print(f"DEBUG: Error parsing full_data: {e}")

        if not formatted_report:
            flash('No formatted report available', 'error')
            return redirect(url_for('observer.process_observation'))

        # Create Word document with emoji support
        extractor = ObservationExtractor()
        doc_buffer = extractor.create_word_document_with_emojis(formatted_report)

        # Create proper filename with student name
        student_name = report['student_name']
        if student_name:
            clean_name = re.sub(r'[^\w\s-]', '', student_name).strip()
            clean_name = re.sub(r'[-\s]+', '_', clean_name)
        else:
            clean_name = 'Student'

        date = report['date'] if report['date'] else datetime.now().strftime('%Y-%m-%d')
        filename = f"observation_report_{clean_name}_{date}.docx"

        return send_file(
            doc_buffer,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )

    except Exception as e:
        print(f"DEBUG: Download error: {e}")
        flash(f'Error downloading report: {str(e)}', 'error')
        return redirect(url_for('observer.process_observation'))


@observer_bp.route('/download_pdf')
@login_required
@observer_required
def download_pdf():
    print(f"Session data in download_pdf: {dict(session)}")

    try:
        report_id = session.get('last_report_id')
        print(f"DEBUG: Download PDF - session report_id: {report_id}")

        if not report_id:
            print("No report_id in session")
            flash('No report available for download', 'error')
            return redirect(url_for('observer.process_observation'))

        # Get the report from database
        supabase = get_supabase_client()
        report_data = supabase.table('observations').select("*").eq('id', report_id).execute().data

        if not report_data:
            flash('Report not found', 'error')
            return redirect(url_for('observer.process_observation'))

        report = report_data[0]

        # Get formatted report
        formatted_report = None
        if report.get('full_data'):
            try:
                full_data = json.loads(report['full_data'])
                formatted_report = full_data.get('formatted_report')
            except:
                pass

        if not formatted_report:
            flash('No formatted report available', 'error')
            return redirect(url_for('observer.process_observation'))

        # Use alternative PDF creation method without WeasyPrint
        extractor = ObservationExtractor()
        pdf_buffer = extractor.create_pdf_alternative(formatted_report)

        # Create proper filename with student name
        student_name = report['student_name']
        if student_name:
            clean_name = re.sub(r'[^\w\s-]', '', student_name).strip()
            clean_name = re.sub(r'[-\s]+', '_', clean_name)
        else:
            clean_name = 'Student'

        date = report['date'] if report['date'] else datetime.now().strftime('%Y-%m-%d')
        filename = f"observation_report_{clean_name}_{date}.pdf"

        return send_file(
            pdf_buffer,
            as_attachment=True,
            download_name=filename,
            mimetype='application/pdf'
        )

    except Exception as e:
        print(f"DEBUG: Download PDF error: {e}")
        flash(f'Error downloading PDF: {str(e)}', 'error')
        return redirect(url_for('observer.process_observation'))


@observer_bp.route('/email_report', methods=['POST'])
@login_required
@observer_required
def email_report():
    try:
        report_id = session.get('last_report_id')
        recipient_email = request.form.get('recipient_email')

        print(f"DEBUG: Email report - session report_id: {report_id}")

        if not report_id or not recipient_email:
            return jsonify({'success': False, 'error': 'Missing report or email'})

        # Get the report from database
        supabase = get_supabase_client()
        report_data = supabase.table('observations').select("*").eq('id', report_id).execute().data

        if not report_data:
            return jsonify({'success': False, 'error': 'Report not found'})

        report = report_data[0]

        # Get formatted report
        formatted_report = None
        if report.get('full_data'):
            try:
                full_data = json.loads(report['full_data'])
                formatted_report = full_data.get('formatted_report')
            except:
                pass

        if not formatted_report:
            return jsonify({'success': False, 'error': 'No formatted report available'})

        # Send email
        extractor = ObservationExtractor()
        subject = f"Observation Report for {report['student_name']} - {report['date']}"
        success, message = extractor.send_email(recipient_email, subject, formatted_report)

        return jsonify({'success': success, 'message': message})

    except Exception as e:
        print(f"DEBUG: Email error: {e}")
        return jsonify({'success': False, 'error': str(e)})


@observer_bp.route('/custom_report', methods=['POST'])
@login_required
@observer_required
def custom_report():
    child_id = request.form.get('child_id')
    prompt = request.form.get('prompt')

    extractor = ObservationExtractor()
    try:
        report = extractor.generate_custom_report_from_prompt(prompt, child_id)

        # Store full report in session for downloads
        session['last_custom_report'] = report  # Store full report
        session.permanent = True
        session.modified = True

        return jsonify({'success': True, 'report': report})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@observer_bp.route('/download_custom_report')
@login_required
@observer_required
def download_custom_report():
    try:
        custom_report = session.get('last_custom_report')
        if not custom_report:
            flash('No custom report available for download', 'error')
            return redirect(url_for('observer.process_observation'))

        # Create Word document
        extractor = ObservationExtractor()
        doc_buffer = extractor.create_word_document_with_emojis(custom_report)

        # Create filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"custom_report_{timestamp}.docx"

        return send_file(
            doc_buffer,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )

    except Exception as e:
        flash(f'Error downloading custom report: {str(e)}', 'error')
        return redirect(url_for('observer.process_observation'))


@observer_bp.route('/download_custom_pdf')
@login_required
@observer_required
def download_custom_pdf():
    try:
        custom_report = session.get('last_custom_report')
        if not custom_report:
            flash('No custom report available for download', 'error')
            return redirect(url_for('observer.process_observation'))

        # Create PDF using alternative method
        extractor = ObservationExtractor()
        pdf_buffer = extractor.create_pdf_alternative(custom_report)

        # Create filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"custom_report_{timestamp}.pdf"

        return send_file(
            pdf_buffer,
            as_attachment=True,
            download_name=filename,
            mimetype='application/pdf'
        )

    except Exception as e:
        flash(f'Error downloading custom PDF: {str(e)}', 'error')
        return redirect(url_for('observer.process_observation'))


@observer_bp.route('/email_custom_report', methods=['POST'])
@login_required
@observer_required
def email_custom_report():
    try:
        custom_report = session.get('last_custom_report')
        recipient_email = request.form.get('recipient_email')

        print(f"DEBUG: Email custom report - custom_report exists: {bool(custom_report)}")

        if not custom_report or not recipient_email:
            return jsonify({'success': False, 'error': 'Missing report or email'})

        # Send email
        extractor = ObservationExtractor()
        subject = f"Custom Observation Report - {datetime.now().strftime('%Y-%m-%d')}"
        success, message = extractor.send_email(recipient_email, subject, custom_report)

        return jsonify({'success': success, 'message': message})

    except Exception as e:
        print(f"DEBUG: Email custom report error: {e}")
        return jsonify({'success': False, 'error': str(e)})


@observer_bp.route('/goals')
@login_required
@observer_required
def goals():
    observer_id = session.get('user_id')
    children = get_observer_children(observer_id)

    # Get goals for all children
    all_goals = {}
    for child in children:
        child_goals = get_goals_by_child(child['id'])
        all_goals[child['id']] = child_goals

    return render_template('observer/goals.html', children=children, all_goals=all_goals)


@observer_bp.route('/add_goal', methods=['POST'])
@login_required
@observer_required
def add_goal():
    observer_id = session.get('user_id')
    child_id = request.form.get('child_id')
    goal_text = request.form.get('goal_text')
    target_date = request.form.get('target_date')

    goal_data = {
        "id": str(uuid.uuid4()),
        "observer_id": observer_id,
        "child_id": child_id,
        "goal_text": goal_text,
        "target_date": target_date,
        "status": "active",
        "created_at": datetime.now().isoformat()
    }

    try:
        supabase = get_supabase_client()
        supabase.table('goals').insert(goal_data).execute()
        flash('Goal added successfully!', 'success')
    except Exception as e:
        flash(f'Error adding goal: {str(e)}', 'error')

    return redirect(url_for('observer.goals'))


@observer_bp.route('/messages')
@login_required
@observer_required
def messages():
    observer_id = session.get('user_id')
    children = get_observer_children(observer_id)
    supabase = get_supabase_client()

    # Get parents for observer's children
    parents = []
    for child in children:
        try:
            parent_data = supabase.table('users').select("*").eq('child_id', child['id']).eq('role',
                                                                                             'Parent').execute().data
            if parent_data:
                parents.extend(parent_data)
        except Exception as e:
            logger.error(f"Error fetching parents for child {child['id']}: {str(e)}")

    # Get parent feedback for observer's reports
    feedback_data = []
    try:
        reports = supabase.table('observations').select("id, student_name, date, student_id").eq('username',
                                                                                                 observer_id).execute().data

        for report in reports:
            try:
                feedback = supabase.table('parent_feedback').select("*").eq('report_id', report['id']).execute().data
                for fb in feedback:
                    # Get parent info
                    parent_info = supabase.table('users').select("name, email").eq('child_id', report['student_id']).eq(
                        'role', 'Parent').execute().data
                    fb['parent_info'] = parent_info[0] if parent_info else {'name': 'Unknown Parent', 'email': ''}
                    fb['report_info'] = report

                    # Check for observer response
                    response = supabase.table('feedback_responses').select("*").eq('feedback_id',
                                                                                   fb['id']).execute().data
                    fb['observer_response'] = response[0] if response else None

                    feedback_data.append(fb)
            except Exception as e:
                logger.error(f"Error processing feedback for report {report['id']}: {str(e)}")

        # Sort by timestamp (newest first)
        feedback_data.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    except Exception as e:
        logger.error(f"Error loading reports: {str(e)}")

    # ===== PRINCIPAL FEEDBACK SECTION =====
    principal_feedback = []
    try:
        principal_feedback_response = supabase.table('principal_feedback').select(
            "id, feedback_text, feedback_type, created_at, principal_id"
        ).eq('observer_id', observer_id).order('created_at', desc=True).execute()

        principal_feedback = principal_feedback_response.data if principal_feedback_response.data else []

        # Enrich with principal names
        for fb in principal_feedback:
            principal_info = supabase.table('users').select("name").eq('id', fb['principal_id']).single().execute().data
            fb['principal_name'] = principal_info['name'] if principal_info else "Unknown Principal"
    except Exception as e:
        logger.error(f"Error loading principal feedback: {str(e)}")

    return render_template('observer/messages.html',
                           children=children,
                           parents=parents,
                           feedback_data=feedback_data,
                           principal_feedback=principal_feedback)  # Pass to template


@observer_bp.route('/respond_to_feedback', methods=['POST'])
@login_required
@observer_required
def respond_to_feedback():
    feedback_id = request.form.get('feedback_id')
    response_text = request.form.get('response_text')
    observer_id = session.get('user_id')

    if not feedback_id or not response_text:
        flash('Response text is required', 'error')
        return redirect(url_for('observer.messages'))

    try:
        supabase = get_supabase_client()

        # Check if response already exists
        existing_response = supabase.table('feedback_responses').select("*").eq('feedback_id',
                                                                                feedback_id).execute().data

        if existing_response:
            # Update existing response
            supabase.table('feedback_responses').update({
                'response_text': response_text.strip(),
                'timestamp': datetime.now().isoformat()
            }).eq('feedback_id', feedback_id).execute()
            flash('Response updated successfully!', 'success')
        else:
            # Create new feedback response
            response_data = {
                "id": str(uuid.uuid4()),
                "feedback_id": feedback_id,
                "observer_id": observer_id,
                "response_text": response_text.strip(),
                "timestamp": datetime.now().isoformat()
            }

            supabase.table('feedback_responses').insert(response_data).execute()
            flash('Response sent successfully!', 'success')

    except Exception as e:
        flash(f'Error sending response: {str(e)}', 'error')

    return redirect(url_for('observer.messages'))


@observer_bp.route('/get_messages/<parent_id>')
@login_required
@observer_required
def get_messages(parent_id):
    observer_id = session.get('user_id')
    messages = get_messages_between_users(observer_id, parent_id)
    return jsonify(messages)


@observer_bp.route('/send_message', methods=['POST'])
@login_required
@observer_required
def send_message():
    observer_id = session.get('user_id')
    parent_id = request.form.get('parent_id')
    content = request.form.get('content')

    message_data = {
        "id": str(uuid.uuid4()),
        "sender_id": observer_id,
        "receiver_id": parent_id,
        "content": content,
        "timestamp": datetime.now().isoformat(),
        "read": False
    }

    try:
        supabase = get_supabase_client()
        supabase.table('messages').insert(message_data).execute()
        flash('Message sent successfully!', 'success')
    except Exception as e:
        flash(f'Error sending message: {str(e)}', 'error')

    return redirect(url_for('observer.messages'))


@observer_bp.route('/get_messages_api/<parent_id>')
@login_required
@observer_required
def get_messages_api(parent_id):
    observer_id = session.get('user_id')
    try:
        supabase = get_supabase_client()

        # Get messages in both directions using separate queries
        messages1 = supabase.table('messages').select("*") \
            .eq('sender_id', observer_id).eq('receiver_id', parent_id) \
            .order('timestamp', desc=False).execute().data

        messages2 = supabase.table('messages').select("*") \
            .eq('sender_id', parent_id).eq('receiver_id', observer_id) \
            .order('timestamp', desc=False).execute().data

        # Combine and sort messages
        messages = sorted((messages1 or []) + (messages2 or []), key=lambda m: m['timestamp'])

        return jsonify(messages)
    except Exception as e:
        print(f"Error getting messages: {str(e)}")
        return jsonify([])


@observer_bp.route('/send_message_api', methods=['POST'])
@login_required
@observer_required
def send_message_api():
    observer_id = session.get('user_id')
    parent_id = request.form.get('receiver_id')
    content = request.form.get('content')

    if not parent_id or not content:
        return jsonify({'success': False, 'error': 'Missing data'})

    try:
        supabase = get_supabase_client()
        message_data = {
            "id": str(uuid.uuid4()),
            "sender_id": observer_id,
            "receiver_id": parent_id,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "read": False
        }

        supabase.table('messages').insert(message_data).execute()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@observer_bp.route('/monthly_reports')
@login_required
@observer_required
def monthly_reports():
    observer_id = session.get('user_id')
    children = get_observer_children(observer_id)

    return render_template('observer/monthly_reports.html', children=children)


@observer_bp.route('/generate_monthly_report', methods=['POST'])
@login_required
@observer_required
def generate_monthly_report():
    child_id = request.form.get('child_id')
    year = int(request.form.get('year'))
    month = int(request.form.get('month'))

    supabase = get_supabase_client()
    report_generator = MonthlyReportGenerator(supabase)

    # Get child name
    child_data = supabase.table('children').select("name").eq('id', child_id).execute().data
    child_name = child_data[0]['name'] if child_data else 'Student'

    # Get data
    observations = report_generator.get_month_data(child_id, year, month)
    goal_progress = report_generator.get_goal_progress(child_id, year, month)

    # Generate JSON formatted summary with graph suggestions
    json_summary = report_generator.generate_monthly_summary_json_format(
        observations, goal_progress, child_name, year, month
    )

    # Generate traditional charts for backward compatibility
    strength_counts = report_generator.get_strength_areas(observations)
    development_counts = report_generator.get_development_areas(observations)
    obs_chart = report_generator.generate_observation_frequency_chart(observations)
    strengths_chart = report_generator.generate_strengths_chart(strength_counts)
    development_chart = report_generator.generate_development_areas_chart(development_counts)
    goals_chart = report_generator.generate_goal_progress_chart(goal_progress)

    # Store in session for downloads
    session['last_monthly_report'] = json_summary
    session.permanent = True
    session.modified = True

    return jsonify({
        'success': True,
        'summary': json_summary,
        'charts': {
            'observations': obs_chart.to_json() if obs_chart else None,
            'strengths': strengths_chart.to_json() if strengths_chart else None,
            'development': development_chart.to_json() if development_chart else None,
            'goals': goals_chart.to_json() if goals_chart else None
        },
        'data': {
            'observations_count': len(observations),
            'goals_count': len(goal_progress),
            'strengths': strength_counts,
            'development': development_counts
        }
    })


@observer_bp.route('/download_monthly_report')
@login_required
@observer_required
def download_monthly_report():
    try:
        monthly_report = session.get('last_monthly_report')
        if not monthly_report:
            flash('No monthly report available for download', 'error')
            return redirect(url_for('observer.monthly_reports'))

        # Create Word document
        extractor = ObservationExtractor()
        doc_buffer = extractor.create_word_document_with_emojis(monthly_report)

        # Create filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"monthly_report_{timestamp}.docx"

        return send_file(
            doc_buffer,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )

    except Exception as e:
        flash(f'Error downloading monthly report: {str(e)}', 'error')
        return redirect(url_for('observer.monthly_reports'))


@observer_bp.route('/download_monthly_pdf')
@login_required
@observer_required
def download_monthly_pdf():
    try:
        monthly_report = session.get('last_monthly_report')
        if not monthly_report:
            flash('No monthly report available for download', 'error')
            return redirect(url_for('observer.monthly_reports'))

        # Create PDF
        extractor = ObservationExtractor()
        pdf_buffer = extractor.create_pdf_alternative(monthly_report)

        # Create filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"monthly_report_{timestamp}.pdf"

        return send_file(
            pdf_buffer,
            as_attachment=True,
            download_name=filename,
            mimetype='application/pdf'
        )

    except Exception as e:
        flash(f'Error downloading monthly PDF: {str(e)}', 'error')
        return redirect(url_for('observer.monthly_reports'))


@observer_bp.route('/email_monthly_report', methods=['POST'])
@login_required
@observer_required
def email_monthly_report():
    try:
        monthly_report = session.get('last_monthly_report')
        recipient_email = request.form.get('recipient_email')

        if not monthly_report or not recipient_email:
            return jsonify({'success': False, 'error': 'Missing report or email'})

        # Send email
        extractor = ObservationExtractor()
        subject = f"Monthly Observation Report - {datetime.now().strftime('%Y-%m')}"
        success, message = extractor.send_email(recipient_email, subject, monthly_report)

        return jsonify({'success': success, 'message': message})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@observer_bp.route('/mark_goal_achieved/<goal_id>', methods=['POST'])
@login_required
@observer_required
def mark_goal_achieved(goal_id):
    try:
        supabase = get_supabase_client()
        supabase.table('goals').update({'status': 'achieved'}).eq('id', goal_id).execute()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@observer_bp.route('/delete_goal/<goal_id>', methods=['DELETE'])
@login_required
@observer_required
def delete_goal(goal_id):
    try:
        supabase = get_supabase_client()
        supabase.table('goals').delete().eq('id', goal_id).execute()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# FIXED: Observer application route with RLS bypass
@observer_bp.route('/apply', methods=['GET', 'POST'])
def apply():
    """Observer application form - FIXED with RLS bypass"""
    if request.method == 'POST':
        try:
            # Get form data
            applicant_name = request.form.get('applicant_name', '').strip()
            applicant_email = request.form.get('applicant_email', '').strip().lower()
            applicant_phone = request.form.get('applicant_phone', '').strip()
            qualifications = request.form.get('qualifications', '').strip()
            experience_years = request.form.get('experience_years', '')
            motivation_text = request.form.get('motivation_text', '').strip()
            organization_id = request.form.get('organization_id', '')

            # Validation
            if not all([applicant_name, applicant_email, qualifications, experience_years, motivation_text,
                        organization_id]):
                flash('Please fill in all required fields', 'error')
                return render_template('observer/apply.html', organizations=get_organizations())

            try:
                experience_years = int(experience_years)
                if experience_years < 0:
                    flash('Experience years must be a positive number', 'error')
                    return render_template('observer/apply.html', organizations=get_organizations())
            except ValueError:
                flash('Experience years must be a valid number', 'error')
                return render_template('observer/apply.html', organizations=get_organizations())

            # Create application data
            application_data = {
                'id': str(uuid.uuid4()),
                'applicant_name': applicant_name,
                'applicant_email': applicant_email,
                'applicant_phone': applicant_phone,
                'qualifications': qualifications,
                'experience_years': experience_years,
                'motivation_text': motivation_text,
                'organization_id': organization_id,
                'status': 'pending',
                'applied_at': datetime.now().isoformat()
            }

            # FIXED: Use service role client to bypass RLS
            from supabase import create_client
            from config import Config

            service_key = getattr(Config, 'SUPABASE_SERVICE_KEY', None)

            if service_key:
                service_client = create_client(Config.SUPABASE_URL, service_key)
                result = service_client.table('observer_applications').insert(application_data,
                                                                              returning='minimal').execute()
                success = result.status_code == 201
            else:
                # Fallback: try with regular client and returning='minimal'
                supabase = get_supabase_client()
                result = supabase.table('observer_applications').insert(application_data, returning='minimal').execute()
                success = result.status_code == 201

            if success:
                flash('Observer application submitted successfully! You will be notified once reviewed.', 'success')
                return redirect(url_for('landing'))
            else:
                flash('Error submitting application. Please try again.', 'error')

        except Exception as e:
            logger.error(f"Error submitting observer application: {e}")
            flash('Application submission failed. Please try again.', 'error')

    try:
        organizations = get_organizations()
    except Exception as e:
        organizations = []
        flash('Error loading organizations. Please try again later.', 'error')

    return render_template('observer/apply.html', organizations=organizations)

