import os
import json
import time
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, jsonify
from datetime import datetime
from uuid import uuid4
from io import BytesIO
import bcrypt
import boto3
from functools import wraps
from collections import defaultdict
import re
import requests
from PyPDF2 import PdfReader
from docx import Document as DocxDocument

load_dotenv()

app = Flask(__name__, template_folder='templates', static_folder='static')
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'dev-secret-key')
app.config['AWS_REGION'] = os.getenv('AWS_REGION', 'us-east-1')
app.config['S3_INPUT_BUCKET'] = os.getenv('S3_INPUT_BUCKET')
app.config['S3_OUTPUT_BUCKET'] = os.getenv('S3_OUTPUT_BUCKET')
app.config['USERS_TABLE'] = os.getenv('USERS_TABLE', 'users')
app.config['DOCUMENTS_TABLE'] = os.getenv('DOCUMENTS_TABLE', 'doc')
app.config['GEMINI_API_KEY'] = os.getenv('GEMINI_API_KEY')

s3_client = boto3.client('s3', region_name=app.config['AWS_REGION'])
dynamodb = boto3.resource('dynamodb', region_name=app.config['AWS_REGION'])

def get_users_table():
    return dynamodb.Table(app.config['USERS_TABLE'])

def get_documents_table():
    return dynamodb.Table(app.config['DOCUMENTS_TABLE'])

def is_valid_client_name(name):
    """Validate client name - only letters, numbers, spaces, hyphens, apostrophes"""
    return bool(re.match(r"^[a-zA-Z0-9\s\-']+$", name.strip()))

# Max characters of document text sent to Gemini (keeps prompt + cost bounded)
MAX_ANALYSIS_CHARS = 15000

def extract_document_text(file_bytes, filename):
    """Extract plain text from a PDF or DOCX file for Gemini analysis.

    PDF parsing via PyPDF2 [1] and DOCX parsing via python-docx [2].
    [1] https://pypdf2.readthedocs.io/
    [2] https://python-docx.readthedocs.io/
    """
    extension = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''

    if extension == 'pdf':
        reader = PdfReader(BytesIO(file_bytes))
        text = '\n'.join(page.extract_text() or '' for page in reader.pages)
    elif extension == 'docx':
        doc = DocxDocument(BytesIO(file_bytes))
        text = '\n'.join(p.text for p in doc.paragraphs)
    else:
        raise ValueError(f'Text extraction not supported for .{extension} files')

    return text.strip()[:MAX_ANALYSIS_CHARS]

GEMINI_ENDPOINT = (
    'https://generativelanguage.googleapis.com/v1beta/models/'
    'gemini-3.6-flash:generateContent'
)

class GeminiRateLimitError(Exception):
    pass

class GeminiAuthError(Exception):
    pass

def analyze_document_with_gemini(document_text, max_retries=2):
    """Send document text to Google Gemini and return structured legal analysis.

    Uses the Gemini REST API with a JSON-constrained response schema [1].
    [1] https://ai.google.dev/gemini-api/docs/structured-output
    """
    if not app.config['GEMINI_API_KEY']:
        raise RuntimeError('GEMINI_API_KEY is not configured')

    prompt = (
        "You are a legal document analyzer. Analyze the provided legal document and "
        "extract: key parties/signatories, document type, important dates and deadlines, "
        "identified risks or problematic clauses, and a 2-3 sentence summary. "
        "Respond ONLY in JSON with keys: parties (array), doc_type (string), "
        "dates (array), risks (array), summary (string), risk_level (one of 'low', 'medium', 'high').\n\n"
        f"Document content:\n\n{document_text}"
    )

    payload = {
        'contents': [{'parts': [{'text': prompt}]}],
        'generationConfig': {
            'temperature': 0.2,
            'responseMimeType': 'application/json'
        }
    }

    for attempt in range(max_retries + 1):
        response = requests.post(
            GEMINI_ENDPOINT,
            params={'key': app.config['GEMINI_API_KEY']},
            json=payload,
            timeout=25
        )

        if response.status_code == 429:
            if attempt < max_retries:
                time.sleep(2 ** attempt)
                continue
            raise GeminiRateLimitError('Gemini rate limit reached')

        if response.status_code in (401, 403):
            raise GeminiAuthError(response.text)

        if response.status_code in (500, 502, 503, 504):
            if attempt < max_retries:
                time.sleep(2 ** attempt)
                continue

        response.raise_for_status()
        data = response.json()
        text = data['candidates'][0]['content']['parts'][0]['text']
        return json.loads(text)

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

