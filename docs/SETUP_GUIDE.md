# Autopack Setup Guide

**Quick reference for getting Autopack up and running**

---

## Prerequisites

- Python 3.11+
- Docker + docker-compose
- Git
- API keys for LLM providers (see Multi-Provider Setup below)

---

## Quick Start (5 minutes)

### 1. Clone and Setup

```bash
git clone https://github.com/hshk99/Autopack.git
cd Autopack

# Copy environment template
cp .env.example .env
```

### 2. Add Your API Keys

Edit `.env`:
```bash
# Required: At least one provider (GLM recommended for low-cost)
GLM_API_KEY=your-zhipu-api-key           # Zhipu AI (low complexity)
GOOGLE_API_KEY=your-google-api-key       # Google Gemini (medium complexity)
ANTHROPIC_API_KEY=your-anthropic-key     # Anthropic (high complexity)
OPENAI_API_KEY=your-openai-key           # OpenAI (escalation/fallback)
```

**Get keys**:
- GLM: https://open.bigmodel.cn/
- Gemini: https://ai.google.dev/
- Anthropic: https://console.anthropic.com/
- OpenAI: https://platform.openai.com/api-keys

### 3. Start Services

```bash
docker-compose up -d
```

### 4. Verify Health

```bash
curl http://localhost:8000/health
```

Should return: `{"status":"healthy"}`

### 5. Run First Build

```bash
python integrations/supervisor.py --project-id MyProject
```

**Done!** You should see autonomous build output.

---

## Services

| Service | Port | Description |
|---------|------|-------------|
| **Autopack API** | 8000 | FastAPI application |
| **PostgreSQL** | 5432 | Database |
| **API Docs** | 8000/docs | Swagger UI |

---

## Multi-Project Setup

### Option 1: Single Project
```python
from integrations.supervisor import Supervisor

supervisor = Supervisor(
    api_url="http://localhost:8000",
    project_id="MyWebApp"  # For learned rules isolation
)

result = supervisor.run_autonomous_build(
    run_id="feature-add-auth",
    tiers=[...],
    phases=[...]
)
```

### Option 2: External Project Directory
```python
supervisor = Supervisor(
    api_url="http://localhost:8000",
    project_id="MyWebApp",
    target_repo_path="c:\\Projects\\my-web-app"  # Build in external directory
)
```

**Project Isolation**:
- Each `project_id` gets its own learned rules
- Each `target_repo_path` gets its own `.autonomous_runs/` directory
- Complete isolation between projects

---

## Configuration Files

### Essential Files

| File | Purpose |
|------|---------|
| `.env` | API keys and environment variables |
| `config/models.yaml` | LLM model selection and pricing |
| `config/pricing.yaml` | Cost tracking |
| `config/project_types.yaml` | Auxiliary agent definitions |
| `docker-compose.yml` | Service orchestration |

### Optional Configuration

**For Advanced Users**:
- `config/stack_profiles.yaml` - Stack configurations
- `prompts/claude/*.md` - Auxiliary agent prompts (10 agents)

---

## Environment Variables

**LLM Provider Keys** (at least one required):
```bash
GLM_API_KEY=your-zhipu-key               # Zhipu AI GLM (low complexity)
GOOGLE_API_KEY=your-google-key           # Google Gemini (medium complexity)
ANTHROPIC_API_KEY=your-anthropic-key     # Anthropic Claude (high complexity)
OPENAI_API_KEY=sk-...                    # OpenAI (escalation/fallback)
```

**Optional**:
```bash
DATABASE_URL=postgresql://...            # Default: postgres/postgres@localhost
TARGET_REPO_PATH=c:\Projects\my-app      # Default: current directory
```

---

## API Key Setup Options

### Option 1: .env File (Recommended) ✅
```bash
# Already done in Quick Start
cp .env.example .env
# Edit .env and add: OPENAI_API_KEY=sk-...
```

### Option 2: Environment Variable
**Windows PowerShell**:
```powershell
$env:OPENAI_API_KEY = "sk-your-key-here"
```

**Linux/Mac**:
```bash
export OPENAI_API_KEY='sk-your-key-here'
```

### Option 3: Pass Directly
```python
supervisor = Supervisor(
    api_url="http://localhost:8000",
    openai_api_key="sk-your-key-here"
)
```

**Security**: Never commit keys to git! `.env` is in `.gitignore`.

---

## Verify Setup

### Check Services
```bash
# Check Docker containers
docker-compose ps

# Check API health
curl http://localhost:8000/health

# Check database connection
docker-compose exec db psql -U postgres -c "SELECT version();"
```

### Test Autonomous Build
```bash
python integrations/supervisor.py --project-id TestProject
```

**Expected Output**:
```
[Supervisor] Creating run: auto-build-...
[Supervisor] Run created
[Supervisor] Model Selection: glm-4.6-20250101 (low complexity)
[Supervisor] Dispatching to Builder...
```

