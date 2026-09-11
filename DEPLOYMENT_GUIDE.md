# LexCloud Deployment & Security Guide

## Current Status
✅ **Local Environment**: Secret key properly configured and loaded  
📊 **Key Length**: 64 characters (256-bit, cryptographically secure)  
✅ **Git History**: `.env` never committed (safe from exposure)

---

## 🚀 Deployment to Production (AWS Elastic Beanstalk)

### Option 1: EB CLI (Recommended if you have EB access)

```bash
# 1. Initialize EB CLI (one-time setup)
cd /Users/thang/Desktop/Cloud\ /a3-2/lexcloud
eb init

# 2. Set environment variable for your EB environment
eb setenv FLASK_SECRET_KEY=253b67d1130e038e34f48653584f4f290b1145f00fa6f61d9c69e402eed12ca8

# 3. Verify it was set
eb printenv

# 4. Deploy
eb deploy

# 5. Monitor deployment
eb status
eb logs
```

### Option 2: AWS Management Console (Direct)

1. Go to AWS Elastic Beanstalk Console
2. Select your environment (e.g., `lexcloud-env`)
3. Configuration → Software
4. Scroll to "Environment Properties"
5. Add/Update property:
   - **Name**: `FLASK_SECRET_KEY`
   - **Value**: `253b67d1130e038e34f48653584f4f290b1145f00fa6f61d9c69e402eed12ca8`
6. Click "Apply" and wait for environment to update

### Option 3: AWS CLI Direct Command

```bash
aws elasticbeanstalk update-environment \
  --environment-name lexcloud-env \
  --option-settings \
    Namespace=aws:elasticbeanstalk:application:environment \
    OptionName=FLASK_SECRET_KEY \
    Value=253b67d1130e038e34f48653584f4f290b1145f00fa6f61d9c69e402eed12ca8
```

---

## 🔐 Advanced: AWS Secrets Manager Integration (Best Practice)

### Setup Secrets Manager

```bash
# 1. Create secret in AWS Secrets Manager
aws secretsmanager create-secret \
  --name lexcloud/flask-secret-key \
  --secret-string 253b67d1130e038e34f48653584f4f290b1145f00fa6f61d9c69e402eed12ca8 \
  --region us-east-1

# 2. Verify secret was created
aws secretsmanager get-secret-value \
  --secret-id lexcloud/flask-secret-key \
  --region us-east-1
```

### Update Flask App to Use Secrets Manager

Edit `app.py` to read from Secrets Manager:

```python
import os
import boto3
from dotenv import load_dotenv

load_dotenv()

# Try to get from Secrets Manager first, fall back to env var
def get_secret_key():
    try:
        client = boto3.client('secretsmanager', region_name=os.getenv('AWS_REGION', 'us-east-1'))
        response = client.get_secret_value(SecretId='lexcloud/flask-secret-key')
        return response['SecretString']
    except Exception as e:
        print(f"Warning: Could not fetch from Secrets Manager: {e}")
        # Fallback to environment variable
        return os.getenv('FLASK_SECRET_KEY', 'dev-secret-key')

app = Flask(__name__, template_folder='templates', static_folder='static')
app.config['SECRET_KEY'] = get_secret_key()
```

### Update IAM Role

Ensure your EB EC2 instance IAM role has permission to read the secret:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue"
      ],
      "Resource": "arn:aws:secretsmanager:us-east-1:ACCOUNT-ID:secret:lexcloud/flask-secret-key-*"
    }
  ]
}
```

---

## ✅ Verification Checklist

After deploying to production:

- [ ] Log into application with user account
- [ ] Verify session persists across page reloads
- [ ] Test logout and login flow
- [ ] Check CloudWatch logs: `eb logs` (no SECRET_KEY errors)
- [ ] Run health check: `curl https://your-lexcloud-domain/health`
- [ ] Monitor for 24 hours for session-related errors
- [ ] Verify CSRF protection is working (submit forms)

---

## 🛡️ Security Best Practices

### Do
✅ Store secrets in AWS Secrets Manager or Parameter Store  
✅ Rotate keys periodically (quarterly)  
✅ Use different keys for dev/staging/prod  
✅ Monitor secret access via CloudTrail  
✅ Ensure `.env` is in `.gitignore` (already done)  

### Don't
❌ Commit `.env` to git  
❌ Hardcode secrets in code  
❌ Share secrets in email/Slack  
❌ Use same secret across environments  
❌ Log the secret key value  

---

## 📋 Secret Key Rotation

When you need to rotate the secret key (recommended quarterly):

```bash
# 1. Generate new key
python3 -c "import secrets; print(secrets.token_hex(32))"

# 2. Update Secrets Manager
aws secretsmanager update-secret \
  --secret-id lexcloud/flask-secret-key \
  --secret-string NEW_KEY_HERE

# 3. Or update EB environment variable
eb setenv FLASK_SECRET_KEY=NEW_KEY_HERE

# 4. Deploy
eb deploy

# 5. Monitor for session errors
eb logs
```

---

## 🔍 Monitoring & Alerts

Setup CloudWatch alarms for security issues:

```bash
# Create alarm for failed authentication attempts
aws cloudwatch put-metric-alarm \
  --alarm-name lexcloud-failed-auth \
  --alarm-description "Alert on failed login attempts" \
  --metric-name FailedAuthentication \
  --namespace LexCloud
```

---

## 📞 Support

If you encounter issues after deployment:

1. Check EB logs: `eb logs`
2. Check CloudWatch: AWS Console → CloudWatch → Logs
3. Test locally: `python run.py`
4. Verify env vars: `eb printenv`

---

**Last Updated**: 2026-09-12  
**Status**: 🟢 Ready for Production Deployment
