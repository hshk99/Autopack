# Windows Cleanup APIs Research

**Date**: 2026-01-01
**Purpose**: Research safe deletion methods for Storage Optimizer
**Version**: 1.0

## Overview

This document evaluates various methods for safely deleting files on Windows, balancing safety (recoverability) with completeness (permanent deletion).

---

## Safe Deletion Methods

### 1. Send to Recycle Bin (Recommended for User Files)

**Library**: `send2trash` (Python package)

#### Pros
✅ **Recoverable** - Files can be restored from Recycle Bin
✅ **User-friendly** - Familiar behavior
✅ **Cross-platform** - Works on Windows, macOS, Linux
✅ **Safe** - No accidental permanent deletion
✅ **Simple API** - One function call

#### Cons
❌ **Requires package** - Not built-in to Python
❌ **Slower** - Moves files instead of unlinking
❌ **Disk space** - Files still occupy space until bin is emptied
❌ **Large files** - May prompt user for confirmation

#### Installation
```bash
pip install send2trash
```

#### Usage
```python
from send2trash import send2trash

# Move file to Recycle Bin
send2trash('C:\\temp\\file.txt')

# Move folder to Recycle Bin
send2trash('C:\\temp\\old_folder')
```

#### Error Handling
```python
try:
    send2trash(path)
except Exception as e:
    # Permission denied, file in use, or path doesn't exist
    logger.error(f"Failed to move {path} to Recycle Bin: {e}")
```

#### Use Case for Autopack
**Primary deletion method** for:
- User files (downloads, temp files)
- Developer artifacts (node_modules, venv)
- Browser caches
- Any files user might want to recover

---

### 2. Permanent Deletion (os.remove / shutil.rmtree)

**Library**: Built-in Python (`os`, `shutil`)

#### Pros
✅ **Built-in** - No external dependencies
✅ **Fast** - Direct file deletion
✅ **Guaranteed space reclamation** - Immediate disk space freed
✅ **Simple** - Standard Python API

#### Cons
❌ **Irreversible** - No recovery without backup
❌ **Dangerous** - Risk of data loss
❌ **Permission errors** - May fail on locked files

#### Usage
```python
import os
import shutil
from pathlib import Path

# Delete single file
os.remove('C:\\temp\\file.txt')
# or
Path('C:\\temp\\file.txt').unlink()

# Delete folder recursively
shutil.rmtree('C:\\temp\\old_folder')
```

#### Safe Deletion Pattern
```python
def safe_delete(path: Path, use_recycle_bin: bool = True):
    """Safely delete file or folder."""
    if not path.exists():
        raise FileNotFoundError(f"Path does not exist: {path}")

    # Protected paths - never delete
    protected = [
        'C:\\Windows',
        'C:\\Program Files',
        'C:\\Program Files (x86)',
    ]

    if any(str(path).startswith(p) for p in protected):
        raise PermissionError(f"Cannot delete protected path: {path}")

    try:
        if use_recycle_bin and SEND2TRASH_AVAILABLE:
            send2trash(str(path))
            logger.info(f"Moved to Recycle Bin: {path}")
        else:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            logger.info(f"Permanently deleted: {path}")
    except PermissionError:
        logger.error(f"Permission denied: {path}")
        raise
    except FileNotFoundError:
        logger.warning(f"File not found (may have been deleted): {path}")
    except Exception as e:
        logger.error(f"Failed to delete {path}: {e}")
        raise
```

#### Use Case for Autopack
**Secondary deletion method** for:
- Temp files (when recycle bin would be too slow)
- Very large files (to avoid filling recycle bin)
- System cleanup tasks

---

### 3. Windows Storage Sense API

**Access**: Via PowerShell or Win32 API

#### Overview
Storage Sense is a built-in Windows feature that automatically cleans:
- Temporary files
- Recycle Bin (files older than X days)
- Downloads folder (files older than X days)
- Previous Windows installation (Windows.old)

#### PowerShell Commands
```powershell
# Enable Storage Sense
Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\StorageSense\Parameters\StoragePolicy" -Name "01" -Value 1

# Run Storage Sense now
cleanmgr /autoclean

# Run with custom settings
cleanmgr /verylowdisk
```

#### Python Integration
```python
import subprocess

def run_storage_sense():
    """Trigger Windows Storage Sense cleanup."""
    try:
        # Run cleanmgr in automated mode
        subprocess.run(['cleanmgr', '/autoclean'], check=True, timeout=300)
        logger.info("Storage Sense cleanup completed")
    except subprocess.CalledProcessError as e:
        logger.error(f"Storage Sense failed: {e}")
    except subprocess.TimeoutExpired:
        logger.warning("Storage Sense timed out")
```