@app.route('/test-upload-form')
def test_upload_form():
    """Serve test upload form"""
    return render_template('test_upload.html')

@app.route('/api/debug/test-upload', methods=['POST'])
def debug_test_upload():
    """Debug endpoint to test upload without UI"""
    try:
        file = request.files.get('file')
        contract_type = request.form.get('contract_type', '').strip()
        client_name = request.form.get('client_name', '').strip()
        email = session.get('email', 'test@example.com')

        # Validation checks
        if not file:
            return {'error': 'No file provided'}, 400

        if not contract_type:
            return {'error': 'contract_type required'}, 400

        if not client_name:
            return {'error': 'client_name required'}, 400

        if not is_valid_client_name(client_name):
            return {'error': 'client_name can only contain letters, numbers, spaces, hyphens, and apostrophes'}, 400

        # Debug values
        debug_info = {
            'email': email,
            'file_name': file.filename,
            'file_content_type': file.content_type,
            'file_content_type_type': type(file.content_type).__name__,
            'contract_type': contract_type,
            'client_name': client_name,
            'file_size': file.seek(0, 2),
        }
        file.seek(0)

        # Try to upload
        filename = file.filename
        document_id = str(uuid4())
        s3_key = f"documents/{email}/{document_id}_{filename}"

        s3_client.upload_fileobj(
            file.stream,
            app.config['S3_INPUT_BUCKET'],
            s3_key,
            ExtraArgs={'ContentType': str(file.content_type) if file.content_type else 'application/octet-stream'}
        )

        documents_table = get_documents_table()
        composite_key = f"{email}#{document_id}"
        uploaded_at = datetime.utcnow().isoformat()

        document_data = {
            'email': str(composite_key),
            'document_id': str(document_id),
            'user_email': str(email),
            'contract_type': str(contract_type) if contract_type else 'Unknown',
            'client_name': str(client_name) if client_name else 'Unknown',
            's3_key': str(s3_key),
            'uploaded_at': str(uploaded_at),
            'status': 'Uploaded',
            'filename': str(filename)
        }

        documents_table.put_item(Item=document_data)

        return {
            'success': True,
            'message': 'Document uploaded successfully',
            'debug': debug_info,
            'document_id': document_id
        }, 200

    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        return {
            'error': str(e),
            'traceback': error_trace,
            'type': type(e).__name__
        }, 500

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

        # Validation
        if not email or not password:
            flash('Email and password are required.', 'danger')
            return redirect(url_for('register'))

        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'danger')
            return redirect(url_for('register'))

        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return redirect(url_for('register'))

        if '@' not in email:
            flash('Please enter a valid email address.', 'danger')
            return redirect(url_for('register'))

        users_table = get_users_table()
        try:
            existing = users_table.get_item(Key={'email': email})
            if 'Item' in existing:
                flash('Email already registered. Please login or use a different email.', 'danger')
                return redirect(url_for('register'))

            hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            users_table.put_item(Item={
                'email': email,
                'password_hash': hashed_password
            })
            print(f"[REGISTER] User registered: {email}")
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            print(f"[REGISTER ERROR] {str(e)}")
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
            print(f"[LOGIN] User logged in: {email}")
            print(f"[SESSION] Email set to: {session.get('email')}")
            flash(f'Welcome, {email}!', 'success')
            return redirect(url_for('dashboard'))
        except Exception as e:
            print(f"[LOGIN ERROR] {str(e)}")
            flash(f'Login failed: {str(e)}', 'danger')
            return redirect(url_for('login'))

    return render_template('login.html')

@app.route('/logout')
def logout():
    email = session.get('email')
    session.clear()
    print(f"[LOGOUT] User logged out: {email}")
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    email = session.get('email')
    print(f"[DASHBOARD] Accessed by: {email}")
    return render_template('dashboard.html', email=email)

