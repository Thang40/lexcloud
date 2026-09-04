import os

class Config:
    SECRET_KEY = os.getenv('FLASK_SECRET_KEY', 'dev-secret-key')
    AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')
    S3_INPUT_BUCKET = os.getenv('S3_INPUT_BUCKET')
    S3_OUTPUT_BUCKET = os.getenv('S3_OUTPUT_BUCKET')
    USERS_TABLE = os.getenv('USERS_TABLE', 'users')
    DOCUMENTS_TABLE = os.getenv('DOCUMENTS_TABLE', 'doc')
    FLASK_ENV = os.getenv('FLASK_ENV', 'development')
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = False
    SESSION_COOKIE_SAMESITE = 'Lax'
