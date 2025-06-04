from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session, send_file
from flask_login import login_required, current_user
from models.database import (get_supabase_client, get_observer_children, save_observation,
                             get_observations_by_child, save_goal, get_goals_by_child,
                             get_messages_between_users, save_message, save_processed_data, upload_file_to_storage,
                             get_scheduled_reports_for_observer, get_next_scheduled_time_for_child,
                             check_if_report_processed_today, save_scheduled_report, log_report_processing,
                             get_child_schedule_status)
from models.observation_extractor import ObservationExtractor
from models.monthly_report_generator import MonthlyReportGenerator
from utils.decorators import observer_required
import json
from datetime import datetime, timedelta
import uuid
import io
import re

observer_bp = Blueprint('observer', __name__)


@observer_bp.route('/dashboard')
@login_required
@observer_required
def dashboard():
    observer_id = session.get('user_id')

    # Get schedule status for all children
    schedule_status = get_child_schedule_status(observer_id)

    return render_template('observer/dashboard.html', schedule_status=schedule_status)


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
                "file_url": file_url
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

                "file_url": file_url

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

        # FIXED: Use alternative PDF creation method without WeasyPrint
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

        # FIXED: Store full report in session for downloads
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


# ADDED: Custom report email functionality
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


# UPDATED: Enhanced messages route with feedback functionality
@observer_bp.route('/messages')
@login_required
@observer_required
def messages():
    observer_id = session.get('user_id')
    children = get_observer_children(observer_id)

    # Get parents for these children
    parents = []
    supabase = get_supabase_client()
    for child in children:
        parent_data = supabase.table('users').select("*").eq('child_id', child['id']).eq('role',
                                                                                         'Parent').execute().data
        if parent_data:
            parents.extend(parent_data)

    # NEW: Get all feedback for this observer's reports
    feedback_data = []
    try:
        # Get all reports by this observer
        reports = supabase.table('observations').select("id, student_name, date, student_id").eq('username',
                                                                                                 observer_id).execute().data

        # Get feedback for these reports
        for report in reports:
            feedback = supabase.table('parent_feedback').select("*").eq('report_id', report['id']).execute().data

            for fb in feedback:
                # Get parent info
                parent_info = supabase.table('users').select("name, email").eq('child_id', report['student_id']).eq(
                    'role', 'Parent').execute().data
                fb['parent_info'] = parent_info[0] if parent_info else {'name': 'Unknown Parent', 'email': ''}
                fb['report_info'] = report

                # Check if observer has responded
                response = supabase.table('feedback_responses').select("*").eq('feedback_id', fb['id']).execute().data
                fb['observer_response'] = response[0] if response else None

                feedback_data.append(fb)

        # Sort by timestamp (newest first)
        feedback_data.sort(key=lambda x: x.get('timestamp', ''), reverse=True)

    except Exception as e:
        print(f"Error loading feedback: {e}")
        feedback_data = []

    return render_template('observer/messages.html',
                           children=children,
                           parents=parents,
                           feedback_data=feedback_data)


# NEW: Feedback response route
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


# UPDATED: Enhanced monthly report generation with JSON format and graph suggestions
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


# ADDED: Monthly report download routes
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
