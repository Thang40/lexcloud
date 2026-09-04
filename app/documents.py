from flask import Blueprint, render_template, request, redirect, url_for, session, flash, send_file, current_app
from app.extensions import get_s3_client, get_documents_table
from app.auth import login_required
from datetime import datetime
from uuid import uuid4
from io import BytesIO

documents_bp = Blueprint('documents', __name__)

@documents_bp.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    if request.method == 'POST':
        email = session['email']
        file = request.files.get('file')
        contract_type = request.form.get('contract_type', '').strip()
        client_name = request.form.get('client_name', '').strip()

        if not file or file.filename == '':
            flash('No file selected.', 'danger')
            return redirect(url_for('documents.upload'))

        if not contract_type or not client_name:
            flash('Contract type and client name are required.', 'danger')
            return redirect(url_for('documents.upload'))

        try:
            filename = file.filename
            document_id = str(uuid4())
            s3_key = f"documents/{email}/{document_id}_{filename}"

            s3_client = get_s3_client()
            s3_client.upload_fileobj(
                file.stream,
                current_app.config['S3_INPUT_BUCKET'],
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
            return redirect(url_for('documents.list_documents'))
        except Exception as e:
            flash(f'Upload failed: {str(e)}', 'danger')
            return redirect(url_for('documents.upload'))

    return render_template('upload.html')

@documents_bp.route('/documents', methods=['GET', 'POST'])
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

@documents_bp.route('/documents/<document_id>/view')
@login_required
def view_document(document_id):
    email = session['email']
    documents_table = get_documents_table()

    try:
        response = documents_table.get_item(Key={'document_id': document_id})
        if 'Item' not in response:
            flash('Document not found.', 'danger')
            return redirect(url_for('documents.list_documents'))

        doc = response['Item']
        if doc['owner_email'] != email:
            flash('Unauthorized.', 'danger')
            return redirect(url_for('documents.list_documents'))

        s3_client = get_s3_client()
        file_obj = s3_client.get_object(Bucket=current_app.config['S3_INPUT_BUCKET'], Key=doc['s3_key'])
        file_data = file_obj['Body'].read()

        return send_file(
            BytesIO(file_data),
            mimetype=file_obj.get('ContentType', 'application/octet-stream'),
            as_attachment=True,
            download_name=doc.get('filename', 'document')
        )
    except Exception as e:
        flash(f'Failed to retrieve document: {str(e)}', 'danger')
        return redirect(url_for('documents.list_documents'))
