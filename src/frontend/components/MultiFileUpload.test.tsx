/**
 * MultiFileUpload component tests
 *
 * Tests file upload component functionality including:
 * - File selection and validation
 * - File size limits
 * - Upload progress tracking
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MultiFileUpload } from './MultiFileUpload';

describe('MultiFileUpload component', () => {
  it('renders drop zone with instructions', () => {
    render(<MultiFileUpload />);
    expect(screen.getByText(/drag & drop files here or click to browse/i)).toBeInTheDocument();
  });

  it('displays maximum file count and size', () => {
    render(<MultiFileUpload maxFiles={5} maxFileSize={10 * 1024 * 1024} />);
    expect(screen.getByText(/maximum 5 files/i)).toBeInTheDocument();
    expect(screen.getByText(/10 mb/i)).toBeInTheDocument();
  });

  it('allows file selection through hidden input', () => {
    render(<MultiFileUpload />);
    const hiddenInput = document.querySelector('input[type="file"]');
    expect(hiddenInput).toBeInTheDocument();
    expect(hiddenInput).toHaveAttribute('multiple');
  });

  it('calls onUploadError when file exceeds size limit', async () => {
    const user = userEvent.setup();
    const onUploadError = vi.fn();
    const maxFileSize = 1024; // 1KB limit

    render(<MultiFileUpload maxFileSize={maxFileSize} onUploadError={onUploadError} />);

    // Create a mock file larger than the limit
    const largeFile = new File(['x'.repeat(2048)], 'large.txt', { type: 'text/plain' });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;

    // Simulate file selection
    Object.defineProperty(input, 'files', {
      value: [largeFile],
      writable: false,
    });

    await user.upload(input, largeFile);

    // Error callback should be called for oversized file
    expect(onUploadError).toHaveBeenCalled();
  });

  it('accepts files within size limit', async () => {
    const user = userEvent.setup();
    const maxFileSize = 10 * 1024 * 1024; // 10MB

    render(<MultiFileUpload maxFileSize={maxFileSize} />);

    const smallFile = new File(['test content'], 'test.txt', { type: 'text/plain' });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;

    Object.defineProperty(input, 'files', {
      value: [smallFile],
      writable: false,
    });

    await user.upload(input, smallFile);

    // File should be added to the list (check for file list UI)
    expect(screen.getByText(/files \(1\)/i)).toBeInTheDocument();
  });

  it('respects maxFiles limit', async () => {
    const user = userEvent.setup();
    const onUploadError = vi.fn();
    const maxFiles = 2;

    render(<MultiFileUpload maxFiles={maxFiles} onUploadError={onUploadError} />);

    const files = [
      new File(['content1'], 'file1.txt', { type: 'text/plain' }),
      new File(['content2'], 'file2.txt', { type: 'text/plain' }),
      new File(['content3'], 'file3.txt', { type: 'text/plain' }),
    ];

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;

    Object.defineProperty(input, 'files', {
      value: files,
      writable: false,
    });

    await user.upload(input, files);

    // Should call error handler because we exceed maxFiles
    expect(onUploadError).toHaveBeenCalledWith(expect.stringContaining('Maximum 2 files'));
  });
});
