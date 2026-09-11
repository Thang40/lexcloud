#!/usr/bin/env python3
"""
Verify LexCloud deployment readiness before pushing to production
"""
import os
import sys
from dotenv import load_dotenv

def check_secret_key():
    """Verify SECRET_KEY is properly configured"""
    load_dotenv()
    secret = os.getenv('FLASK_SECRET_KEY')

    if not secret:
        print("❌ FLASK_SECRET_KEY not set in .env")
        return False

    if secret == 'your-secret-key-12345-change-in-production':
        print("❌ FLASK_SECRET_KEY is still the default placeholder")
        return False

    if len(secret) < 32:
        print(f"❌ FLASK_SECRET_KEY too short ({len(secret)} chars, need 32+)")
        return False

    print(f"✅ FLASK_SECRET_KEY is secure ({len(secret)} characters)")
    return True

def check_aws_config():
    """Verify AWS configuration"""
    checks = {
        'AWS_REGION': 'us-east-1',
        'S3_INPUT_BUCKET': None,
        'S3_OUTPUT_BUCKET': None,
        'USERS_TABLE': 'users',
        'DOCUMENTS_TABLE': 'doc',
    }

    all_ok = True
    for key, default in checks.items():
        value = os.getenv(key, default)
        if not value:
            print(f"❌ {key} not set")
            all_ok = False
        else:
            print(f"✅ {key} configured")

    return all_ok

def check_dependencies():
    """Verify Python dependencies are installed"""
    required = {
        'flask': 'Flask',
        'boto3': 'boto3',
        'bcrypt': 'bcrypt',
        'dotenv': 'python-dotenv',
        'gunicorn': 'gunicorn',
    }

    all_ok = True
    for module, package in required.items():
        try:
            __import__(module)
            print(f"✅ {package} installed")
        except ImportError:
            print(f"❌ {package} not installed - run: pip install {package}")
            all_ok = False

    return all_ok

def check_flask_app():
    """Verify Flask app loads without errors"""
    try:
        from app import app
        print("✅ Flask app loads successfully")
        print(f"   - SECRET_KEY configured: {bool(app.config.get('SECRET_KEY'))}")
        print(f"   - AWS region: {app.config.get('AWS_REGION')}")
        return True
    except Exception as e:
        print(f"❌ Flask app failed to load: {e}")
        return False

def main():
    print("\n🔍 LexCloud Deployment Verification\n")
    print("=" * 50)

    results = {
        "Secret Key": check_secret_key(),
        "AWS Config": check_aws_config(),
        "Dependencies": check_dependencies(),
        "Flask App": check_flask_app(),
    }

    print("\n" + "=" * 50)
    print("\n📊 Summary:")
    for check, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status}: {check}")

    all_passed = all(results.values())

    print("\n" + "=" * 50)
    if all_passed:
        print("\n✅ All checks passed! Ready for deployment.\n")
        return 0
    else:
        print("\n❌ Some checks failed. Fix issues before deploying.\n")
        return 1

if __name__ == '__main__':
    sys.exit(main())
