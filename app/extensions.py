import boto3
from flask import current_app

_s3_client = None
_dynamodb_resource = None

def get_s3_client():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client('s3', region_name=current_app.config['AWS_REGION'])
    return _s3_client

def get_dynamodb_resource():
    global _dynamodb_resource
    if _dynamodb_resource is None:
        _dynamodb_resource = boto3.resource('dynamodb', region_name=current_app.config['AWS_REGION'])
    return _dynamodb_resource

def get_users_table():
    dynamodb = get_dynamodb_resource()
    return dynamodb.Table(current_app.config['USERS_TABLE'])

def get_documents_table():
    dynamodb = get_dynamodb_resource()
    return dynamodb.Table(current_app.config['DOCUMENTS_TABLE'])
