/**
 * Build verification script for frontend
 * Validates that the build output is complete and ready for Electron packaging
 */

import * as fs from 'fs';
import * as path from 'path';

interface BuildVerificationResult {
  success: boolean;
  errors: string[];
  warnings: string[];
  buildFiles: string[];
}

/**
 * Verify that the build output exists and contains required files
 */
export function verifyBuild(distPath: string = path.join(__dirname, '..', 'dist')): BuildVerificationResult {
  const result: BuildVerificationResult = {
    success: true,
    errors: [],
    warnings: [],
    buildFiles: []
  };

  // Check if dist directory exists
  if (!fs.existsSync(distPath)) {
    result.success = false;
    result.errors.push('Build output directory does not exist: ' + distPath);
    return result;
  }

  // Check if dist directory is not empty
  const files = fs.readdirSync(distPath);
  if (files.length === 0) {
    result.success = false;
    result.errors.push('Build output directory is empty');
    return result;
  }

  result.buildFiles = files;

  // Check for essential files
  const requiredFiles = ['index.html'];
  const missingFiles = requiredFiles.filter(file => !files.includes(file));
  
  if (missingFiles.length > 0) {
    result.warnings.push(`Missing expected files: ${missingFiles.join(', ')}`);
  }

  // Check for JavaScript bundles
  const hasJsFiles = files.some(file => file.endsWith('.js'));
  if (!hasJsFiles) {
    result.warnings.push('No JavaScript bundle files found in build output');
  }

  return result;
}

/**
 * Verify Electron packaging configuration
 */
export function verifyElectronConfig(packageJsonPath: string = path.join(__dirname, '..', 'package.json')): BuildVerificationResult {
  const result: BuildVerificationResult = {
    success: true,
    errors: [],
    warnings: [],
    buildFiles: []
  };

  try {
    const packageJson = JSON.parse(fs.readFileSync(packageJsonPath, 'utf-8'));

    // Check for electron-builder configuration
    if (!packageJson.build) {
      result.errors.push('Missing electron-builder configuration in package.json');
      result.success = false;
    } else {
      // Verify build configuration
      if (!packageJson.build.appId) {
        result.warnings.push('Missing appId in electron-builder configuration');
      }
      if (!packageJson.build.files) {
        result.warnings.push('Missing files array in electron-builder configuration');
      }
    }

    // Check for main entry point
    if (!packageJson.main) {
      result.errors.push('Missing main entry point in package.json');
      result.success = false;
    }

    // Check for required scripts
    const requiredScripts = ['build', 'electron:build'];
    const missingScripts = requiredScripts.filter(script => !packageJson.scripts || !packageJson.scripts[script]);
    
    if (missingScripts.length > 0) {
      result.warnings.push(`Missing recommended scripts: ${missingScripts.join(', ')}`);
    }

  } catch (error) {
    result.success = false;
    result.errors.push(`Failed to read or parse package.json: ${error}`);
  }

  return result;
}

/**
 * Run all build verifications
 */
export function runAllVerifications(): boolean {
  console.log('\n=== Frontend Build Verification ===\n');

  // Verify build output
  console.log('Checking build output...');
  const buildResult = verifyBuild();
  
  if (buildResult.success) {
    console.log('✓ Build output verified');
    console.log(`  Found ${buildResult.buildFiles.length} files:`, buildResult.buildFiles.join(', '));
  } else {
    console.error('✗ Build verification failed');
    buildResult.errors.forEach(err => console.error(`  ERROR: ${err}`));
  }

  buildResult.warnings.forEach(warn => console.warn(`  WARNING: ${warn}`));

  // Verify Electron configuration
  console.log('\nChecking Electron packaging configuration...');
  const configResult = verifyElectronConfig();
  
  if (configResult.success) {
    console.log('✓ Electron configuration verified');
  } else {
    console.error('✗ Electron configuration verification failed');
    configResult.errors.forEach(err => console.error(`  ERROR: ${err}`));
  }

  configResult.warnings.forEach(warn => console.warn(`  WARNING: ${warn}`));

  const overallSuccess = buildResult.success && configResult.success;
  
  console.log('\n=== Verification Summary ===');
  console.log(`Status: ${overallSuccess ? '✓ PASSED' : '✗ FAILED'}`);
  console.log(`Total Errors: ${buildResult.errors.length + configResult.errors.length}`);
  console.log(`Total Warnings: ${buildResult.warnings.length + configResult.warnings.length}`);
  console.log('');

  return overallSuccess;
}

// Run verification if executed directly
if (require.main === module) {
  const success = runAllVerifications();
  process.exit(success ? 0 : 1);
}
