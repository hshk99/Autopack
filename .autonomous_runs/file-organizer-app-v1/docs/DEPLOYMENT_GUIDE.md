# Deployment Guide - FileOrganizer v1.0

## Production Deployment

### Backend Deployment

1. **Set production environment:**
   ```bash
   cp .env.production .env
   # Edit .env with production OpenAI API key
   ```

2. **Run database migrations:**
   ```bash
   python add_indexes.py
   python load_all_packs.py
   ```

3. **Start backend:**
   ```bash
   python main.py
   ```

   For production, consider using:
   - **Gunicorn:** `gunicorn -w 4 -k uvicorn.workers.UvicornWorker main:app`
   - **Systemd service** for auto-restart

### Frontend Deployment

1. **Build React app:**
   ```bash
   npm run build
   ```

2. **Package Electron app:**
   ```bash
   npm run build:electron
   ```

   This creates distributable packages in `dist/`:
   - Windows: `.exe` installer
   - macOS: `.dmg` installer
   - Linux: `.AppImage` / `.deb`

### Distribution

Upload built packages to:
- GitHub Releases
- Your website
- App stores (future)

## Security Checklist

- [ ] OpenAI API key secured (not in version control)
- [ ] CORS origins restricted in production
- [ ] File upload validation enabled
- [ ] HTTPS enabled (if deploying as web app)
- [ ] Database backups configured
- [ ] Logging configured

## Performance Tuning

- Set `CACHE_TTL_SECONDS` for optimal caching
- Adjust batch processing `max_workers` based on CPU cores
- Monitor OpenAI API usage and costs

## Monitoring

Key metrics to monitor:
- API response times
- OpenAI API usage
- Document processing errors
- Disk space usage

## Troubleshooting

**Tesseract not found:**
- Set `TESSERACT_CMD` in .env

**OpenAI API errors:**
- Check API key validity
- Monitor rate limits

**Database locked:**
- Ensure only one backend instance running
- Consider PostgreSQL for production

## Backup Strategy

Backup these regularly:
- `fileorganizer.db` - SQLite database
- `uploads/` - Uploaded documents
- `packs/` - Custom pack templates (if modified)

## Updates

To update to new version:
1. Backup database
2. Pull new code
3. Run migrations
4. Restart services

---

For issues, see README.md or open a GitHub issue.
