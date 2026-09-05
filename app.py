import os
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, jsonify
from datetime import datetime
from uuid import uuid4
from io import BytesIO
import bcrypt
import boto3
from functools import wraps
from collections import defaultdict

load_dotenv()

app = Flask(__name__, template_folder='templates')
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'dev-secret-key')
app.config['AWS_REGION'] = os.getenv('AWS_REGION', 'us-east-1')
app.config['S3_INPUT_BUCKET'] = os.getenv('S3_INPUT_BUCKET')
app.config['S3_OUTPUT_BUCKET'] = os.getenv('S3_OUTPUT_BUCKET')
app.config['USERS_TABLE'] = os.getenv('USERS_TABLE', 'users')
app.config['DOCUMENTS_TABLE'] = os.getenv('DOCUMENTS_TABLE', 'doc')

s3_client = boto3.client('s3', region_name=app.config['AWS_REGION'])
dynamodb = boto3.resource('dynamodb', region_name=app.config['AWS_REGION'])

def get_users_table():
    return dynamodb.Table(app.config['USERS_TABLE'])

def get_documents_table():
    return dynamodb.Table(app.config['DOCUMENTS_TABLE'])

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'email' not in session:
            flash('Please log in first.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/health')
def health():
    return {'status': 'ok'}, 200

@app.route('/')
def index():
    if 'email' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        if not email or not password:
            flash('Email and password are required.', 'danger')
            return redirect(url_for('register'))

        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return redirect(url_for('register'))

        users_table = get_users_table()
        try:
            existing = users_table.get_item(Key={'email': email})
            if 'Item' in existing:
                flash('Email already registered.', 'danger')
                return redirect(url_for('register'))

            hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            users_table.put_item(Item={
                'email': email,
                'password_hash': hashed_password
            })
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            flash(f'Registration failed: {str(e)}', 'danger')
            return redirect(url_for('register'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')

        if not email or not password:
            flash('Email and password are required.', 'danger')
            return redirect(url_for('login'))

        users_table = get_users_table()
        try:
            response = users_table.get_item(Key={'email': email})
            if 'Item' not in response:
                flash('Invalid email or password.', 'danger')
                return redirect(url_for('login'))

            user = response['Item']
            if not bcrypt.checkpw(password.encode('utf-8'), user['password_hash'].encode('utf-8')):
                flash('Invalid email or password.', 'danger')
                return redirect(url_for('login'))

            session['email'] = email
            flash(f'Welcome, {email}!', 'success')
            return redirect(url_for('dashboard'))
        except Exception as e:
            flash(f'Login failed: {str(e)}', 'danger')
            return redirect(url_for('login'))

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html', email=session['email'])

@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    if request.method == 'POST':
        email = session['email']
        file = request.files.get('file')
        contract_type = request.form.get('contract_type', '').strip()
        client_name = request.form.get('client_name', '').strip()

        if not file or file.filename == '':
            flash('No file selected.', 'danger')
            return redirect(url_for('upload'))

        if not contract_type or not client_name:
            flash('Contract type and client name are required.', 'danger')
            return redirect(url_for('upload'))

        try:
            filename = file.filename
            document_id = str(uuid4())
            s3_key = f"documents/{email}/{document_id}_{filename}"

            s3_client.upload_fileobj(
                file.stream,
                app.config['S3_INPUT_BUCKET'],
                s3_key,
                ExtraArgs={'ContentType': file.content_type or 'application/octet-stream'}
            )

            documents_table = get_documents_table()
            documents_table.put_item(Item={
                'document_id': document_id,
                'owner_email': email,
                'contract_type': contract_type,
                'client_name': client_name,
                's3_key': s3_key,
                'uploaded_at': datetime.utcnow().isoformat(),
                'status': 'Uploaded',
                'filename': filename
            })

            flash(f'Document "{filename}" uploaded successfully.', 'success')
            return redirect(url_for('list_documents'))
        except Exception as e:
            flash(f'Upload failed: {str(e)}', 'danger')
            return redirect(url_for('upload'))

    return render_template('upload.html')

@app.route('/documents', methods=['GET'])
@login_required
def list_documents():
    email = session['email']
    documents_table = get_documents_table()
    contract_type_filter = request.args.get('contract_type', '').strip()
    client_name_filter = request.args.get('client_name', '').strip()

    try:
        response = documents_table.scan(
            FilterExpression='owner_email = :email',
            ExpressionAttributeValues={':email': email}
        )
        documents = response.get('Items', [])

        if contract_type_filter:
            documents = [d for d in documents if d.get('contract_type') == contract_type_filter]

        if client_name_filter:
            documents = [d for d in documents if client_name_filter.lower() in d.get('client_name', '').lower()]

        documents.sort(key=lambda d: d.get('uploaded_at', ''), reverse=True)

        return render_template('documents.html', documents=documents, contract_type_filter=contract_type_filter, client_name_filter=client_name_filter)
    except Exception as e:
        flash(f'Failed to load documents: {str(e)}', 'danger')
        return render_template('documents.html', documents=[], contract_type_filter='', client_name_filter='')

@app.route('/documents/<document_id>/view')
@login_required
def view_document(document_id):
    email = session['email']
    documents_table = get_documents_table()

    try:
        response = documents_table.get_item(Key={'document_id': document_id})
        if 'Item' not in response:
            flash('Document not found.', 'danger')
            return redirect(url_for('list_documents'))

        doc = response['Item']
        if doc['owner_email'] != email:
            flash('Unauthorized.', 'danger')
            return redirect(url_for('list_documents'))

        file_obj = s3_client.get_object(Bucket=app.config['S3_INPUT_BUCKET'], Key=doc['s3_key'])
        file_data = file_obj['Body'].read()

        return send_file(
            BytesIO(file_data),
            mimetype=file_obj.get('ContentType', 'application/octet-stream'),
            as_attachment=True,
            download_name=doc.get('filename', 'document')
        )
    except Exception as e:
        flash(f'Failed to retrieve document: {str(e)}', 'danger')
        return redirect(url_for('list_documents'))

@app.route('/analytics')
@login_required
def analytics():
    return render_template('analytics.html')

@app.route('/api/analytics/data')
@login_required
def analytics_data():
    email = session['email']
    documents_table = get_documents_table()

    try:
        response = documents_table.scan(
            FilterExpression='owner_email = :email',
            ExpressionAttributeValues={':email': email}
        )
        documents = response.get('Items', [])

        contract_counts = {}
        monthly_counts = {}

        for doc in documents:
            contract_type = doc.get('contract_type', 'Unknown')
            contract_counts[contract_type] = contract_counts.get(contract_type, 0) + 1

            uploaded_at = doc.get('uploaded_at', '')
            if uploaded_at:
                try:
                    date_obj = datetime.fromisoformat(uploaded_at)
                    month_key = date_obj.strftime('%Y-%m')
                    monthly_counts[month_key] = monthly_counts.get(month_key, 0) + 1
                except:
                    pass

        return jsonify({
            'contract_types': {
                'labels': list(contract_counts.keys()),
                'data': list(contract_counts.values())
            },
            'monthly': {
                'labels': sorted(monthly_counts.keys()),
                'data': [monthly_counts[k] for k in sorted(monthly_counts.keys())]
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