@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    email = session.get('email')

    # DEBUG: Check if email exists
    if not email:
        flash('Error: Session email not found. Please log in again.', 'danger')
        return redirect(url_for('login'))

    if request.method == 'POST':
        file = request.files.get('file')
        contract_type = request.form.get('contract_type', '').strip()
        client_name = request.form.get('client_name', '').strip()

        # Validation
        if not file or file.filename == '':
            flash('No file selected.', 'danger')
            return redirect(url_for('upload'))

        if not contract_type:
            flash('Contract type is required.', 'danger')
            return redirect(url_for('upload'))

        if not client_name:
            flash('Client name is required.', 'danger')
            return redirect(url_for('upload'))

        if not is_valid_client_name(client_name):
            flash('Client name can only contain letters, numbers, spaces, hyphens, and apostrophes.', 'danger')
            return redirect(url_for('upload'))

        # Check file type
        allowed_extensions = {'pdf', 'png', 'jpg', 'jpeg', 'docx'}
        if not file.filename or '.' not in file.filename or file.filename.rsplit('.', 1)[1].lower() not in allowed_extensions:
            flash('Invalid file type. Only PDF, PNG, JPG, JPEG, DOCX allowed.', 'danger')
            return redirect(url_for('upload'))

        # Check file size (50MB max)
        file.seek(0, 2)
        file_size = file.tell()
        file.seek(0)
        if file_size > 50 * 1024 * 1024:
            flash('File too large. Maximum size is 50MB.', 'danger')
            return redirect(url_for('upload'))

        try:
            filename = file.filename
            document_id = str(uuid4())
            s3_key = f"documents/{email}/{document_id}_{filename}"

            print(f"[UPLOAD S3] Uploading to: {s3_key}")

            s3_client.upload_fileobj(
                file.stream,
                app.config['S3_INPUT_BUCKET'],
                s3_key,
                ExtraArgs={'ContentType': str(file.content_type) if file.content_type else 'application/octet-stream'}
            )

            documents_table = get_documents_table()

            # Use composite key: email#document_id to support multiple documents per user
            composite_key = f"{email}#{document_id}"
            uploaded_at = datetime.utcnow().isoformat()

            document_data = {
                'email': str(composite_key),
                'document_id': str(document_id),
                'user_email': str(email),
                'contract_type': str(contract_type) if contract_type else 'Unknown',
                'client_name': str(client_name) if client_name else 'Unknown',
                's3_key': str(s3_key),
                'uploaded_at': str(uploaded_at),
                'status': 'Uploaded',
                'filename': str(filename)
            }

            print(f"[UPLOAD DB] Saving document: {document_data}")
            documents_table.put_item(Item=document_data)

            print(f"[UPLOAD SUCCESS] Document uploaded by: {email}")
            flash(f'Document "{filename}" uploaded successfully.', 'success')
            return redirect(url_for('list_documents'))
        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            print(f"[UPLOAD ERROR] {str(e)}")
            print(f"[UPLOAD TRACEBACK] {error_trace}")
            flash(f'Upload failed: {str(e)}', 'danger')
            return redirect(url_for('upload'))

    return render_template('upload.html')

