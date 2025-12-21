import React, { useState, useCallback, useRef } from 'react';

export interface FileUploadProgress {
  id: string;
  file: File;
  progress: number;
  status: 'pending' | 'uploading' | 'completed' | 'error';
  error?: string;
}

export interface MultiFileUploadProps {
  onUploadComplete?: (files: FileUploadProgress[]) => void;
  onUploadError?: (error: string) => void;
  maxFiles?: number;
  maxFileSize?: number; // in bytes
  acceptedTypes?: string[];
  uploadEndpoint?: string;
}

export const MultiFileUpload: React.FC<MultiFileUploadProps> = ({
  onUploadComplete,
  onUploadError,
  maxFiles = 10,
  maxFileSize = 50 * 1024 * 1024, // 50MB default
  acceptedTypes = ['*/*'],
  uploadEndpoint = '/api/files/upload',
}) => {
  const [files, setFiles] = useState<FileUploadProgress[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const abortControllersRef = useRef<Map<string, AbortController>>(new Map());

  const generateId = (): string => {
    return `file-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  };

  const validateFile = (file: File): string | null => {
    if (file.size > maxFileSize) {
      return `File "${file.name}" exceeds maximum size of ${formatFileSize(maxFileSize)}`;
    }
    if (acceptedTypes[0] !== '*/*') {
      const fileType = file.type || '';
      const fileExt = file.name.split('.').pop()?.toLowerCase() || '';
      const isAccepted = acceptedTypes.some(type => {
        if (type.startsWith('.')) {
          return fileExt === type.slice(1).toLowerCase();
        }
        if (type.endsWith('/*')) {
          return fileType.startsWith(type.slice(0, -1));
        }
        return fileType === type;
      });
      if (!isAccepted) {
        return `File type "${file.type || fileExt}" is not accepted`;
      }
    }
    return null;
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  const addFiles = useCallback((newFiles: FileList | File[]) => {
    const fileArray = Array.from(newFiles);
    const currentCount = files.length;
    
    if (currentCount + fileArray.length > maxFiles) {
      onUploadError?.(`Maximum ${maxFiles} files allowed`);
      return;
    }

    const newFileProgress: FileUploadProgress[] = [];
    const errors: string[] = [];

    fileArray.forEach(file => {
      const validationError = validateFile(file);
      if (validationError) {
        errors.push(validationError);
      } else {
        newFileProgress.push({
          id: generateId(),
          file,
          progress: 0,
          status: 'pending',
        });
      }
    });

    if (errors.length > 0) {
      onUploadError?.(errors.join('\n'));
    }

    if (newFileProgress.length > 0) {
      setFiles(prev => [...prev, ...newFileProgress]);
    }
  }, [files.length, maxFiles, maxFileSize, acceptedTypes, onUploadError]);

  const removeFile = useCallback((id: string) => {
    const controller = abortControllersRef.current.get(id);
    if (controller) {
      controller.abort();
      abortControllersRef.current.delete(id);
    }
    setFiles(prev => prev.filter(f => f.id !== id));
  }, []);

  const uploadFile = async (fileProgress: FileUploadProgress): Promise<FileUploadProgress> => {
    const controller = new AbortController();
    abortControllersRef.current.set(fileProgress.id, controller);

    try {
      const formData = new FormData();
      formData.append('file', fileProgress.file);

      const xhr = new XMLHttpRequest();
      
      return new Promise((resolve, reject) => {
        xhr.upload.addEventListener('progress', (event) => {
          if (event.lengthComputable) {
            const progress = Math.round((event.loaded / event.total) * 100);
            setFiles(prev => prev.map(f => 
              f.id === fileProgress.id 
                ? { ...f, progress, status: 'uploading' as const }
                : f
            ));
          }
        });

        xhr.addEventListener('load', () => {
          abortControllersRef.current.delete(fileProgress.id);
          if (xhr.status >= 200 && xhr.status < 300) {
            resolve({ ...fileProgress, progress: 100, status: 'completed' });
          } else {
            reject(new Error(`Upload failed with status ${xhr.status}`));
          }
        });

        xhr.addEventListener('error', () => {
          abortControllersRef.current.delete(fileProgress.id);
          reject(new Error('Network error during upload'));
        });

        xhr.addEventListener('abort', () => {
          abortControllersRef.current.delete(fileProgress.id);
          reject(new Error('Upload cancelled'));
        });

        controller.signal.addEventListener('abort', () => {
          xhr.abort();
        });

        xhr.open('POST', uploadEndpoint);
        xhr.send(formData);
      });
    } catch (error) {
      abortControllersRef.current.delete(fileProgress.id);
      throw error;
    }
  };

  const startUpload = useCallback(async () => {
    const pendingFiles = files.filter(f => f.status === 'pending');
    if (pendingFiles.length === 0) return;

    setIsUploading(true);

    const results: FileUploadProgress[] = [];

    for (const fileProgress of pendingFiles) {
      setFiles(prev => prev.map(f => 
        f.id === fileProgress.id 
          ? { ...f, status: 'uploading' as const }
          : f
      ));

      try {
        const result = await uploadFile(fileProgress);
        results.push(result);
        setFiles(prev => prev.map(f => 
          f.id === fileProgress.id 
            ? { ...f, progress: 100, status: 'completed' as const }
            : f
        ));
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : 'Upload failed';
        results.push({ ...fileProgress, status: 'error', error: errorMessage });
        setFiles(prev => prev.map(f => 
          f.id === fileProgress.id 
            ? { ...f, status: 'error' as const, error: errorMessage }
            : f
        ));
      }
    }

    setIsUploading(false);
    onUploadComplete?.(results);
  }, [files, uploadEndpoint, onUploadComplete]);

  const cancelAll = useCallback(() => {
    abortControllersRef.current.forEach(controller => controller.abort());
    abortControllersRef.current.clear();
    setFiles(prev => prev.map(f => 
      f.status === 'uploading' 
        ? { ...f, status: 'error' as const, error: 'Cancelled' }
        : f
    ));
    setIsUploading(false);
  }, []);

  const clearCompleted = useCallback(() => {
    setFiles(prev => prev.filter(f => f.status !== 'completed'));
  }, []);

  const handleDragEnter = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      addFiles(e.dataTransfer.files);
    }
  }, [addFiles]);

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      addFiles(e.target.files);
    }
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  }, [addFiles]);

  const getStatusIcon = (status: FileUploadProgress['status']): string => {
    switch (status) {
      case 'pending': return '⏳';
      case 'uploading': return '📤';
      case 'completed': return '✅';
      case 'error': return '❌';
      default: return '📄';
    }
  };

  const totalProgress = files.length > 0
    ? Math.round(files.reduce((sum, f) => sum + f.progress, 0) / files.length)
    : 0;

  return (
    <div className="multi-file-upload">
      <div
        className={`drop-zone ${isDragging ? 'dragging' : ''}`}
        onDragEnter={handleDragEnter}
        onDragLeave={handleDragLeave}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        style={{
          border: '2px dashed #ccc',
          borderRadius: '8px',
          padding: '40px',
          textAlign: 'center',
          cursor: 'pointer',
          backgroundColor: isDragging ? '#f0f8ff' : '#fafafa',
          transition: 'all 0.2s ease',
        }}
      >
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept={acceptedTypes.join(',')}
          onChange={handleFileSelect}
          style={{ display: 'none' }}
        />
        <div style={{ fontSize: '48px', marginBottom: '16px' }}>📁</div>
        <p style={{ margin: '0 0 8px 0', fontSize: '16px', fontWeight: 500 }}>
          Drag & drop files here or click to browse
        </p>
        <p style={{ margin: 0, fontSize: '14px', color: '#666' }}>
          Maximum {maxFiles} files, up to {formatFileSize(maxFileSize)} each
        </p>
      </div>

      {files.length > 0 && (
        <div className="file-list" style={{ marginTop: '20px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
            <h4 style={{ margin: 0 }}>Files ({files.length})</h4>
            <div style={{ display: 'flex', gap: '8px' }}>
              {files.some(f => f.status === 'completed') && (
                <button
                  onClick={clearCompleted}
                  style={{
                    padding: '6px 12px',
                    border: '1px solid #ccc',
                    borderRadius: '4px',
                    background: 'white',
                    cursor: 'pointer',
                  }}
                >
                  Clear Completed
                </button>
              )}
            </div>
          </div>

          {isUploading && (
            <div style={{ marginBottom: '16px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                <span>Overall Progress</span>
                <span>{totalProgress}%</span>
              </div>
              <div style={{
                width: '100%',
                height: '8px',
                backgroundColor: '#e0e0e0',
                borderRadius: '4px',
                overflow: 'hidden',
              }}>
                <div style={{
                  width: `${totalProgress}%`,
                  height: '100%',
                  backgroundColor: '#4caf50',
                  transition: 'width 0.3s ease',
                }} />
              </div>
            </div>
          )}

          <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
            {files.map(fileProgress => (
              <li
                key={fileProgress.id}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  padding: '12px',
                  borderBottom: '1px solid #eee',
                  gap: '12px',
                }}
              >
                <span style={{ fontSize: '20px' }}>{getStatusIcon(fileProgress.status)}</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    marginBottom: '4px',
                  }}>
                    <span style={{
                      fontWeight: 500,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}>
                      {fileProgress.file.name}
                    </span>
                    <span style={{ color: '#666', fontSize: '14px', marginLeft: '8px'