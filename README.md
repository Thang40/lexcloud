# LexCloud - Smart Legal Document Analyzer

A Flask-based web application for managing, classifying, and analyzing legal documents using AWS services (S3, DynamoDB, Lambda).

## Project Structure

```
lexcloud/
├── app/                          # Flask application package
│   ├── __init__.py              # App factory and blueprint registration
│   ├── config.py                # Configuration (env vars)
│   ├── extensions.py            # AWS service clients/resources
│   ├── auth.py                  # Authentication blueprint (register, login, logout)
│   ├── main.py                  # Main blueprint (dashboard, home)
│   ├── documents.py             # Documents blueprint (upload, list, search, view)
│   ├── analytics.py             # Analytics blueprint (charts, data aggregation)
│   └── templates/               # Jinja2 HTML templates
│       ├── base.html            # Base layout with Bootstrap navbar
│       ├── login.html
│       ├── register.html
│       ├── dashboard.html
│       ├── upload.html
│       ├── documents.html       # Document listing with search/filter
│       └── analytics.html       # Chart.js analytics dashboard
├── lambda/                       # AWS Lambda function
│   └── process_document.py      # S3-triggered document processor
├── run.py                        # Flask app entrypoint
├── requirements.txt              # Python dependencies
├── .env.example                 # Environment variables template
└── .gitignore                   # Git ignore rules
```

## Setup

### Prerequisites
- Python 3.8+
- AWS credentials configured (via AWS CLI, environment variables, or IAM role)
- S3 bucket and DynamoDB tables created in AWS

### Installation

1. Clone the repository:
```bash
cd lexcloud
```

2. Create a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create `.env` from template:
```bash
cp .env.example .env
```

5. Edit `.env` with your AWS configuration:
```
AWS_REGION=us-east-1
S3_INPUT_BUCKET=lexcloud-documents-input-thang123
S3_OUTPUT_BUCKET=lexcloud-documents-output-thang123
USERS_TABLE=users
DOCUMENTS_TABLE=documents
FLASK_ENV=development
FLASK_SECRET_KEY=your-secret-key-12345-change-in-production
```

### AWS Resources Required

Before running the app, create these resources in AWS:

**S3 Buckets:**
1. Input bucket (e.g., `lexcloud-documents-input-thang123`):
   - Block all public access enabled
   - Lambda has permission to read from this bucket
   
2. Output bucket (e.g., `lexcloud-documents-output-thang123`):
   - Block all public access enabled
   - Lambda writes processed documents here

**DynamoDB Tables:**

1. `users` table:
   - Partition Key: `email` (String)

2. `doc` table:
   - Partition Key: `document_id` (String)

### Running the App

```bash
python run.py
```

The app will start on `http://localhost:5000`

## Features

### Authentication
- User registration with bcrypt password hashing
- Email/password login
- Session-based authentication
- Logout functionality

### Document Management
- Upload PDF and image files to S3
- Classify documents by contract type and client name
- Private document storage (documents only accessible to owner)
- Search and filter documents by type, client name, and date
- View/download documents securely

### Analytics
- Aggregated statistics by contract type (doughnut chart)
- Monthly upload trend visualization (line chart)
- Chart.js for dynamic visualization

### Serverless Processing
- Lambda function triggered on S3 file upload
- Automatic metadata extraction and status update
- Document status tracking (Uploaded → Processed)

## Architecture

```
User Browser
    ↓ (HTTP)
Flask App (EC2/Beanstalk) ← Sessions, routing, auth
    ↓ (AWS SDK)
S3 Bucket ← Private document storage
DynamoDB ← User & document metadata
    ↓ (S3 events)
Lambda Function ← Async document processing
```

## Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `FLASK_SECRET_KEY` | Flask session secret | `your-secret-key-12345` |
| `FLASK_ENV` | Flask environment | `development` or `production` |
| `AWS_REGION` | AWS region | `us-east-1` |
| `S3_INPUT_BUCKET` | S3 input bucket for uploads | `lexcloud-documents-input-thang123` |
| `S3_OUTPUT_BUCKET` | S3 output bucket for processed docs | `lexcloud-documents-output-thang123` |
| `USERS_TABLE` | DynamoDB users table name | `users` |
| `DOCUMENTS_TABLE` | DynamoDB documents table name | `doc` |

## Development Notes

- Credentials are loaded via boto3's default credential chain (environment variables, AWS profile, or IAM role)
- Never commit `.env` file with real credentials
- Lambda deployment requires separate setup (IaC or console)
- Document status stays "Uploaded" until Lambda processes it (expected during local dev)
