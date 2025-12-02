# API Key Authentication Fix

## Issue Found

The executor was using the wrong header format for API authentication:
- **Executor was using**: `Authorization: Bearer {api_key}`
- **API server expects**: `X-API-Key: {api_key}`

Additionally, the `_update_phase_status` method was not including the API key header at all.

## Fixes Applied

### 1. Fixed Header Format (3 locations)
Changed all API requests to use `X-API-Key` header instead of `Authorization: Bearer`:

1. **`_fetch_run_status()`** (line ~511)
   - Changed: `headers["Authorization"] = f"Bearer {self.api_key}"`
   - To: `headers["X-API-Key"] = self.api_key`

2. **`_post_builder_result()`** (line ~2246)
   - Changed: `headers["Authorization"] = f"Bearer {self.api_key}"`
   - To: `headers["X-API-Key"] = self.api_key`

3. **`_post_auditor_result()`** (line ~2325)
   - Changed: `headers["Authorization"] = f"Bearer {self.api_key}"`
   - To: `headers["X-API-Key"] = self.api_key`

### 2. Added Missing API Key Header
Added API key header to `_update_phase_status()` method (line ~2618):
- Previously had no API key header
- Now includes: `headers["X-API-Key"] = self.api_key` when `self.api_key` is set

## .env Loading Status

✅ All components already load `.env`:
- **API Server** (`main.py`): Loads `.env` on line 50
- **Executor** (`autonomous_executor.py`): Loads `.env` on line 153
- **Create Script** (`create_phase3_delegated_run.py`): Loads `.env` on line 24

## API Key Flow

1. `.env` file contains: `AUTOPACK_API_KEY=your_key_here`
2. All components load `.env` using `load_dotenv()`
3. Executor reads API key from:
   - Command line argument: `--api-key`
   - Environment variable: `AUTOPACK_API_KEY` (from `.env`)
   - Default: `os.getenv("AUTOPACK_API_KEY")` (line 2991)
4. Executor passes API key in `X-API-Key` header for all API requests
5. API server verifies the key matches `AUTOPACK_API_KEY` from `.env`

## Testing

The executor should now:
- ✅ Successfully authenticate with the API server
- ✅ Use the correct `X-API-Key` header format
- ✅ Include API key in all API requests (including status updates)
- ✅ Load API key from `.env` file automatically

## Next Steps

1. Ensure `.env` file contains: `AUTOPACK_API_KEY=your_actual_key`
2. Test API authentication by running the executor
3. Verify no more 403 Forbidden errors