#### Use Case for Autopack
**Complementary cleanup** - Run as part of optimization, but not primary method

---

### 4. Disk Cleanup Utility (cleanmgr.exe)

**Tool**: Built-in Windows tool

#### Capabilities
- Temporary files cleanup
- Windows Update cleanup
- Thumbnail cache
- Recycle Bin
- Previous Windows installations
- System error memory dumps

#### Command Line Usage
```bash
# Configure cleanup profile
cleanmgr /sageset:1

# Run cleanup profile
cleanmgr /sagerun:1

# Very low disk mode (aggressive)
cleanmgr /verylowdisk

# Auto cleanup (no UI)
cleanmgr /autoclean
```

#### Python Integration
```python
def run_disk_cleanup(profile_id: int = 1):
    """Run Windows Disk Cleanup."""
    try:
        # Run cleanup profile
        subprocess.run(
            ['cleanmgr', f'/sagerun:{profile_id}'],
            check=True,
            timeout=600  # 10 minutes
        )
        logger.info("Disk Cleanup completed")
    except Exception as e:
        logger.error(f"Disk Cleanup failed: {e}")
```

#### Use Case for Autopack
**System-level cleanup** - For Windows Update cleanup, Windows.old removal

---

### 5. DISM Cleanup (Deployment Image Servicing)

**Tool**: DISM.exe (built-in)

#### Capabilities
Cleans Windows component store and updates:
- Superseded Windows updates
- Component store cleanup
- Service pack cleanup

#### Command Line Usage
```bash
# Analyze cleanup potential
Dism.exe /Online /Cleanup-Image /AnalyzeComponentStore

# Cleanup component store
Dism.exe /Online /Cleanup-Image /StartComponentCleanup

# Cleanup with reset base (more aggressive)
Dism.exe /Online /Cleanup-Image /StartComponentCleanup /ResetBase

# Cleanup service packs
Dism.exe /Online /Cleanup-Image /SPSuperseded
```

#### Python Integration
```python
def run_dism_cleanup():
    """Run DISM component store cleanup."""
    try:
        subprocess.run([
            'Dism.exe',
            '/Online',
            '/Cleanup-Image',
            '/StartComponentCleanup',
            '/ResetBase'
        ], check=True, timeout=1800)  # 30 minutes
        logger.info("DISM cleanup completed")
    except Exception as e:
        logger.error(f"DISM cleanup failed: {e}")
```

#### Use Case for Autopack
**Advanced cleanup** - Run monthly or after Windows updates

---

## Recommended Strategy for Autopack

### Deletion Method Decision Tree

```
File/Folder to Delete
├── Is it a protected path? (C:\Windows, C:\Program Files)
│   └── YES: BLOCK - Never delete
├── Is it larger than 100 MB?
│   └── YES: Require user approval
├── Is safety_level == SAFE?
│   └── YES: Send to Recycle Bin
├── Is safety_level == REVIEW?
│   └── YES: Require user approval → Send to Recycle Bin
└── Is safety_level == DANGEROUS?
    └── YES: BLOCK - Never delete
```

### Implementation

```python
class CleanupExecutor:
    """Safe cleanup executor."""

    def __init__(self, config: StorageOptimizerConfig):
        self.config = config
        self.protected_paths = [
            'C:\\Windows\\System32',
            'C:\\Windows\\WinSxS',
            'C:\\Program Files',
            'C:\\Program Files (x86)',
        ]

    def delete_item(self, candidate: CleanupCandidate) -> CleanupResult:
        """Delete item safely."""
        path = Path(candidate.path)

        # Safety check: protected paths
        if self._is_protected(path):
            return CleanupResult(
                path=str(path),
                success=False,
                error="Protected path - cannot delete"
            )

        # Safety check: dangerous items
        if candidate.safety_level == SafetyLevel.DANGEROUS:
            return CleanupResult(
                path=str(path),
                success=False,
                error="Dangerous item - manual review required"
            )

        # Use recycle bin for safety
        try:
            if self.config.use_recycle_bin and SEND2TRASH_AVAILABLE:
                send2trash(str(path))
                method = "Recycle Bin"
            else:
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
                method = "Permanent"

            logger.info(f"Deleted ({method}): {path} ({candidate.size_gb:.2f} GB)")
            return CleanupResult(
                path=str(path),
                size_freed_bytes=candidate.size_bytes,
                success=True,
                error=None
            )

        except PermissionError as e:
            logger.error(f"Permission denied: {path}")
            return CleanupResult(
                path=str(path),
                success=False,
                error=f"Permission denied: {e}"
            )
        except Exception as e:
            logger.error(f"Failed to delete {path}: {e}")
            return CleanupResult(
                path=str(path),
                success=False,
                error=str(e)
            )

    def _is_protected(self, path: Path) -> bool:
        """Check if path is protected."""
        path_str = str(path).lower()
        return any(path_str.startswith(p.lower()) for p in self.protected_paths)
```

