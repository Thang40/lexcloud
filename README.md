# LexCloud - Smart Legal Document Analyzer

A Flask-based web application for managing, classifying, and analyzing legal documents using AWS services (S3, DynamoDB, Lambda).

## Quick Start

```bash
cd lexcloud
pip install -r requirements.txt
cp .env.example .env
python run.py
```

Visit: **http://localhost:5001**

## Project Structure

```
lexcloud/
├── static/css/
│   └── style.css            # Professional styling (17KB)
├── templates/               # Jinja2 HTML templates
│   ├── base.html            # Master layout
│   ├── login.html
│   ├── register.html
│   ├── dashboard.html
│   ├── upload.html
│   ├── documents.html
│   ├── analytics.html
│   └── 404.html             # Error page
├── app.py                   # Flask application
├── run.py                   # Server launcher
└── requirements.txt         # Python dependencies
```

## Features

✅ **Authentication**
- User registration with password validation
- Email/password login
- Session-based authentication
- Secure logout

✅ **Document Management**
- Upload PDF, PNG, JPG, JPEG, DOCX files
- Classify documents by type and client
- Search and filter documents
- Download documents securely

✅ **Validation**
- Server-side input validation
- File type checking
- File size limit (50MB max)
- Email format validation
- Password strength requirements

✅ **Analytics**
- Document statistics
- Contract type breakdown
- Monthly upload trends
- Real-time data charts

✅ **Professional UI**
- Responsive design (mobile, tablet, desktop)
- Professional color scheme
- Zero external CSS dependencies
- Smooth animations and hover effects

## Configuration

1. **Create .env file:**
```bash
cp .env.example .env
```

2. **Edit .env with your AWS settings:**
```
AWS_REGION=us-east-1
S3_INPUT_BUCKET=your-bucket-name
S3_OUTPUT_BUCKET=your-output-bucket
USERS_TABLE=users
DOCUMENTS_TABLE=doc
FLASK_SECRET_KEY=your-secret-key
FLASK_ENV=development
```

3. **Create AWS Resources:**
   - S3 buckets for input and output
   - DynamoDB tables (users and documents)
   - IAM permissions for Lambda

## Running the Application

### Development Mode
```bash
python run.py
```
Server runs on **http://localhost:5001**

### Test URLs
- Login: http://localhost:5001/login
- Register: http://localhost:5001/register
- Dashboard: http://localhost:5001/dashboard
- Upload: http://localhost:5001/upload
- Documents: http://localhost:5001/documents
- Analytics: http://localhost:5001/analytics

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Server health check |
| GET/POST | `/login` | User login |
| GET/POST | `/register` | User registration |
| GET | `/dashboard` | Main dashboard |
| GET/POST | `/upload` | Upload document |
| GET | `/documents` | List documents |
| GET | `/documents/<id>/view` | Download document |
| GET | `/analytics` | Analytics dashboard |
| GET | `/api/analytics/data` | Analytics data (JSON) |

## Error Handling

- **404 Error**: Custom error page with LexCloud branding
- **Validation Errors**: Flash messages display validation issues
- **Form Submission**: Server-side validation on all forms
- **File Upload**: Type and size validation

## Design System

### Colors
- Primary: #0066cc (Blue)
- Success: #00aa44 (Green)
- Warning: #ff9900 (Orange)
- Danger: #cc0000 (Red)
- Text: #333333
- Background: #f5f5f5

### Responsive Breakpoints
- Desktop (1200px+): Full layout
- Tablet (768px-1199px): Adapted grid
- Mobile (<768px): Single column

## Validation Rules

### Registration
- Email required and must be valid
- Password minimum 6 characters
- Password and confirm password must match
- Email cannot already exist

### Login
- Email and password required
- Must match registered credentials

### Upload
- File required
- Contract type required
- Client name required
- File type: PDF, PNG, JPG, JPEG, DOCX only
- Maximum file size: 50MB

## Deployment

### AWS Elastic Beanstalk
```bash
eb create lexcloud-env
eb deploy
```

### Environment Variables
Set in Elastic Beanstalk configuration:
- `FLASK_ENV=production`
- `AWS_REGION`
- `S3_INPUT_BUCKET`
- `S3_OUTPUT_BUCKET`
- `USERS_TABLE`
- `DOCUMENTS_TABLE`
- `FLASK_SECRET_KEY` (strong random key)

## Dependencies

- Flask 3.0.0
- boto3 1.28.85
- bcrypt 4.1.1
- python-dotenv 1.0.0
- gunicorn 23.0.0

## Support

- Check console for validation error messages
- View Flask logs for debugging
- Use browser DevTools (F12) to inspect HTML/CSS
- Check AWS CloudWatch for Lambda errors

## Status

✅ **Production Ready**
- All validations implemented
- Error handling in place
- Responsive design tested
- Documentation complete

---

**Created**: September 2024
**Version**: 1.0
**License**: MIT
