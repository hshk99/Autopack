"""Fix quality_gate import issues by commenting out all references."""
from pathlib import Path

def fix_quality_gate_refs():
    """Comment out quality_gate references that cause import errors."""

    file_path = Path("src/autopack/autonomous_executor.py")

    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    modified = []
    in_quality_gate_block = False
    block_indent = 0

    for i, line in enumerate(lines):
        line_num = i + 1

        # Comment out import
        if line_num == 44 and 'from autopack.quality_gate import QualityGate' in line:
            modified.append('# from autopack.quality_gate import QualityGate  # BUILD-126: Phase G not complete yet\n')
            print(f"Line {line_num}: Commented import")
            continue

        # Comment out initialization (line 1030)
        if line_num == 1030 and 'self.quality_gate = QualityGate(' in line:
            modified.append('            # self.quality_gate = QualityGate(repo_root=self.workspace)  # BUILD-126: Phase G not complete\n')
            print(f"Line {line_num}: Commented initialization")
            continue

        if line_num == 1031 and 'Quality Gate: Initialized' in line:
            modified.append('            # logger.info("Quality Gate: Initialized")  # BUILD-126: Phase G not complete\n')
            print(f"Line {line_num}: Commented log message")
            continue

        # Start of quality gate block (line 4417-4471)
        if line_num == 4417 and '# Step 5: Apply Quality Gate' in line:
            in_quality_gate_block = True
            block_indent = len(line) - len(line.lstrip())
            modified.append(line.replace('# Step 5:', '# BUILD-126: Step 5: Quality Gate disabled - Phase G not complete yet\n            # Step 5:'))
            print(f"Line {line_num}: Start quality gate block")
            continue

        # In quality gate block
        if in_quality_gate_block:
            current_indent = len(line) - len(line.lstrip())

            # End of block when we hit line 4473 or lower indent
            if line_num >= 4473 and (current_indent <= block_indent or '# Update phase status to COMPLETE' in line):
                in_quality_gate_block = False
                modified.append(line)
                print(f"Line {line_num}: End quality gate block")
                continue

            # Comment out lines in block
            if line.strip():  # Non-empty line
                modified.append('            # ' + line.lstrip())
            else:
                modified.append(line)
            continue

        # Keep all other lines unchanged
        modified.append(line)

    # Write back
    with open(file_path, 'w', encoding='utf-8') as f:
        f.writelines(modified)

    print(f"\n✓ Fixed quality_gate references in {file_path}")
    print("  - Commented import at line 44")
    print("  - Commented initialization at line 1030-1031")
    print("  - Commented quality gate block at lines 4417-4472")

if __name__ == "__main__":
    fix_quality_gate_refs()
