import boto3
import json
import os
from datetime import datetime

s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')

DOCUMENTS_TABLE = os.getenv('DYNAMODB_DOCUMENTS_TABLE', 'documents')
AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')

def lambda_handler(event, context):
    """
    S3-triggered Lambda function to process uploaded documents.
    Extracts metadata and updates DynamoDB document status.

    Expected S3 event structure: ObjectCreated event from S3 bucket.
    Deployment: Connect to S3 ObjectCreated:* event via S3 bucket notifications.
    """

    try:
        records = event.get('Records', [])

        for record in records:
            bucket = record['s3']['bucket']['name']
            key = record['s3']['object']['key']

            document_id = extract_document_id_from_key(key)

            if not document_id:
                print(f"Could not extract document_id from key: {key}")
                continue

            response = s3_client.head_object(Bucket=bucket, Key=key)
            file_size = response.get('ContentLength', 0)
            content_type = response.get('ContentType', 'application/octet-stream')

            table = dynamodb.Table(DOCUMENTS_TABLE)
            table.update_item(
                Key={'document_id': document_id},
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

            print(f"Successfully processed document: {document_id}")

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

def extract_document_id_from_key(key):
    """
    Extract document_id from S3 key format: documents/<email>/<uuid>_<filename>
    """
    try:
        parts = key.split('/')
        if len(parts) >= 3 and parts[0] == 'documents':
            filename_part = parts[2]
            document_id = filename_part.split('_')[0]
            return document_id
    except Exception as e:
        print(f"Error extracting document_id: {str(e)}")

    return None
