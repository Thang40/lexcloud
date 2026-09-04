import os

class Config:
    SECRET_KEY = os.getenv('FLASK_SECRET_KEY', 'dev-secret-key')
    AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')
    S3_BUCKET_NAME = os.getenv('S3_BUCKET_NAME')
    DYNAMODB_USERS_TABLE = os.getenv('DYNAMODB_USERS_TABLE', 'users')
    DYNAMODB_DOCUMENTS_TABLE = os.getenv('DYNAMODB_DOCUMENTS_TABLE', 'documents')
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = False
    SESSION_COOKIE_SAMESITE = 'Lax'
