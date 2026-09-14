import boto3
import json
import os
import time
from io import BytesIO
from datetime import datetime

import requests
from PyPDF2 import PdfReader
from docx import Document as DocxDocument

s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')

DOCUMENTS_TABLE = os.getenv('DOCUMENTS_TABLE', 'doc')
S3_INPUT_BUCKET = os.getenv('S3_INPUT_BUCKET')
S3_OUTPUT_BUCKET = os.getenv('S3_OUTPUT_BUCKET')
AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

MAX_ANALYSIS_CHARS = 15000
GEMINI_ENDPOINT = (
    'https://generativelanguage.googleapis.com/v1beta/models/'
    'gemini-3.6-flash:generateContent'
)


class GeminiRateLimitError(Exception):
    pass


class GeminiAuthError(Exception):
    pass


def lambda_handler(event, context):
    """
    Two entry points into the same function, distinguished by event shape:

    1. S3 ObjectCreated notification -> update DynamoDB metadata (status,
       file size, content type). Original behaviour, unchanged.
    2. API Gateway POST /analyze -> fetch the document from S3, extract
       text, run Gemini analysis, and store the result in DynamoDB.
    """
    try:
        if 'httpMethod' in event or event.get('requestContext', {}).get('http'):
            return handle_analyze_request(event)

        if isinstance(event.get('body'), str):
            body = json.loads(event['body'])
            records = body.get('Records', [])
        else:
            records = event.get('Records', [])

        if not records:
            return {
                'statusCode': 400,
                'body': json.dumps('Error: No Records found in event')
            }

        for record in records:
            bucket = record['s3']['bucket']['name']
            key = record['s3']['object']['key']

            email, document_id = extract_email_and_document_id(key)

            if not email or not document_id:
                print(f"Could not extract email/document_id from key: {key}")
                continue

            response = s3_client.head_object(Bucket=bucket, Key=key)
            file_size = response.get('ContentLength', 0)
            content_type = response.get('ContentType', 'application/octet-stream')

            table = dynamodb.Table(DOCUMENTS_TABLE)
            composite_key = f"{email}#{document_id}"
            table.update_item(
                Key={'email': composite_key, 'document_id': document_id},
                UpdateExpression='SET #status = :status, #processed_at = :processed_at, #file_size = :file_size, #content_type = :content_type',
                ExpressionAttributeNames={
                    '#status': 'status',
                    '#processed_at': 'processed_at',
                    '#file_size': 'file_size',
                    '#content_type': 'content_type'
                },
                ExpressionAttributeValues={
                    ':status': 'Processed',
                    ':processed_at': datetime.utcnow().isoformat(),
                    ':file_size': file_size,
                    ':content_type': content_type
                }
            )

            print(f"Successfully processed document: {document_id} for {email}")

        return {
            'statusCode': 200,
            'body': json.dumps('Documents processed successfully')
        }

    except Exception as e:
        print(f"Error processing documents: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps(f'Error: {str(e)}')
        }


def extract_email_and_document_id(key):
    """
    Extract email and document_id from S3 key format: documents/<email>/<uuid>_<filename>
    Returns: (email, document_id) or (None, None) if extraction fails
    """
    try:
        parts = key.split('/')
        if len(parts) >= 3 and parts[0] == 'documents':
            email = parts[1]
            filename_part = parts[2]
            document_id = filename_part.split('_')[0]
            return email, document_id
    except Exception as e:
        print(f"Error extracting email/document_id: {str(e)}")

    return None, None


def _json_response(status_code, body_dict):
    return {
        'statusCode': status_code,
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps(body_dict)
    }


def handle_analyze_request(event):
    """
    Handle POST /analyze from API Gateway.

    Expected JSON body: {"document_id": "...", "email": "..."}

    Fetches the document record from DynamoDB, downloads the file from S3,
    extracts its text, runs Gemini analysis, stores the result back to
    DynamoDB, and returns the analysis as the HTTP response.
    """
    try:
        body = json.loads(event.get('body') or '{}')
    except json.JSONDecodeError:
        return _json_response(400, {'error': 'Invalid JSON body'})

    document_id = body.get('document_id')
    email = body.get('email')

    if not document_id or not email:
        return _json_response(400, {'error': 'document_id and email are required'})

    if not GEMINI_API_KEY:
        return _json_response(503, {'error': 'Gemini API key is not configured on the server'})

    documents_table = dynamodb.Table(DOCUMENTS_TABLE)
    composite_key = f"{email}#{document_id}"

    try:
        response = documents_table.get_item(Key={'email': composite_key, 'document_id': document_id})
        if 'Item' not in response:
            return _json_response(404, {'error': 'Document not found'})

        doc = response['Item']
        if doc.get('user_email') != email:
            return _json_response(403, {'error': 'Unauthorized'})

        documents_table.update_item(
            Key={'email': composite_key, 'document_id': document_id},
            UpdateExpression='SET analysis_status = :status',
            ExpressionAttributeValues={':status': 'pending'}
        )

        file_obj = s3_client.get_object(Bucket=S3_INPUT_BUCKET, Key=doc['s3_key'])
        file_bytes = file_obj['Body'].read()

        try:
            document_text = extract_document_text(file_bytes, doc.get('filename', ''))
        except ValueError as e:
            _mark_failed(documents_table, composite_key, document_id)
            return _json_response(400, {'error': str(e)})

        if not document_text:
            _mark_failed(documents_table, composite_key, document_id)
            return _json_response(400, {'error': 'No extractable text found in document'})

        analysis = analyze_document_with_gemini(document_text)

        documents_table.update_item(
            Key={'email': composite_key, 'document_id': document_id},
            UpdateExpression='SET analysis = :analysis, analysis_status = :status',
            ExpressionAttributeValues={':analysis': json.dumps(analysis), ':status': 'completed'}
        )

        print(f"[ANALYZE DOC SUCCESS] {document_id} for {email}")
        return _json_response(200, {'success': True, 'analysis': analysis})

    except GeminiAuthError:
        print("[ANALYZE DOC ERROR] Invalid Gemini API key")
        _mark_failed(documents_table, composite_key, document_id)
        return _json_response(502, {'error': 'Gemini API key is invalid. Please check server configuration.'})
    except GeminiRateLimitError:
        print("[ANALYZE DOC ERROR] Gemini rate limit exceeded")
        _mark_failed(documents_table, composite_key, document_id)
        return _json_response(429, {'error': 'Gemini rate limit reached. Please try again shortly.'})
    except Exception as e:
        print(f"[ANALYZE DOC ERROR] {str(e)}")
        try:
            _mark_failed(documents_table, composite_key, document_id)
        except Exception:
            pass
        return _json_response(500, {'error': f'Analysis failed: {str(e)}'})


def _mark_failed(documents_table, composite_key, document_id):
    documents_table.update_item(
        Key={'email': composite_key, 'document_id': document_id},
        UpdateExpression='SET analysis_status = :status',
        ExpressionAttributeValues={':status': 'failed'}
    )


def extract_document_text(file_bytes, filename):
    """Extract plain text from a PDF or DOCX file for Gemini analysis."""
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


def analyze_document_with_gemini(document_text, max_retries=1):
    """Send document text to Google Gemini and return structured legal analysis.

    max_retries and the per-request timeout are kept low (worst case ~27s)
    to stay under API Gateway's hard 29s integration timeout -- if Gemini
    doesn't respond in time, the caller should see the real Gemini error,
    not a generic 504 from API Gateway.
    """
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
            params={'key': GEMINI_API_KEY},
            json=payload,
            timeout=12
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