---

## Special Cases

### Windows.old Removal

Windows.old contains the previous Windows installation (~20-30 GB).

**Recommended method**:
```python
def remove_windows_old():
    """Remove Windows.old using Disk Cleanup."""
    try:
        # Use built-in Windows cleanup for Windows.old
        # Safer than manual deletion
        subprocess.run([
            'cleanmgr',
            '/autoclean'
        ], check=True, timeout=600)
    except Exception as e:
        logger.error(f"Failed to remove Windows.old: {e}")
```

**Why not manual deletion?**
- Windows.old has complex permissions
- May contain recovery data
- Disk Cleanup handles it safely

### Locked Files

Files in use can't be deleted.

**Handling strategy**:
```python
def delete_with_retry(path: Path, max_retries: int = 3):
    """Delete file with retry logic."""
    for attempt in range(max_retries):
        try:
            send2trash(str(path))
            return True
        except PermissionError:
            if attempt < max_retries - 1:
                time.sleep(1)  # Wait before retry
            else:
                logger.warning(f"File is locked: {path}")
                return False
```

### Very Large Files (>10 GB)

Large files may prompt user when moving to Recycle Bin.

**Solution**:
```python
def delete_large_file(path: Path, size_gb: float):
    """Delete large file appropriately."""
    if size_gb > 10:
        # Bypass Recycle Bin for very large files
        # (User already approved via Autopack approval workflow)
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        logger.info(f"Permanently deleted large file: {path} ({size_gb:.2f} GB)")
    else:
        send2trash(str(path))
```

---

## Safety Checklist

### Before Deletion
- [ ] Verify path exists
- [ ] Check if path is protected
- [ ] Validate user approval (for REVIEW items)
- [ ] Check available disk space (for Recycle Bin)
- [ ] Log deletion intent

### During Deletion
- [ ] Use appropriate method (Recycle Bin vs permanent)
- [ ] Handle permission errors gracefully
- [ ] Handle locked files
- [ ] Catch and log exceptions

### After Deletion
- [ ] Verify deletion succeeded
- [ ] Log result (success/failure)
- [ ] Update space freed counter
- [ ] Record in database (for audit trail)

---

## Testing Checklist

### send2trash Testing
- [ ] Test with single file
- [ ] Test with folder
- [ ] Test with locked file (should fail gracefully)
- [ ] Test with non-existent path
- [ ] Test with very large file (>10 GB)
- [ ] Test with Unicode filename
- [ ] Verify file appears in Recycle Bin
- [ ] Verify file can be restored from Recycle Bin

### Permanent Deletion Testing
- [ ] Test os.remove() with file
- [ ] Test shutil.rmtree() with folder
- [ ] Test permission errors
- [ ] Test with locked file
- [ ] Verify file is permanently deleted
- [ ] Verify disk space is immediately freed

### Protected Path Testing
- [ ] Test protection prevents C:\Windows deletion
- [ ] Test protection prevents C:\Program Files deletion
- [ ] Test non-protected paths can be deleted
- [ ] Test path protection is case-insensitive

---

## Dependencies

```toml
# pyproject.toml

[project]
dependencies = [
    "send2trash>=1.8.0",  # Recycle Bin deletion
]
```

---

## Conclusion

**Recommended Approach**:

1. **Primary**: `send2trash` (Recycle Bin) - Safe, recoverable
2. **Secondary**: `os.remove` / `shutil.rmtree` - For large files, with user approval
3. **System cleanup**: `cleanmgr.exe` - For Windows.old, Windows Update cleanup
4. **Advanced**: `DISM.exe` - For component store cleanup

**Safety layers**:
- ✅ Protected path checking
- ✅ User approval for large files
- ✅ Safety level classification
- ✅ Recycle Bin by default
- ✅ Comprehensive logging

---

**Status**: Research Complete
**Next**: Implement CleanupExecutor with send2trash + fallback
**Related**: [IMPLEMENTATION_PLAN_STORAGE_OPTIMIZER.md](docs/IMPLEMENTATION_PLAN_STORAGE_OPTIMIZER.md)
