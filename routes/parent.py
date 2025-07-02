from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session, send_file
from flask_login import login_required
from models.database import (get_supabase_client, get_observations_by_child, get_goals_by_child,
                             get_messages_between_users, save_message)
from models.monthly_report_generator import MonthlyReportGenerator
from utils.decorators import parent_required
import json
from datetime import datetime, timedelta
import uuid
import re
from models.observation_extractor import ObservationExtractor

parent_bp = Blueprint('parent', __name__)


@parent_bp.route('/dashboard')
@login_required
@parent_required
def dashboard():
    user_id = session.get('user_id')
    child_id = session.get('child_id')

    if not child_id:
        flash('No child assigned to your account. Please contact admin.', 'warning')
        return render_template('parent/dashboard.html', child=None, observer=None, reports=[])

    try:
        # Get child information
        supabase = get_supabase_client()
        child_data = supabase.table('children').select("*").eq('id', child_id).execute().data
        child = child_data[0] if child_data else None

        # Get observer information
        mapping = supabase.table('observer_child_mappings').select("observer_id").eq("child_id",
                                                                                     child_id).execute().data
        observer = None
        if mapping:
            observer_id = mapping[0]['observer_id']
            observer_data = supabase.table('users').select("*").eq('id', observer_id).execute().data
            observer = observer_data[0] if observer_data else None

        # Get recent reports
        reports = get_observations_by_child(child_id, limit=10)

        return render_template('parent/dashboard.html', child=child, observer=observer, reports=reports)
    except Exception as e:
        flash(f'Error loading dashboard: {str(e)}', 'error')
        return render_template('parent/dashboard.html', child=None, observer=None, reports=[])


@parent_bp.route('/reports')
@login_required
@parent_required
def reports():
    child_id = session.get('child_id')

    if not child_id:
        flash('No child assigned to your account.', 'warning')
        return render_template('parent/reports.html', reports=[], feedback_data={})

    try:
        reports = get_observations_by_child(child_id)

        # Parse JSON data for each report
        for report in reports:
            # Parse full_data JSON
            if report.get('full_data'):
                try:
                    if isinstance(report['full_data'], str):
                        report['full_data_parsed'] = json.loads(report['full_data'])
                    else:
                        report['full_data_parsed'] = report['full_data']
                except:
                    report['full_data_parsed'] = {}
            else:
                report['full_data_parsed'] = {}

            # Parse strengths JSON
            if report.get('strengths'):
                try:
                    if isinstance(report['strengths'], str):
                        report['strengths_parsed'] = json.loads(report['strengths'])
                    else:
                        report['strengths_parsed'] = report['strengths']
                except:
                    report['strengths_parsed'] = []
            else:
                report['strengths_parsed'] = []

            # Parse areas_of_development JSON
            if report.get('areas_of_development'):
                try:
                    if isinstance(report['areas_of_development'], str):
                        report['areas_parsed'] = json.loads(report['areas_of_development'])
                    else:
                        report['areas_parsed'] = report['areas_of_development']
                except:
                    report['areas_parsed'] = []
            else:
                report['areas_parsed'] = []

            # Parse recommendations JSON
            if report.get('recommendations'):
                try:
                    if isinstance(report['recommendations'], str):
                        report['recommendations_parsed'] = json.loads(report['recommendations'])
                    else:
                        report['recommendations_parsed'] = report['recommendations']
                except:
                    report['recommendations_parsed'] = []
            else:
                report['recommendations_parsed'] = []

        # Get existing feedback
        supabase = get_supabase_client()
        feedback_data = {}
        for report in reports:
            feedback = supabase.table('parent_feedback').select("*").eq('report_id', report['id']).eq('parent_id',
                                                                                                      session.get(
                                                                                                          'user_id')).execute().data
            if feedback:
                feedback_data[report['id']] = feedback[0]

        return render_template('parent/reports.html', reports=reports, feedback_data=feedback_data)
    except Exception as e:
        flash(f'Error loading reports: {str(e)}', 'error')
        return render_template('parent/reports.html', reports=[], feedback_data={})


