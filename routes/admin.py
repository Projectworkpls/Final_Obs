from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file, session
from models.database import (get_supabase_client, get_children, get_observers, get_parents,
                             save_observation, get_observer_children, upload_file_to_storage, get_signed_audio_url)
from models.observation_extractor import ObservationExtractor
from utils.decorators import admin_required
import pandas as pd
import uuid
import json
from datetime import datetime
import io
import re
import urllib.parse
import logging
import os

# Set up logging to replace print statements
logger = logging.getLogger(__name__)

admin_bp = Blueprint('admin', __name__)


@admin_bp.route('/dashboard')
@admin_required
def dashboard():
    # Get comprehensive analytics data for the dashboard
    try:
        supabase = get_supabase_client()

        # Get comprehensive analytics data
        users_response = supabase.table('users').select("id", count="exact").execute()
        observers_response = supabase.table('users').select("id", count="exact").eq('role', 'Observer').execute()
        parents_response = supabase.table('users').select("id", count="exact").eq('role', 'Parent').execute()
        children_response = supabase.table('children').select("id", count="exact").execute()
        observations_response = supabase.table('observations').select("id", count="exact").execute()

        # Get all reports with detailed information including file URLs
        all_reports_response = supabase.table('observations').select("""
            id, student_name, observer_name, date, timestamp, filename, 
            file_url, full_data, processed_by_admin, username, student_id
        """).order('timestamp', desc=True).execute()

        all_reports = all_reports_response.data if all_reports_response.data else []

        # Process reports to extract formatted reports and file info
        processed_reports = []
        for report in all_reports:
            processed_report = {
                'id': report.get('id'),
                'student_name': report.get('student_name', 'N/A'),
                'observer_name': report.get('observer_name', 'N/A'),
                'date': report.get('date', 'N/A'),
                'timestamp': report.get('timestamp', 'N/A'),
                'filename': report.get('filename', 'N/A'),
                'file_url': report.get('file_url'),
                'processed_by_admin': report.get('processed_by_admin', False),
                'has_formatted_report': False,
                'formatted_report': None,
                'file_type': None,
                'signed_url': None
            }

            # URL encode the file_url to handle spaces and special characters
            if processed_report['file_url']:
                # Properly encode the URL to handle spaces and special characters
                processed_report['file_url'] = urllib.parse.quote(processed_report['file_url'],
                                                                  safe=':/?#[]@!$&\'()*+,;=')

                # Determine file type from URL or filename
                file_url_lower = processed_report['file_url'].lower()
                if any(ext in file_url_lower for ext in ['.mp3', '.wav', '.m4a', '.ogg']):
                    processed_report['file_type'] = 'audio'
                    # Create signed URL for audio files for better compatibility
                    filename = processed_report['file_url'].split('/')[-1]
                    signed_url = get_signed_audio_url(filename)
                    if signed_url:
                        processed_report['signed_url'] = signed_url
                elif any(ext in file_url_lower for ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp']):
                    processed_report['file_type'] = 'image'

            # Extract formatted report from full_data
            if report.get('full_data'):
                try:
                    full_data = json.loads(report['full_data'])
                    if full_data.get('formatted_report'):
                        processed_report['has_formatted_report'] = True
                        processed_report['formatted_report'] = full_data['formatted_report']
                except:
                    pass

            processed_reports.append(processed_report)

        # Get recent activity (last 10 observations)
        recent_observations = processed_reports[:10]

        # Get system status data
        total_storage_files = supabase.table('observations').select("file_url").not_.is_('file_url', 'null').execute()

        analytics = {
            'total_users': users_response.count if users_response.count else 0,
            'observers_count': observers_response.count if observers_response.count else 0,
            'parents_count': parents_response.count if parents_response.count else 0,
            'children_count': children_response.count if children_response.count else 0,
            'observations_count': observations_response.count if observations_response.count else 0,
            'storage_files': len(total_storage_files.data) if total_storage_files.data else 0,
            'recent_observations': recent_observations,
            'all_reports': processed_reports
        }

    except Exception as e:
        analytics = {
            'total_users': 0, 'observers_count': 0, 'parents_count': 0,
            'children_count': 0, 'observations_count': 0, 'storage_files': 0,
            'recent_observations': [], 'all_reports': []
        }

    return render_template('admin/dashboard.html', analytics=analytics)


@admin_bp.route('/view_report/<report_id>')
@admin_required
def view_report(report_id):
    try:
        supabase = get_supabase_client()

        # Get the specific report
        report_response = supabase.table('observations').select("*").eq('id', report_id).execute()

        if not report_response.data:
            flash('Report not found', 'error')
            return redirect(url_for('admin.dashboard'))

        report = report_response.data[0]

        # URL encode the file_url if it exists and create signed URL for audio
        if report.get('file_url'):
            report['file_url'] = urllib.parse.quote(report['file_url'], safe=':/?#[]@!$&\'()*+,;=')

            # If it's an audio file, create signed URL
            if any(ext in report['file_url'].lower() for ext in ['.mp3', '.wav', '.m4a', '.ogg']):
                filename = report['file_url'].split('/')[-1]
                signed_url = get_signed_audio_url(filename)
                if signed_url:
                    report['signed_url'] = signed_url

        # Extract formatted report from full_data
        formatted_report = None
        if report.get('full_data'):
            try:
                full_data = json.loads(report['full_data'])
                formatted_report = full_data.get('formatted_report')
            except:
                pass

        # If no formatted report exists, generate one
        if not formatted_report:
            observations_text = report.get('observations', '')
            if observations_text:
                user_info = {
                    'student_name': report.get('student_name', 'N/A'),
                    'observer_name': report.get('observer_name', 'N/A'),
                    'session_date': report.get('date', 'N/A'),
                    'session_start': '',
                    'session_end': ''
                }

                # Generate formatted report
                extractor = ObservationExtractor()
                formatted_report = extractor.generate_report_from_text(observations_text, user_info)

                # Update the database with the formatted report
                updated_full_data = json.loads(report.get('full_data', '{}'))
                updated_full_data['formatted_report'] = formatted_report

                supabase.table('observations').update({
                    'full_data': json.dumps(updated_full_data)
                }).eq('id', report_id).execute()

        return render_template('admin/view_report.html',
                               report=report,
                               formatted_report=formatted_report)

    except Exception as e:
        flash(f'Error loading report: {str(e)}', 'error')
        return redirect(url_for('admin.dashboard'))


@admin_bp.route('/generate_transcript/<report_id>')
@admin_required
def generate_transcript(report_id):
    """Generate conversational transcript from audio/text observations"""
    try:
        supabase = get_supabase_client()

        # Get the specific report
        report_response = supabase.table('observations').select("*").eq('id', report_id).execute()

        if not report_response.data:
            return jsonify({'success': False, 'error': 'Report not found'})

        report = report_response.data[0]

        # Get the raw observations/transcript
        raw_text = report.get('observations', '')

        if not raw_text:
            return jsonify({'success': False, 'error': 'No transcript data available'})

        # Generate conversational format using Gemini API
        extractor = ObservationExtractor()
        conversational_transcript = extractor.generate_conversational_transcript(raw_text)

        return jsonify({
            'success': True,
            'transcript': conversational_transcript,
            'student_name': report.get('student_name', 'Unknown'),
            'observer_name': report.get('observer_name', 'Unknown'),
            'date': report.get('date', 'Unknown')
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@admin_bp.route('/download_report/<report_id>')
@admin_required
def download_report(report_id):
    try:
        supabase = get_supabase_client()
        report_data = supabase.table('observations').select("*").eq('id', report_id).execute().data

        if not report_data:
            flash('Report not found', 'error')
            return redirect(url_for('admin.dashboard'))

        report = report_data[0]

        # Get formatted report from full_data
        formatted_report = None
        if report.get('full_data'):
            try:
                full_data = json.loads(report['full_data'])
                formatted_report = full_data.get('formatted_report')
            except:
                pass

        if not formatted_report:
            flash('No formatted report available', 'error')
            return redirect(url_for('admin.dashboard'))

        # Create Word document
        extractor = ObservationExtractor()
        doc_buffer = extractor.create_word_document_with_emojis(formatted_report)

        # Create filename
        student_name = report['student_name']
        if student_name:
            clean_name = re.sub(r'[^\w\s-]', '', student_name).strip()
            clean_name = re.sub(r'[-\s]+', '_', clean_name)
        else:
            clean_name = 'Student'

        date = report['date'] if report['date'] else datetime.now().strftime('%Y-%m-%d')
        filename = f"report_{clean_name}_{date}.docx"

        return send_file(
            doc_buffer,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )

    except Exception as e:
        flash(f'Error downloading report: {str(e)}', 'error')
        return redirect(url_for('admin.dashboard'))


@admin_bp.route('/user_management')
@admin_required
def user_management():
    try:
        supabase = get_supabase_client()
        users = supabase.table('users').select("*").execute().data
        children = get_children()
        return render_template('admin/user_management.html', users=users, children=children)
    except Exception as e:
        flash(f'Error loading user management: {str(e)}', 'error')
        return render_template('admin/user_management.html', users=[], children=[])


@admin_bp.route('/add_user', methods=['POST'])
@admin_required
def add_user():
    name = request.form.get('name')
    email = request.form.get('email').strip().lower()
    role = request.form.get('role')
    password = request.form.get('password')
    child_id = request.form.get('child_id') if role == 'Parent' else None

    user_data = {
        "id": str(uuid.uuid4()),
        "email": email,
        "name": name,
        "password": password,
        "role": role,
        "created_at": datetime.now().isoformat()
    }

    if child_id:
        user_data["child_id"] = child_id

    try:
        supabase = get_supabase_client()
        supabase.table('users').insert(user_data).execute()
        flash('User added successfully!', 'success')
    except Exception as e:
        flash(f'Error adding user: {str(e)}', 'error')

    return redirect(url_for('admin.user_management'))


@admin_bp.route('/bulk_upload_users', methods=['POST'])
@admin_required
def bulk_upload_users():
    if 'file' not in request.files:
        flash('No file selected', 'error')
        return redirect(url_for('admin.user_management'))

    file = request.files['file']
    upload_type = request.form.get('upload_type')

    if file.filename == '':
        flash('No file selected', 'error')
        return redirect(url_for('admin.user_management'))

    try:
        df = pd.read_csv(file)
        supabase = get_supabase_client()

        if upload_type == 'children':
            if 'name' not in df.columns:
                flash('CSV must contain a "name" column', 'error')
                return redirect(url_for('admin.user_management'))

            children_data = []
            for _, row in df.iterrows():
                child_data = {
                    "id": str(uuid.uuid4()),
                    "name": row['name'],
                    "birth_date": row.get('birth_date', None),
                    "grade": row.get('grade', None),
                    "created_at": datetime.now().isoformat()
                }
                children_data.append(child_data)

            batch_size = 50
            for i in range(0, len(children_data), batch_size):
                batch = children_data[i:i + batch_size]
                supabase.table('children').insert(batch).execute()

            flash(f'Successfully added {len(children_data)} children!', 'success')

        elif upload_type == 'parents':
            required_cols = ['name', 'email', 'password']
            if not all(col in df.columns for col in required_cols):
                flash('CSV must contain "name", "email", and "password" columns', 'error')
                return redirect(url_for('admin.user_management'))

            parents_data = []
            for _, row in df.iterrows():
                parent_data = {
                    "id": str(uuid.uuid4()),
                    "name": row['name'],
                    "email": row['email'].strip().lower(),
                    "password": row['password'],
                    "role": "Parent",
                    "created_at": datetime.now().isoformat()
                }
                parents_data.append(parent_data)

            batch_size = 50
            for i in range(0, len(parents_data), batch_size):
                batch = parents_data[i:i + batch_size]
                supabase.table('users').insert(batch).execute()

            flash(f'Successfully added {len(parents_data)} parents!', 'success')

        elif upload_type == 'observers':
            required_cols = ['name', 'email', 'password']
            if not all(col in df.columns for col in required_cols):
                flash('CSV must contain "name", "email", and "password" columns', 'error')
                return redirect(url_for('admin.user_management'))

            observers_data = []
            for _, row in df.iterrows():
                observer_data = {
                    "id": str(uuid.uuid4()),
                    "name": row['name'],
                    "email": row['email'].strip().lower(),
                    "password": row['password'],
                    "role": "Observer",
                    "created_at": datetime.now().isoformat()
                }
                observers_data.append(observer_data)

            batch_size = 50
            for i in range(0, len(observers_data), batch_size):
                batch = observers_data[i:i + batch_size]
                supabase.table('users').insert(batch).execute()

            flash(f'Successfully added {len(observers_data)} observers!', 'success')

    except Exception as e:
        flash(f'Error processing file: {str(e)}', 'error')

    return redirect(url_for('admin.user_management'))


@admin_bp.route('/mappings')
@admin_required
def mappings():
    try:
        observers = get_observers()
        children = get_children()
        parents = get_parents()

        supabase = get_supabase_client()
        observer_mappings = supabase.table('observer_child_mappings').select("*").execute().data

        return render_template('admin/mappings.html',
                               observers=observers,
                               children=children,
                               parents=parents,
                               observer_mappings=observer_mappings)
    except Exception as e:
        flash(f'Error loading mappings: {str(e)}', 'error')
        return render_template('admin/mappings.html', observers=[], children=[], parents=[], observer_mappings=[])


@admin_bp.route('/add_mapping', methods=['POST'])
@admin_required
def add_mapping():
    mapping_type = request.form.get('mapping_type')
    supabase = get_supabase_client()

    if mapping_type == 'observer_child':
        observer_id = request.form.get('observer_id')
        child_id = request.form.get('child_id')

        mapping_data = {
            "id": str(uuid.uuid4()),
            "observer_id": observer_id,
            "child_id": child_id,
            "created_at": datetime.now().isoformat()
        }

        try:
            supabase.table('observer_child_mappings').insert(mapping_data).execute()
            flash('Observer-Child mapping added successfully!', 'success')
        except Exception as e:
            flash(f'Error adding mapping: {str(e)}', 'error')

    elif mapping_type == 'parent_child':
        parent_id = request.form.get('parent_id')
        child_id = request.form.get('child_id')

        try:
            supabase.table('users').update({'child_id': child_id}).eq('id', parent_id).execute()
            flash('Parent-Child mapping added successfully!', 'success')
        except Exception as e:
            flash(f'Error adding mapping: {str(e)}', 'error')

    return redirect(url_for('admin.mappings'))


@admin_bp.route('/bulk_upload_mappings', methods=['POST'])
@admin_required
def bulk_upload_mappings():
    if 'file' not in request.files:
        flash('No file selected', 'error')
        return redirect(url_for('admin.mappings'))

    file = request.files['file']
    mapping_type = request.form.get('mapping_type')

    try:
        df = pd.read_csv(file)
        supabase = get_supabase_client()

        if mapping_type == 'observer_child':
            if not all(col in df.columns for col in ['observer_id', 'child_id']):
                flash('CSV must contain "observer_id" and "child_id" columns', 'error')
                return redirect(url_for('admin.mappings'))

            mappings_data = []
            for _, row in df.iterrows():
                mapping_data = {
                    "id": str(uuid.uuid4()),
                    "observer_id": row['observer_id'],
                    "child_id": row['child_id'],
                    "created_at": datetime.now().isoformat()
                }
                mappings_data.append(mapping_data)

            supabase.table('observer_child_mappings').insert(mappings_data).execute()
            flash(f'Successfully added {len(mappings_data)} observer-child mappings!', 'success')

        elif mapping_type == 'parent_child':
            if not all(col in df.columns for col in ['parent_email', 'child_name']):
                flash('CSV must contain "parent_email" and "child_name" columns', 'error')
                return redirect(url_for('admin.mappings'))

            children = get_children()
            parents = get_parents()

            child_name_to_id = {c['name'].lower(): c['id'] for c in children}
            parent_email_to_id = {p['email'].lower(): p['id'] for p in parents}

            success_count = 0
            for _, row in df.iterrows():
                parent_email = row['parent_email'].strip().lower()
                child_name = row['child_name'].strip().lower()

                parent_id = parent_email_to_id.get(parent_email)
                child_id = child_name_to_id.get(child_name)

                if parent_id and child_id:
                    supabase.table('users').update({'child_id': child_id}).eq('id', parent_id).execute()
                    success_count += 1

            flash(f'Successfully mapped {success_count} parent-child relationships!', 'success')

    except Exception as e:
        flash(f'Error processing file: {str(e)}', 'error')

    return redirect(url_for('admin.mappings'))


@admin_bp.route('/process_reports')
@admin_required
def process_reports():
    try:
        observers = get_observers()
        return render_template('admin/process_reports.html', observers=observers)
    except Exception as e:
        flash(f'Error loading process reports: {str(e)}', 'error')
        return render_template('admin/process_reports.html', observers=[])


@admin_bp.route('/get_observer_children/<observer_id>')
@admin_required
def get_observer_children_api(observer_id):
    try:
        children = get_observer_children(observer_id)
        return jsonify(children)
    except Exception as e:
        return jsonify([])


@admin_bp.route('/process_observation', methods=['POST'])
@admin_required
def process_observation():
    observer_id = request.form.get('observer_id')
    child_id = request.form.get('child_id')
    processing_mode = request.form.get('processing_mode')
    session_date = request.form.get('session_date')
    session_start = request.form.get('session_start')
    session_end = request.form.get('session_end')

    try:
        supabase = get_supabase_client()
        observer = supabase.table('users').select("name").eq('id', observer_id).execute().data
        child = supabase.table('children').select("name").eq('id', child_id).execute().data

        observer_name = observer[0]['name'] if observer else 'Unknown Observer'
        child_name = child[0]['name'] if child else 'Unknown Child'

        user_info = {
            'student_name': child_name,
            'observer_name': observer_name,
            'session_date': session_date,
            'session_start': session_start,
            'session_end': session_end
        }

        extractor = ObservationExtractor()
        observation_id = str(uuid.uuid4())

        if processing_mode == 'ocr':
            if 'file' not in request.files:
                flash('No file uploaded', 'error')
                return redirect(url_for('admin.process_reports'))

            file = request.files['file']

            # Extract text and process
            extracted_text = extractor.extract_text_with_ocr(file)
            structured_data = extractor.process_with_groq(extracted_text)
            observations_text = structured_data.get("observations", "")

            # Upload file to storage
            file.seek(0)
            file_url = upload_file_to_storage(
                file.read(),
                file.filename,
                f"image/{file.content_type.split('/')[1]}"
            )

            # Generate formatted report
            report = extractor.generate_report_from_text(observations_text, user_info)

            # Save observation - store formatted report in full_data
            observation_data = {
                "id": observation_id,
                "student_id": child_id,
                "username": observer_id,
                "student_name": structured_data.get("studentName", child_name),
                "observer_name": observer_name,
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
                "processed_by_admin": True,
                "file_url": file_url
            }

            # Save processed data separately
            processed_data = {
                "id": str(uuid.uuid4()),
                "child_id": child_id,
                "observer_id": observer_id,
                "processing_type": "ocr",
                "extracted_text": extracted_text,
                "structured_data": json.dumps(structured_data),
                "generated_report": report,
                "timestamp": datetime.now().isoformat(),
                "file_url": file_url
            }

            # Save to database
            supabase.table('observations').insert(observation_data).execute()
            supabase.table('processed_observations').insert(processed_data).execute()

            flash('OCR observation processed and saved successfully!', 'success')

        elif processing_mode == 'audio':
            if 'file' not in request.files:
                flash('No file uploaded', 'error')
                return redirect(url_for('admin.process_reports'))

            file = request.files['file']

            # Transcribe audio
            transcript = extractor.transcribe_with_assemblyai(file)

            # Upload file to storage
            file.seek(0)
            file_url = upload_file_to_storage(
                file.read(),
                file.filename,
                f"audio/{file.content_type.split('/')[1]}"
            )

            # Generate formatted report from transcript
            report = extractor.generate_report_from_text(transcript, user_info)

            # Save observation - store formatted report in full_data
            observation_data = {
                "id": observation_id,
                "student_id": child_id,
                "username": observer_id,
                "student_name": child_name,
                "observer_name": observer_name,
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
                    "formatted_report": report
                }),
                "theme_of_day": "",
                "curiosity_seed": "",
                "processed_by_admin": True,
                "file_url": file_url
            }

            # Save processed data separately
            processed_data = {
                "id": str(uuid.uuid4()),
                "child_id": child_id,
                "observer_id": observer_id,
                "processing_type": "audio",
                "extracted_text": transcript,
                "structured_data": json.dumps({"transcript": transcript}),
                "generated_report": report,
                "timestamp": datetime.now().isoformat(),
                "file_url": file_url
            }

            # Save to database
            supabase.table('observations').insert(observation_data).execute()
            supabase.table('processed_observations').insert(processed_data).execute()

            flash('Audio observation processed and saved successfully!', 'success')

        # Store report ID in session for downloads
        session['last_admin_report_id'] = observation_id
        session['last_admin_report'] = report

    except Exception as e:
        flash(f'Error processing observation: {str(e)}', 'error')

    return redirect(url_for('admin.process_reports'))


@admin_bp.route('/download_admin_report')
@admin_required
def download_admin_report():
    try:
        report_id = session.get('last_admin_report_id')
        if not report_id:
            flash('No report available for download', 'error')
            return redirect(url_for('admin.process_reports'))

        # Get the report from database
        supabase = get_supabase_client()
        report_data = supabase.table('observations').select("*").eq('id', report_id).execute().data

        if not report_data:
            flash('Report not found', 'error')
            return redirect(url_for('admin.process_reports'))

        report = report_data[0]

        # Get formatted report from full_data
        formatted_report = None
        if report.get('full_data'):
            try:
                full_data = json.loads(report['full_data'])
                formatted_report = full_data.get('formatted_report')
            except:
                pass

        if not formatted_report:
            flash('No formatted report available', 'error')
            return redirect(url_for('admin.process_reports'))

        # Create Word document
        extractor = ObservationExtractor()
        doc_buffer = extractor.create_word_document_with_emojis(formatted_report)

        # Create filename
        student_name = report['student_name']
        if student_name:
            clean_name = re.sub(r'[^\w\s-]', '', student_name).strip()
            clean_name = re.sub(r'[-\s]+', '_', clean_name)
        else:
            clean_name = 'Student'

        date = report['date'] if report['date'] else datetime.now().strftime('%Y-%m-%d')
        filename = f"admin_report_{clean_name}_{date}.docx"

        return send_file(
            doc_buffer,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )

    except Exception as e:
        flash(f'Error downloading report: {str(e)}', 'error')
        return redirect(url_for('admin.process_reports'))


@admin_bp.route('/download_admin_pdf')
@admin_required
def download_admin_pdf():
    try:
        report_id = session.get('last_admin_report_id')
        if not report_id:
            flash('No report available for download', 'error')
            return redirect(url_for('admin.process_reports'))

        # Get the report from database
        supabase = get_supabase_client()
        report_data = supabase.table('observations').select("*").eq('id', report_id).execute().data

        if not report_data:
            flash('Report not found', 'error')
            return redirect(url_for('admin.process_reports'))

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
            return redirect(url_for('admin.process_reports'))

        # Create PDF
        extractor = ObservationExtractor()
        pdf_buffer = extractor.create_pdf_with_emojis(formatted_report)

        # Create filename
        student_name = report['student_name']
        if student_name:
            clean_name = re.sub(r'[^\w\s-]', '', student_name).strip()
            clean_name = re.sub(r'[-\s]+', '_', clean_name)
        else:
            clean_name = 'Student'

        date = report['date'] if report['date'] else datetime.now().strftime('%Y-%m-%d')
        filename = f"admin_report_{clean_name}_{date}.pdf"

        return send_file(
            pdf_buffer,
            as_attachment=True,
            download_name=filename,
            mimetype='application/pdf'
        )

    except Exception as e:
        flash(f'Error downloading PDF: {str(e)}', 'error')
        return redirect(url_for('admin.process_reports'))


@admin_bp.route('/email_report', methods=['POST'])
@admin_required
def email_report():
    try:
        report_id = session.get('last_admin_report_id')
        recipient_email = request.form.get('recipient_email')
        subject = request.form.get('subject', 'Observation Report (Admin Processed)')
        additional_message = request.form.get('additional_message', '')

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

        # Prepare email content
        email_content = f"""
{additional_message}

{formatted_report}

---
This report was processed by the administrator.
"""

        # Send email
        extractor = ObservationExtractor()
        success, message = extractor.send_email(recipient_email, subject, email_content)

        return jsonify({'success': success, 'message': message})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@admin_bp.route('/delete_user/<user_id>')
@admin_required
def delete_user(user_id):
    try:
        supabase = get_supabase_client()
        supabase.table('users').delete().eq('id', user_id).execute()
        flash('User deleted successfully!', 'success')
    except Exception as e:
        flash(f'Error deleting user: {str(e)}', 'error')
    return redirect(url_for('admin.user_management'))


@admin_bp.route('/delete_mapping/<mapping_id>')
@admin_required
def delete_mapping(mapping_id):
    try:
        supabase = get_supabase_client()
        supabase.table('observer_child_mappings').delete().eq('id', mapping_id).execute()
        flash('Mapping deleted successfully!', 'success')
    except Exception as e:
        flash(f'Error deleting mapping: {str(e)}', 'error')
    return redirect(url_for('admin.mappings'))
