from flask import Blueprint, render_template, session, jsonify
from app.extensions import get_documents_table
from app.auth import login_required
from datetime import datetime
from collections import defaultdict

analytics_bp = Blueprint('analytics', __name__)

@analytics_bp.route('/analytics')
@login_required
def analytics():
    return render_template('analytics.html')

@analytics_bp.route('/api/analytics/data')
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

        contract_counts = defaultdict(int)
        monthly_counts = defaultdict(int)

        for doc in documents:
            contract_type = doc.get('contract_type', 'Unknown')
            contract_counts[contract_type] += 1

            uploaded_at = doc.get('uploaded_at', '')
            if uploaded_at:
                try:
                    date_obj = datetime.fromisoformat(uploaded_at)
                    month_key = date_obj.strftime('%Y-%m')
                    monthly_counts[month_key] += 1
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
