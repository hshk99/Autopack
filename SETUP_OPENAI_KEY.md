# Setting Up Your OpenAI API Key

To run autonomous builds, you need to provide your OpenAI API key. Here are your options:

---

## Option 1: .env File (Recommended) ✅

This is the easiest and most secure way for development.

### Steps:

1. **Copy the example file:**
   ```bash
   cp .env.example .env
   ```

2. **Edit .env and add your key:**
   ```bash
   # Open .env in your editor
   notepad .env  # Windows
   # or
   nano .env     # Linux/Mac
   ```

3. **Replace the placeholder:**
   ```
   OPENAI_API_KEY=sk-your-actual-key-here
   ```

4. **Save and close**

5. **.env is in .gitignore** - Your key won't be committed to git!

### Then run:
```bash
# For local testing
python integrations/supervisor.py

# For Docker
docker-compose up -d
```

Docker Compose will automatically load variables from `.env`.

---

## Option 2: Environment Variable (Quick Testing)

Set the key temporarily in your terminal session:

### Windows PowerShell:
```powershell
$env:OPENAI_API_KEY = "sk-your-key-here"
python integrations/supervisor.py
```

### Windows CMD:
```cmd
set OPENAI_API_KEY=sk-your-key-here
python integrations/supervisor.py
```

### Linux/Mac:
```bash
export OPENAI_API_KEY='sk-your-key-here'
python integrations/supervisor.py
```

**Note:** This only lasts for the current terminal session.

---

## Option 3: Pass Directly to Supervisor (Code)

You can also pass the key directly when creating the Supervisor:

```python
from integrations.supervisor import Supervisor

supervisor = Supervisor(
    api_url="http://localhost:8000",
    openai_api_key="sk-your-key-here"  # Pass directly
)

# Run autonomous build
result = supervisor.run_autonomous_build(...)
```

**Warning:** Don't commit code with API keys hardcoded!

---

## Verifying Your Setup

### Check if key is set:

**PowerShell:**
```powershell
$env:OPENAI_API_KEY
```

**CMD:**
```cmd
echo %OPENAI_API_KEY%
```

**Linux/Mac:**
```bash
echo $OPENAI_API_KEY
```

### Test the integration:

```bash
# Make sure Autopack API is running
docker-compose up -d

# Run the example build
python integrations/supervisor.py
```

You should see:
```
Autopack Supervisor - Autonomous Build Orchestration
Per v7 GPT Architect: OpenAI API with ModelSelector

============================================================
🤖 AUTONOMOUS BUILD: auto-build-1732439000
============================================================

[Supervisor] Creating run: auto-build-1732439000
[Supervisor] ✅ Run created: auto-build-1732439000

[Supervisor] ═══ Executing Phase: P1.1 ═══
[Supervisor] 🧠 Model Selection:
[Supervisor]    Builder: gpt-4o-mini
[Supervisor]    Auditor: gpt-4o-mini
...
```

---

## Getting an OpenAI API Key

If you don't have a key yet:

1. Go to https://platform.openai.com/api-keys
2. Sign in or create an account
3. Click "Create new secret key"
4. Copy the key (starts with `sk-`)
5. Store it securely (you can't see it again!)

### Pricing (as of 2024):

- **gpt-4o-mini**: $0.15 / 1M input tokens, $0.60 / 1M output tokens
- **gpt-4o**: $2.50 / 1M input tokens, $10.00 / 1M output tokens
- **gpt-4-turbo**: $10.00 / 1M input tokens, $30.00 / 1M output tokens

A typical simple phase uses ~3,000 tokens = **$0.0009 with gpt-4o-mini** ✅

---

## Security Best Practices

✅ **DO:**
- Use `.env` file (it's in `.gitignore`)
- Use environment variables
- Rotate keys periodically
- Use different keys for dev/prod

❌ **DON'T:**
- Commit keys to git
- Share keys publicly
- Hardcode keys in source files
- Use the same key everywhere

---

## Troubleshooting

### "OPENAI_API_KEY environment variable not set"

**Solution:** The key isn't loaded. Use Option 1 or 2 above.

### "Invalid API key"

**Solutions:**
- Check for typos (keys start with `sk-`)
- Verify key is active at https://platform.openai.com/api-keys
- Check for extra spaces or quotes

### "Rate limit exceeded"

**Solutions:**
- You've hit OpenAI's usage limits
- Wait a few seconds and retry
- Upgrade your OpenAI plan for higher limits

### "Insufficient quota"

**Solution:**
- Add credits to your OpenAI account
- Check your billing at https://platform.openai.com/account/billing

---

## Next Steps

Once your key is set up:

1. ✅ **Run first test build:**
   ```bash
   python integrations/supervisor.py
   ```

2. ✅ **Check the results:**
   - Watch the console output
   - Check `.autonomous_runs/` for generated files
   - View run summary at http://localhost:8000/docs

3. ✅ **Try a custom build:**
   - Modify the example in `supervisor.py`
   - Add more phases
   - Try different complexity levels

4. ✅ **Monitor costs:**
   - Check token usage in console output
   - Review OpenAI usage at https://platform.openai.com/usage

---

**You're ready to go!** 🚀

For questions or issues, see:
- [LLM_INTEGRATION_STATUS.md](LLM_INTEGRATION_STATUS.md) - Integration status
- [INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md) - Complete integration guide
- https://github.com/hshk99/Autopack