@parent_bp.route('/view_report/<report_id>')
@login_required
@parent_required
def view_report(report_id):
    try:
        child_id = session.get('child_id')

        if not child_id:
            flash('No child assigned to your account.', 'warning')
            return redirect(url_for('parent.dashboard'))

        supabase = get_supabase_client()

        # Get the specific report and verify it belongs to this parent's child
        report_data = supabase.table('observations').select("*").eq('id', report_id).eq('student_id',
                                                                                        child_id).execute().data

        if not report_data:
            flash('Report not found or access denied', 'error')
            return redirect(url_for('parent.reports'))

        report = report_data[0]

        # Get formatted report from full_data
        formatted_report = None
        if report.get('full_data'):
            try:
                full_data = json.loads(report['full_data'])
                formatted_report = full_data.get('formatted_report')
            except Exception as e:
                pass

        # If no formatted report, use observations text
        if not formatted_report:
            formatted_report = report.get('observations', 'No report content available')

        # Get existing feedback for this report
        feedback_data = supabase.table('parent_feedback').select("*").eq('report_id', report_id).eq('parent_id',
                                                                                                    session.get(
                                                                                                        'user_id')).execute().data
        existing_feedback = feedback_data[0] if feedback_data else None

        # Parse strengths, development areas, and recommendations if available
        strengths = []
        development_areas = []
        recommendations = []

        try:
            if report.get('strengths'):
                strengths = json.loads(report['strengths']) if isinstance(report['strengths'], str) else report[
                    'strengths']
            if report.get('areas_of_development'):
                development_areas = json.loads(report['areas_of_development']) if isinstance(
                    report['areas_of_development'], str) else report['areas_of_development']
            if report.get('recommendations'):
                recommendations = json.loads(report['recommendations']) if isinstance(report['recommendations'],
                                                                                      str) else report[
                    'recommendations']
        except Exception as e:
            pass

        return render_template('parent/view_report.html',
                               report=report,
                               formatted_report=formatted_report,
                               existing_feedback=existing_feedback,
                               strengths=strengths,
                               development_areas=development_areas,
                               recommendations=recommendations)

    except Exception as e:
        flash(f'Error loading report: {str(e)}', 'error')
        return redirect(url_for('parent.reports'))


@parent_bp.route('/submit_feedback', methods=['POST'])
@login_required
@parent_required
def submit_feedback():
    report_id = request.form.get('report_id')
    feedback_text = request.form.get('feedback_text')
    rating = request.form.get('rating')

    if not report_id or not feedback_text or not rating:
        flash('All fields are required', 'error')
        return redirect(url_for('parent.view_report', report_id=report_id))

    feedback_data = {
        "id": str(uuid.uuid4()),
        "report_id": report_id,
        "parent_id": session.get('user_id'),
        "feedback_text": feedback_text,
        "rating": int(rating),
        "timestamp": datetime.now().isoformat()
    }

    try:
        supabase = get_supabase_client()

        # Check if feedback already exists
        existing = supabase.table('parent_feedback').select("*").eq('report_id', report_id).eq('parent_id', session.get(
            'user_id')).execute().data

        if existing:
            # Update existing feedback
            supabase.table('parent_feedback').update({
                'feedback_text': feedback_text,
                'rating': int(rating),
                'timestamp': datetime.now().isoformat()
            }).eq('id', existing[0]['id']).execute()
            flash('Feedback updated successfully!', 'success')
        else:
            # Insert new feedback
            supabase.table('parent_feedback').insert(feedback_data).execute()
            flash('Feedback submitted successfully!', 'success')

    except Exception as e:
        flash(f'Error submitting feedback: {str(e)}', 'error')

    return redirect(url_for('parent.view_report', report_id=report_id))


@parent_bp.route('/messages')
@login_required
@parent_required
def messages():
    user_id = session.get('user_id')
    child_id = session.get('child_id')

    if not child_id:
        flash('No child assigned to your account.', 'warning')
        return render_template('parent/messages.html', observer=None, messages=[])

    try:
        # Get observer information
        supabase = get_supabase_client()
        mapping = supabase.table('observer_child_mappings').select("observer_id").eq("child_id",
                                                                                     child_id).execute().data
        observer = None
        messages = []

        if mapping:
            observer_id = mapping[0]['observer_id']
            observer_data = supabase.table('users').select("*").eq('id', observer_id).execute().data
            observer = observer_data[0] if observer_data else None

            # Get messages
            if observer:
                messages = get_messages_between_users(user_id, observer_id)

        return render_template('parent/messages.html', observer=observer, messages=messages)
    except Exception as e:
        flash(f'Error loading messages: {str(e)}', 'error')
        return render_template('parent/messages.html', observer=None, messages=[])


@parent_bp.route('/send_message', methods=['POST'])
@login_required
@parent_required
def send_message():
    user_id = session.get('user_id')
    child_id = session.get('child_id')
    content = request.form.get('content')

    if not content or not content.strip():
        flash('Message content cannot be empty', 'error')
        return redirect(url_for('parent.messages'))

    try:
        # Get observer ID
        supabase = get_supabase_client()
        mapping = supabase.table('observer_child_mappings').select("observer_id").eq("child_id",
                                                                                     child_id).execute().data
        if not mapping:
            flash('No observer assigned to your child.', 'error')
            return redirect(url_for('parent.messages'))

        observer_id = mapping[0]['observer_id']

        message_data = {
            "id": str(uuid.uuid4()),
            "sender_id": user_id,
            "receiver_id": observer_id,
            "content": content.strip(),
            "timestamp": datetime.now().isoformat(),
            "read": False
        }

        supabase.table('messages').insert(message_data).execute()
        flash('Message sent successfully!', 'success')

    except Exception as e:
        flash(f'Error sending message: {str(e)}', 'error')

    return redirect(url_for('parent.messages'))