### View API Documentation
Open browser: http://localhost:8000/docs

---

## Cost Management

### Typical Costs (Per Run) - Current Model Stack

| Complexity | Model | Est. Tokens | Est. Cost |
|-----------|-------|-------------|-----------|
| Low | glm-4.6-20250101 | 1.5M | $1.05 |
| Medium | gemini-2.5-pro | 2.5M | $15.63 |
| High | claude-sonnet-4-5 | 1.0M | $18.00 |
| **Total (Mixed)** | **Varies** | **5M** | **~$35** |

**With Optimizations**: ~$20 per run (43% reduction)

### Cost per Phase (Current Stack)

| Complexity | Model | Builder + Auditor Cost |
|-----------|-------|------------------------|
| Low | GLM-4 Plus | ~$0.0035/phase |
| Medium | Gemini 2.5 Pro | ~$0.03/phase |
| High | Claude Sonnet 4.5 | ~$0.16/phase |

### Monitor Usage
- Console output shows token usage per phase
- OpenAI dashboard: https://platform.openai.com/usage
- Run `scripts/analyze_learned_rules.py` for cost analysis

---

## Troubleshooting

### "Connection refused" on port 8000
**Solution**: Start Docker services
```bash
docker-compose up -d
```

### "OPENAI_API_KEY not set"
**Solution**: Add key to `.env` file (see API Key Setup above)

### "Invalid API key"
**Solutions**:
- Verify key at https://platform.openai.com/api-keys
- Check for typos (keys start with `sk-`)
- Remove extra spaces or quotes

### "Rate limit exceeded"
**Solutions**:
- Wait a few seconds and retry
- Upgrade OpenAI plan for higher limits

### "Insufficient quota"
**Solution**:
- Add credits to OpenAI account
- Check billing: https://platform.openai.com/account/billing

### Docker issues
```bash
# Restart services
docker-compose down
docker-compose up -d

# Check logs
docker-compose logs autopack-api
docker-compose logs db
```

### Database connection issues
```bash
# Reset database
docker-compose down -v
docker-compose up -d
```

---

## Recommended Workflow

### First-Time Setup
1. ✅ Complete Quick Start (above)
2. ✅ Run test build to verify setup
3. ✅ Check `.autonomous_runs/` for generated files
4. ✅ Review API docs at http://localhost:8000/docs

### Daily Usage
1. Start services: `docker-compose up -d`
2. Run build: `python integrations/supervisor.py --project-id MyProject`
3. Monitor console output for progress
4. Check results in `.autonomous_runs/{project_id}/`
5. Review learned rules: `python scripts/analyze_learned_rules.py --project-id MyProject`

### After Each Run
- Check promoted rules in `.autonomous_runs/{project_id}/project_learned_rules.json`
- Review postmortem in `docs/run_{run_id}_lessons.md` (if aux agents enabled)
- Monitor token usage and costs

---

## Next Steps

### For New Users
1. ✅ **Complete Quick Start** (above)
2. ✅ **Run first test build**
3. ✅ **Read main README.md** for full capabilities
4. ✅ **Read LEARNED_RULES_README.md** for self-improving intelligence

### For Production Use
1. **Configure quota-aware routing**: See `docs/QUOTA_AWARE_ROUTING.md`
2. **Enable auxiliary agents**: Set `enable_aux_agents=True` in Supervisor
3. **Set up multi-project isolation**: Use unique `project_id` per project
4. **Implement quota tracking**: Follow TODOs in `config/models.yaml`

### For Advanced Optimization
1. **Review token efficiency**: See `docs/TOKEN_EFFICIENCY_IMPLEMENTATION.md`
2. **Optimize model selection**: Adjust `config/models.yaml` based on cost tuning agent recommendations
3. **Set up GLM fallback**: Subscribe to GLM and update `config/models.yaml`

---

## Documentation

- **[README.md](../../README.md)** - Complete system overview
- **[LEARNED_RULES_README.md](../../LEARNED_RULES_README.md)** - Learned rules technical guide
- **[docs/TOKEN_EFFICIENCY_IMPLEMENTATION.md](../TOKEN_EFFICIENCY_IMPLEMENTATION.md)** - Token optimization
- **[docs/QUOTA_AWARE_ROUTING.md](../QUOTA_AWARE_ROUTING.md)** - Multi-provider quota management
- **[docs/archive/CONSOLIDATED_HISTORY.md](CONSOLIDATED_HISTORY.md)** - Implementation history

---

## Support

- **GitHub**: https://github.com/hshk99/Autopack
- **API Docs**: http://localhost:8000/docs (when running)
- **Issues**: Report issues on GitHub repository

---

**You're ready to build!** 🚀

Start with: `python integrations/supervisor.py --project-id MyFirstProject`
