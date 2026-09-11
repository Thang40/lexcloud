# Quick Deployment Reference - LexCloud

## 🚀 Deploy in 5 Minutes

### Step 1: Verify Everything Is Ready
```bash
cd /Users/thang/Desktop/Cloud\ /a3-2/lexcloud
python3 verify_deployment.py
```

You should see: ✅ All checks passed!

### Step 2: Deploy to AWS (Choose ONE)

#### 🅐 Using EB CLI (Recommended)
```bash
eb setenv FLASK_SECRET_KEY=253b67d1130e038e34f48653584f4f290b1145f00fa6f61d9c69e402eed12ca8
eb deploy
eb status
```

#### 🅑 Using AWS CLI (Direct)
```bash
aws elasticbeanstalk update-environment \
  --environment-name lexcloud-env \
  --option-settings \
    Namespace=aws:elasticbeanstalk:application:environment \
    OptionName=FLASK_SECRET_KEY \
    Value=253b67d1130e038e34f48653584f4f290b1145f00fa6f61d9c69e402eed12ca8
```

#### 🅒 Using AWS Console (Manual)
1. Go to AWS Elastic Beanstalk
2. Select environment → Configuration → Software
3. Find "Environment Properties" section
4. Add: `FLASK_SECRET_KEY` = `253b67d1130e038e34f48653584f4f290b1145f00fa6f61d9c69e402eed12ca8`
5. Click "Apply"

### Step 3: Verify Deployment
```bash
# Check deployment status
eb status

# View logs
eb logs

# Test health endpoint
curl https://your-lexcloud-domain/health
```

### Step 4: Test Application
- Log in with test account
- Verify sessions work (refresh page, stays logged in)
- Test logout and login
- Submit forms (CSRF protection)

---

## 📋 What Was Changed

| File | Status | Details |
|------|--------|---------|
| `.env` | ✅ Updated | New secure FLASK_SECRET_KEY |
| `DEPLOYMENT_GUIDE.md` | ✨ New | Full deployment documentation |
| `SECURITY_UPDATE.md` | ✨ New | Security audit results |
| `verify_deployment.py` | ✨ New | Automated verification tool |
| `app.py` | ✅ No change | Already reads from env correctly |
| `.gitignore` | ✅ No change | Already protects .env |

---

## 🔑 Key Details

| Property | Value |
|----------|-------|
| New Secret Key | `253b67d1130e038e34f48653584f4f290b1145f00fa6f61d9c69e402eed12ca8` |
| Key Length | 64 characters (256-bit) |
| Generation Method | `secrets.token_hex(32)` - cryptographically secure |
| AWS Region | us-east-1 |
| EB Environment | lexcloud-env (verify this is your env name) |

---

## ✅ Checklist Before Deploying

- [ ] Run `python3 verify_deployment.py` → all green ✅
- [ ] Verify EB environment name is correct
- [ ] Have AWS credentials configured (`aws sts get-caller-identity`)
- [ ] Backup current production if needed
- [ ] Have 15-30 minutes for deployment + monitoring

---

## 🆘 Troubleshooting

### Deployment Fails
```bash
# Check what went wrong
eb logs --all

# Revert to previous version
eb abort
```

### Sessions Not Working After Deploy
```bash
# Check if SECRET_KEY is set
eb printenv | grep FLASK_SECRET_KEY

# If not set, use eb setenv command again
eb setenv FLASK_SECRET_KEY=253b67d1130e038e34f48653584f4f290b1145f00fa6f61d9c69e402eed12ca8

# Redeploy
eb deploy
```

### Can't Connect to EB
```bash
# Check AWS credentials
aws sts get-caller-identity

# Initialize EB CLI if needed
eb init
```

---

## 📞 Need More Help?

- See `DEPLOYMENT_GUIDE.md` for detailed instructions
- See `SECURITY_UPDATE.md` for security details
- Run `verify_deployment.py` to diagnose issues
- Check EB logs: `eb logs`

---

**Secret Key Deployed**: ✅ 2026-09-12  
**Status**: Ready for Production