@parent_bp.route('/goals')
@login_required
@parent_required
def goals():
    child_id = session.get('child_id')

    if not child_id:
        flash('No child assigned to your account.', 'warning')
        return render_template('parent/goals.html', goals=[], goal_alignments={})

    try:
        goals = get_goals_by_child(child_id)

        # Get goal alignments
        supabase = get_supabase_client()
        goal_alignments = {}
        for goal in goals:
            alignments = supabase.table('goal_alignments').select("*").eq('goal_id', goal['id']).execute().data
            goal_alignments[goal['id']] = alignments

        return render_template('parent/goals.html', goals=goals, goal_alignments=goal_alignments)
    except Exception as e:
        flash(f'Error loading goals: {str(e)}', 'error')
        return render_template('parent/goals.html', goals=[], goal_alignments={})


@parent_bp.route('/get_goals_count')
@login_required
@parent_required
def get_goals_count():
    child_id = session.get('child_id')

    if not child_id:
        return jsonify({'success': False, 'count': 0})

    try:
        goals = get_goals_by_child(child_id)
        active_goals = [g for g in goals if g.get('status') == 'active']
        return jsonify({'success': True, 'count': len(active_goals)})
    except Exception as e:
        return jsonify({'success': False, 'count': 0})


@parent_bp.route('/monthly_report')
@login_required
@parent_required
def monthly_report():
    child_id = session.get('child_id')
    year = request.args.get('year', datetime.now().year, type=int)
    month = request.args.get('month', datetime.now().month, type=int)

    if not child_id:
        flash('No child assigned to your account.', 'warning')
        return render_template('parent/monthly_report.html', report_data=None)

    try:
        supabase = get_supabase_client()
        report_generator = MonthlyReportGenerator(supabase)

        # Get data
        observations = report_generator.get_month_data(child_id, year, month)
        goal_progress = report_generator.get_goal_progress(child_id, year, month)
        strength_counts = report_generator.get_strength_areas(observations)
        development_counts = report_generator.get_development_areas(observations)

        # Generate summary
        summary = report_generator.generate_monthly_summary(observations, goal_progress)

        report_data = {
            'summary': summary,
            'observations_count': len(observations),
            'goals_count': len(goal_progress),
            'strengths': strength_counts,
            'development': development_counts,
            'year': year,
            'month': month
        }

        return render_template('parent/monthly_report.html', report_data=report_data)
    except Exception as e:
        flash(f'Error generating monthly report: {str(e)}', 'error')
        return render_template('parent/monthly_report.html', report_data=None)


@parent_bp.route('/download_monthly_report')
@login_required
@parent_required
def download_monthly_report():
    child_id = session.get('child_id')
    year = request.args.get('year', datetime.now().year, type=int)
    month = request.args.get('month', datetime.now().month, type=int)
    filetype = request.args.get('filetype', 'docx')  # 'docx' or 'pdf'

    if not child_id:
        flash('No child assigned to your account.', 'warning')
        return redirect(url_for('parent.dashboard'))

    try:
        supabase = get_supabase_client()
        report_generator = MonthlyReportGenerator(supabase)

        # Get data
        observations = report_generator.get_month_data(child_id, year, month)
        goal_progress = report_generator.get_goal_progress(child_id, year, month)
        strength_counts = report_generator.get_strength_areas(observations)
        development_counts = report_generator.get_development_areas(observations)

        # Generate JSON summary for narrative/analytics
        child_data = supabase.table('children').select("name").eq('id', child_id).execute().data
        child_name = child_data[0]['name'] if child_data else 'Child'
        summary_json = report_generator.generate_monthly_summary_json_format(
            observations, goal_progress, child_name, year, month
        )
        if isinstance(summary_json, str):
            import json as _json
            try:
                summary_json = _json.loads(summary_json)
            except Exception:
                flash('Could not generate a valid summary for this report. Please check if there are enough daily reports for the selected month.', 'error')
                return redirect(url_for('parent.monthly_report'))

        import calendar
        month_name = calendar.month_name[month]
        filename_base = f"{child_name}_Progress_Report_{month_name}_{year}"

        if filetype == 'pdf':
            pdf_buffer = report_generator.generate_monthly_pdf_report(
                observations, goal_progress, strength_counts, development_counts, summary_json
            )
            filename = filename_base + '.pdf'
            mimetype = 'application/pdf'
            return send_file(
                pdf_buffer,
                as_attachment=True,
                download_name=filename,
                mimetype=mimetype
            )
        else:
            docx_buffer = report_generator.generate_monthly_docx_report(
                observations, goal_progress, strength_counts, development_counts, summary_json
            )
            filename = filename_base + '.docx'
            mimetype = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            return send_file(
                docx_buffer,
                as_attachment=True,
                download_name=filename,
                mimetype=mimetype
            )
    except Exception as e:
        flash(f'Error downloading report: {str(e)}. If you see no curiosity/growth charts, it may be due to missing scores in daily reports.', 'error')
        return redirect(url_for('parent.monthly_report'))


