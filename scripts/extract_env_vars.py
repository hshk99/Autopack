import re
from pathlib import Path

env_vars = set()

# Search in src directory
for py_file in Path('src').rglob('*.py'):
    with open(py_file, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
        # Find os.getenv, os.environ patterns
        patterns = [
            r'os\.getenv\(["\']([^"\']+)["\']',
            r'os\.environ\[["\']([^"\']+)["\']',
            r'os\.environ\.get\(["\']([^"\']+)["\']',
        ]
        for pattern in patterns:
            matches = re.findall(pattern, content)
            env_vars.update(matches)

# Also check for Field definitions with validation_alias
for py_file in Path('src').rglob('*.py'):
    with open(py_file, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
        # Find AliasChoices patterns
        alias_pattern = r'AliasChoices\(([^)]+)\)'
        for match in re.finditer(alias_pattern, content):
            vars_str = match.group(1)
            # Extract variable names from AliasChoices
            var_names = re.findall(r'["\']([^"\']+)["\']', vars_str)
            env_vars.update(var_names)

# Filter and sort
filtered_vars = [var for var in sorted(env_vars) if var and len(var) > 2 and var.isupper()]

print(f"Found {len(filtered_vars)} environment variables:")
for var in filtered_vars:
    print(var)