@app.route('/api/client-names', methods=['GET'])
@login_required
def get_client_names():
    """Get unique client names for current user (for autocomplete)"""
    email = session.get('email')
    documents_table = get_documents_table()

    try:
        # Scan for all documents by this user
        response = documents_table.scan(
            FilterExpression='user_email = :email',
            ExpressionAttributeValues={':email': email},
            ProjectionExpression='client_name'
        )

        # Extract unique client names
        client_names = set()
        for item in response.get('Items', []):
            if item.get('client_name') and item['client_name'] != 'Unknown':
                client_names.add(item['client_name'])

        # Handle pagination
        while 'LastEvaluatedKey' in response:
            response = documents_table.scan(
                FilterExpression='user_email = :email',
                ExpressionAttributeValues={':email': email},
                ProjectionExpression='client_name',
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            for item in response.get('Items', []):
                if item.get('client_name') and item['client_name'] != 'Unknown':
                    client_names.add(item['client_name'])

        return jsonify(sorted(list(client_names)))
    except Exception as e:
        print(f"[GET CLIENT NAMES ERROR] {str(e)}")
        return jsonify([]), 500

@app.route('/documents', methods=['GET'])
@login_required
def list_documents():
    email = session.get('email')
    print(f"[LIST DOCS] Accessed by: {email}")

    documents_table = get_documents_table()
    contract_type_filter = request.args.get('contract_type', '').strip()
    client_name_filter = request.args.get('client_name', '').strip()

    try:
        # Fetch all documents for this user (filter by user_email)
        all_documents = []
        last_evaluated_key = None

        print(f"[LIST DOCS] Starting fetch for email: {email}")

        while True:
            scan_kwargs = {
                'FilterExpression': 'user_email = :email',
                'ExpressionAttributeValues': {':email': email},
                'Limit': 100
            }

            if last_evaluated_key:
                scan_kwargs['ExclusiveStartKey'] = last_evaluated_key

            response = documents_table.scan(**scan_kwargs)
            items = response.get('Items', [])
            all_documents.extend(items)

            print(f"[LIST DOCS] Fetched {len(items)} items, total: {len(all_documents)}")

            last_evaluated_key = response.get('LastEvaluatedKey')
            if not last_evaluated_key:
                print(f"[LIST DOCS] Pagination complete")
                break

        documents = all_documents
        print(f"[LIST DOCS] Found {len(documents)} documents for {email}")

        if contract_type_filter:
            documents = [d for d in documents if d.get('contract_type') == contract_type_filter]

        if client_name_filter:
            documents = [d for d in documents if client_name_filter.lower() in d.get('client_name', '').lower()]

        documents.sort(key=lambda d: d.get('uploaded_at', ''), reverse=True)

        return render_template('documents.html', documents=documents, contract_type_filter=contract_type_filter, client_name_filter=client_name_filter)
    except Exception as e:
        print(f"[LIST DOCS ERROR] {str(e)}")
        flash(f'Failed to load documents: {str(e)}', 'danger')
        return render_template('documents.html', documents=[], contract_type_filter='', client_name_filter='')

@app.route('/documents/<document_id>/view')
@login_required
def view_document(document_id):
    email = session.get('email')
    print(f"[VIEW DOC] Email: {email}, Document: {document_id}")
    
    documents_table = get_documents_table()

    try:
        composite_key = f"{email}#{document_id}"
        response = documents_table.get_item(Key={'email': composite_key, 'document_id': document_id})
        if 'Item' not in response:
            print(f"[VIEW DOC ERROR] Document not found: {document_id}")
            flash('Document not found.', 'danger')
            return redirect(url_for('list_documents'))

        doc = response['Item']

        # Security check: verify ownership
        doc_owner = doc.get('user_email')
        print(f"[VIEW DOC] Document owner: {doc_owner}, Current user: {email}")

        if doc_owner != email:
            print(f"[VIEW DOC ERROR] Unauthorized access attempt by {email} for doc owned by {doc_owner}")
            flash('Unauthorized.', 'danger')
            return redirect(url_for('list_documents'))

        file_obj = s3_client.get_object(Bucket=app.config['S3_INPUT_BUCKET'], Key=doc['s3_key'])
        file_data = file_obj['Body'].read()

        print(f"[VIEW DOC SUCCESS] File downloaded for {email}")

        return send_file(
            BytesIO(file_data),
            mimetype=file_obj.get('ContentType', 'application/octet-stream'),
            as_attachment=True,
            download_name=doc.get('filename', 'document')
        )
    except Exception as e:
        print(f"[VIEW DOC ERROR] {str(e)}")
        flash(f'Failed to retrieve document: {str(e)}', 'danger')
        return redirect(url_for('list_documents'))

@app.route('/api/analyze-document', methods=['POST'])
@login_required
def analyze_document():
    """Extract text from a document and run Google Gemini legal analysis on it."""
    email = session.get('email')
    document_id = request.json.get('document_id') if request.is_json else request.form.get('document_id')

    if not document_id:
        return jsonify({'error': 'document_id is required'}), 400

    if not app.config['GEMINI_API_KEY']:
        return jsonify({'error': 'Gemini API key is not configured on the server'}), 503

    documents_table = get_documents_table()
    composite_key = f"{email}#{document_id}"

    try:
        response = documents_table.get_item(Key={'email': composite_key, 'document_id': document_id})
        if 'Item' not in response:
            return jsonify({'error': 'Document not found'}), 404

        doc = response['Item']
        if doc.get('user_email') != email:
            return jsonify({'error': 'Unauthorized'}), 403

        documents_table.update_item(
            Key={'email': composite_key, 'document_id': document_id},
            UpdateExpression='SET analysis_status = :status',
            ExpressionAttributeValues={':status': 'pending'}
        )

        file_obj = s3_client.get_object(Bucket=app.config['S3_INPUT_BUCKET'], Key=doc['s3_key'])
        file_bytes = file_obj['Body'].read()

        try:
            document_text = extract_document_text(file_bytes, doc.get('filename', ''))
        except ValueError as e:
            documents_table.update_item(
                Key={'email': composite_key, 'document_id': document_id},
                UpdateExpression='SET analysis_status = :status',
                ExpressionAttributeValues={':status': 'failed'}
            )
            return jsonify({'error': str(e)}), 400

        if not document_text:
            documents_table.update_item(
                Key={'email': composite_key, 'document_id': document_id},
                UpdateExpression='SET analysis_status = :status',
                ExpressionAttributeValues={':status': 'failed'}
            )
            return jsonify({'error': 'No extractable text found in document'}), 400

        analysis = analyze_document_with_gemini(document_text)

        documents_table.update_item(
            Key={'email': composite_key, 'document_id': document_id},
            UpdateExpression='SET analysis = :analysis, analysis_status = :status',
            ExpressionAttributeValues={':analysis': json.dumps(analysis), ':status': 'completed'}
        )

        print(f"[ANALYZE DOC SUCCESS] {document_id} for {email}")
        return jsonify({'success': True, 'analysis': analysis}), 200

    except GeminiAuthError:
        print(f"[ANALYZE DOC ERROR] Invalid Gemini API key")
        documents_table.update_item(
            Key={'email': composite_key, 'document_id': document_id},
            UpdateExpression='SET analysis_status = :status',
            ExpressionAttributeValues={':status': 'failed'}
        )
        return jsonify({'error': 'Gemini API key is invalid. Please check server configuration.'}), 502
    except GeminiRateLimitError:
        print(f"[ANALYZE DOC ERROR] Gemini rate limit exceeded")
        documents_table.update_item(
            Key={'email': composite_key, 'document_id': document_id},
            UpdateExpression='SET analysis_status = :status',
            ExpressionAttributeValues={':status': 'failed'}
        )
        return jsonify({'error': 'Gemini rate limit reached. Please try again shortly.'}), 429
    except Exception as e:
        print(f"[ANALYZE DOC ERROR] {str(e)}")
        try:
            documents_table.update_item(
                Key={'email': composite_key, 'document_id': document_id},
                UpdateExpression='SET analysis_status = :status',
                ExpressionAttributeValues={':status': 'failed'}
            )
        except Exception:
            pass
        return jsonify({'error': f'Analysis failed: {str(e)}'}), 500

@app.route('/documents/<document_id>/analysis')
@login_required
def view_analysis(document_id):
    """Render the analysis results page for a document."""
    email = session.get('email')
    documents_table = get_documents_table()
    composite_key = f"{email}#{document_id}"

    try:
        response = documents_table.get_item(Key={'email': composite_key, 'document_id': document_id})
        if 'Item' not in response:
            flash('Document not found.', 'danger')
            return redirect(url_for('list_documents'))

        doc = response['Item']
        if doc.get('user_email') != email:
            flash('Unauthorized.', 'danger')
            return redirect(url_for('list_documents'))

        analysis = json.loads(doc['analysis']) if doc.get('analysis') else None
        return render_template('analysis.html', doc=doc, analysis=analysis)
    except Exception as e:
        print(f"[VIEW ANALYSIS ERROR] {str(e)}")
        flash(f'Failed to load analysis: {str(e)}', 'danger')
        return redirect(url_for('list_documents'))

@app.route('/analytics')
@login_required
def analytics():
    email = session.get('email')
    print(f"[ANALYTICS] Accessed by: {email}")
    return render_template('analytics.html')

@app.route('/api/analytics/data')
@login_required
def analytics_data():
    email = session.get('email')
    print(f"[ANALYTICS API] Data requested by: {email}")

    documents_table = get_documents_table()

    try:
        # Fetch all documents with pagination
        all_documents = []
        last_evaluated_key = None

        while True:
            scan_kwargs = {
                'FilterExpression': 'user_email = :email',
                'ExpressionAttributeValues': {':email': email},
                'Limit': 100
            }

            if last_evaluated_key:
                scan_kwargs['ExclusiveStartKey'] = last_evaluated_key

            response = documents_table.scan(**scan_kwargs)
            all_documents.extend(response.get('Items', []))

            last_evaluated_key = response.get('LastEvaluatedKey')
            if not last_evaluated_key:
                break

        documents = all_documents
        print(f"[ANALYTICS API] Found {len(documents)} documents")

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
        print(f"[ANALYTICS API ERROR] {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.errorhandler(404)
def page_not_found(e):
    print(f"[404 ERROR] Page not found")
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(e):
    print(f"[500 ERROR] Internal server error")
    return render_template('404.html'), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
