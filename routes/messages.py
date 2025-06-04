from flask import Blueprint, request, jsonify, session
from flask_login import login_required
from models.database import get_supabase_client

messages_bp = Blueprint('messages', __name__)

def get_conversation(user_id, other_user_id):
    supabase = get_supabase_client()
    # Fetch messages both ways, sorted oldest first
    messages = supabase.table('messages') \
        .select("*") \
        .or_(
            f"(sender_id.eq.{user_id},receiver_id.eq.{other_user_id})",
            f"(sender_id.eq.{other_user_id},receiver_id.eq.{user_id})"
        ) \
        .order('timestamp', desc=False) \
        .execute().data
    return messages

# API to get messages between two users
@messages_bp.route('/get_conversation/<other_user_id>')
@login_required
def get_conversation_route(other_user_id):
    user_id = session.get('user_id')
    messages = get_conversation(user_id, other_user_id)
    return jsonify(messages)

# API to send a message
@messages_bp.route('/send_message', methods=['POST'])
@login_required
def send_message():
    user_id = session.get('user_id')
    receiver_id = request.form.get('receiver_id')
    content = request.form.get('content')

    if not receiver_id or not content:
        return jsonify({'success': False, 'error': 'Missing data'}), 400

    supabase = get_supabase_client()
    from uuid import uuid4
    from datetime import datetime

    message_data = {
        "id": str(uuid4()),
        "sender_id": user_id,
        "receiver_id": receiver_id,
        "content": content,
        "timestamp": datetime.now().isoformat(),
        "read": False
    }
    supabase.table('messages').insert(message_data).execute()
    return jsonify({'success': True})