@parent_bp.route('/download_report/<report_id>')
@login_required
@parent_required
def download_report(report_id):
    try:
        child_id = session.get('child_id')

        if not child_id:
            flash('No child assigned to your account.', 'warning')
            return redirect(url_for('parent.dashboard'))

        supabase = get_supabase_client()

        # Get the specific report and verify it belongs to this parent's child
        report_data = supabase.table('observations').select("*").eq('id', report_id).eq('student_id',
                                                                                        child_id).execute().data

        if not report_data:
            flash('Report not found or access denied', 'error')
            return redirect(url_for('parent.reports'))

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
            formatted_report = report.get('observations', 'No report content available')

        # Create Word document
        extractor = ObservationExtractor()
        doc_buffer = extractor.create_word_document_with_emojis(formatted_report)

        # Create filename
        student_name = report.get('student_name', 'Student')
        clean_name = re.sub(r'[^\w\s-]', '', student_name).strip()
        clean_name = re.sub(r'[-\s]+', '_', clean_name)
        date = report.get('date', datetime.now().strftime('%Y-%m-%d'))
        filename = f"observation_report_{clean_name}_{date}.docx"

        return send_file(
            doc_buffer,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )

    except Exception as e:
        flash(f'Error downloading report: {str(e)}', 'error')
        return redirect(url_for('parent.reports'))


@parent_bp.route('/download_pdf/<report_id>')
@login_required
@parent_required
def download_pdf(report_id):
    try:
        child_id = session.get('child_id')

        if not child_id:
            flash('No child assigned to your account.', 'warning')
            return redirect(url_for('parent.dashboard'))

        supabase = get_supabase_client()

        # Get the specific report and verify it belongs to this parent's child
        report_data = supabase.table('observations').select("*").eq('id', report_id).eq('student_id',
                                                                                        child_id).execute().data

        if not report_data:
            flash('Report not found or access denied', 'error')
            return redirect(url_for('parent.reports'))

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
            formatted_report = report.get('observations', 'No report content available')

        # Create PDF
        extractor = ObservationExtractor()
        pdf_buffer = extractor.create_pdf_alternative(formatted_report)

        # Create filename
        student_name = report.get('student_name', 'Student')
        clean_name = re.sub(r'[^\w\s-]', '', student_name).strip()
        clean_name = re.sub(r'[-\s]+', '_', clean_name)
        date = report.get('date', datetime.now().strftime('%Y-%m-%d'))
        filename = f"observation_report_{clean_name}_{date}.pdf"

        return send_file(
            pdf_buffer,
            as_attachment=True,
            download_name=filename,
            mimetype='application/pdf'
        )

    except Exception as e:
        flash(f'Error downloading PDF: {str(e)}', 'error')
        return redirect(url_for('parent.reports'))


@parent_bp.route('/get_messages_api/<observer_id>')
@login_required
@parent_required
def get_messages_api(observer_id):
    parent_id = session.get('user_id')
    try:
        supabase = get_supabase_client()

        # Get messages in both directions using separate queries
        messages1 = supabase.table('messages').select("*") \
            .eq('sender_id', parent_id).eq('receiver_id', observer_id) \
            .order('timestamp', desc=False).execute().data

        messages2 = supabase.table('messages').select("*") \
            .eq('sender_id', observer_id).eq('receiver_id', parent_id) \
            .order('timestamp', desc=False).execute().data

        # Combine and sort messages
        messages = sorted((messages1 or []) + (messages2 or []), key=lambda m: m['timestamp'])

        return jsonify(messages)
    except Exception as e:
        return jsonify([])


@parent_bp.route('/send_message_api', methods=['POST'])
@login_required
@parent_required
def send_message_api():
    parent_id = session.get('user_id')
    observer_id = request.form.get('receiver_id')
    content = request.form.get('content')

    if not observer_id or not content:
        return jsonify({'success': False, 'error': 'Missing data'})

    try:
        supabase = get_supabase_client()
        message_data = {
            "id": str(uuid.uuid4()),
            "sender_id": parent_id,
            "receiver_id": observer_id,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "read": False
        }
        supabase.table('messages').insert(message_data).execute()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
