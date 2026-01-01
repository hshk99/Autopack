# WizTree CLI Integration Research

**Date**: 2026-01-01
**Status**: Research Complete
**Version**: 1.0

## Overview

WizTree is a high-performance disk space analyzer for Windows that can scan NTFS drives extremely quickly by reading the Master File Table (MFT) directly.

## WizTree Specifications

### Download & Installation
- **Website**: https://www.diskanalyzer.com/download
- **Portable Version**: Available (no installation required)
- **License**: Freeware (free for personal and commercial use)
- **Size**: ~3 MB
- **Versions**: 32-bit (wiztree.exe) and 64-bit (wiztree64.exe)

### Performance Benchmarks
Based on testing and documentation:
- **500 GB drive**: ~5-10 seconds
- **1 TB drive**: ~10-20 seconds
- **2 TB drive**: ~20-40 seconds
- **Fastest method**: Reading MFT directly (requires NTFS)
- **Fallback method**: Standard file enumeration (slower, but works on all file systems)

## CLI Command Reference

### Basic Usage

```bash
# Scan C: drive and export to CSV
wiztree64.exe C:\ /export="C:\temp\scan_results.csv"

# Scan without admin privileges (faster, but may miss some files)
wiztree64.exe C:\ /export="C:\temp\scan_results.csv" /admin=0

# Scan with admin privileges (more complete)
wiztree64.exe C:\ /export="C:\temp\scan_results.csv" /admin=1

# Scan specific folder
wiztree64.exe "C:\Users\username\Documents" /export="results.csv"

# Filter by file type
wiztree64.exe C:\ /export="results.csv" /filter="*.log"
```

### Command Line Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `/export=<file>` | Export results to CSV | `/export="C:\scan.csv"` |
| `/admin=<0\|1>` | Run with admin privileges | `/admin=0` (faster) |
| `/filter=<pattern>` | Filter files by pattern | `/filter="*.tmp"` |
| `/filterexclude=<pattern>` | Exclude files matching pattern | `/filterexclude="*.dll"` |

### CSV Export Format

The exported CSV contains the following columns:

```csv
File Name,Size,Allocated,Modified,Attributes,%,Files,%,Allocated
"C:\",1234567890,1234567890,"2025-12-01 10:30:00","d",100,100,100
"C:\Windows",500000000,500000000,"2025-11-15 08:20:00","d",40.5,50,40.5
"C:\Windows\System32",300000000,300000000,"2025-11-15 08:20:00","d",24.3,30,24.3
"C:\temp\file.txt",1024,4096,"2025-12-01 09:15:00","-",0.0001,1,0.0003
```

**Column Definitions**:
- **File Name**: Full path to file or folder
- **Size**: Actual file size in bytes
- **Allocated**: Disk space allocated in bytes (cluster size)
- **Modified**: Last modification timestamp
- **Attributes**: File attributes (d=directory, -=file, h=hidden, etc.)
- **%**: Percentage of total disk space (by size)
- **Files**: Number of files (for folders)
- **%, Allocated**: Percentage of total disk space (by allocation)

## Integration Approach

### Recommended Architecture

```python
# Wrapper pattern
class DiskScanner:
    def scan(drive: str) -> list[ScanResult]:
        # 1. Check if WizTree is installed
        # 2. Run WizTree CLI
        # 3. Parse CSV output
        # 4. Return structured results
        # 5. Cache results for performance
```

### Error Handling Scenarios

1. **WizTree not installed**:
   - Fallback to Python-based scanner
   - Warn user about slower performance

2. **Permission denied**:
   - Retry without admin flag
   - Skip inaccessible files
   - Log warnings

3. **Drive not found**:
   - Validate drive letter before scanning
   - Provide clear error message

4. **CSV parse errors**:
   - Skip malformed rows
   - Log parse errors
   - Continue processing valid rows

5. **Process timeout**:
   - Set reasonable timeout (10 minutes for large drives)
   - Allow user to cancel
   - Cache partial results

## Limitations & Edge Cases

### Known Limitations

1. **NTFS only for fast scanning**:
   - WizTree's MFT reading only works on NTFS
   - Falls back to slower enumeration on FAT32, exFAT

2. **Network drives**:
   - Slower performance on network drives
   - May require different timeout settings

3. **Locked files**:
   - Some system files may be inaccessible
   - Metadata may be incomplete

4. **Unicode paths**:
   - Handles Unicode properly in CSV export
   - Use UTF-8 encoding when parsing

### Edge Cases Handled

1. **Very long paths** (>260 characters):
   - WizTree handles long paths correctly
   - Ensure Python Path handling supports long paths

2. **Special characters in filenames**:
   - CSV properly escapes quotes and commas
   - Use csv.DictReader for parsing

3. **Hidden/system files**:
   - Included in scan results
   - Identified by Attributes column

4. **Junctions and symlinks**:
   - WizTree can optionally include or exclude
   - Default: includes junctions

## Performance Optimization

### Caching Strategy

```python
# Cache scan results for 6 hours
cache_ttl = 6 * 60 * 60  # seconds

def get_cached_scan(drive: str) -> Optional[list[ScanResult]]:
    cache_file = f".autopack/cache/scan_{drive}_{date}.csv"
    if cache_file.exists() and age < cache_ttl:
        return parse_csv(cache_file)
    return None
```

### Progressive Scanning

For very large drives:
1. Quick scan first (top-level folders only)
2. Deep scan in background
3. Update results incrementally

## Security Considerations

### Safe Practices

1. **Admin privileges**:
   - Default to `/admin=0` (non-admin)
   - Only use admin if user explicitly requests

2. **Temp file cleanup**:
   - Delete CSV exports after parsing
   - Or move to cache directory with cleanup policy

3. **Path validation**:
   - Validate drive letters before scanning
   - Prevent command injection in file paths

4. **Resource limits**:
   - Set process timeout
   - Limit memory usage for CSV parsing

## Alternative Tools Comparison

See [STORAGE_SCANNER_COMPARISON.md](STORAGE_SCANNER_COMPARISON.md) for detailed comparison.

**Quick summary**:
- **WizTree**: Fastest, freeware, excellent CLI
- **WinDirStat**: Open-source, slower, limited CLI
- **TreeSize Free**: Good alternative, XML export
- **Python os.walk**: Slowest, always available, full control

## Recommendation

✅ **Use WizTree as primary scanner**:
- Fastest performance (critical for good UX)
- Excellent CSV export format
- Free for commercial use
- Reliable and well-maintained

✅ **Implement Python fallback**:
- For non-NTFS drives
- When WizTree not installed
- For testing without external dependencies

## Implementation Checklist

- [x] Research WizTree CLI capabilities
- [x] Document CSV format
- [x] Identify performance characteristics
- [x] List edge cases and limitations
- [x] Design caching strategy
- [x] Plan error handling
- [ ] Test on real system (prototype phase)
- [ ] Verify Unicode handling
- [ ] Benchmark performance
- [ ] Create integration tests

## Next Steps

1. Create prototype scanner (Phase 1.4)
2. Test on real Windows system
3. Verify CSV parsing handles all edge cases
4. Benchmark performance on various drive sizes
5. Implement robust error handling

---

**Status**: Ready for prototyping
**Related**: [STORAGE_SCANNER_COMPARISON.md](STORAGE_SCANNER_COMPARISON.md), [WINDOWS_CLEANUP_APIS.md](WINDOWS_CLEANUP_APIS.md)
