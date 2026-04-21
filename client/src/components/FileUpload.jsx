import React, { useState, useRef } from 'react';
import { api } from '../services/api.js';

export function FileUpload({ courseId, onUploadSuccess }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef(null);

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(e.type === 'dragenter' || e.type === 'dragover');
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFiles(e.dataTransfer.files);
    }
  };

  const handleChange = (e) => {
    if (e.target.files) {
      handleFiles(e.target.files);
    }
  };

  const handleFiles = async (files) => {
    if (files.length === 0) {
      setError('No files selected');
      return;
    }

    setLoading(true);
    setError('');
    setSuccess('');

    try {
      const result = await api.uploadDocuments(courseId, Array.from(files));

      if (result.vectors_added !== undefined) {
        setSuccess(`Successfully uploaded! ${result.vectors_added} vectors added to the knowledge base.`);
        onUploadSuccess?.();
        // Reset file input
        if (fileInputRef.current) fileInputRef.current.value = '';
      } else {
        setError(result.error || 'Upload failed');
      }
    } catch (err) {
      setError(`Error uploading files: ${err.message}`);
      console.error('Upload error:', err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="upload-container">
      <h3>Upload Course Materials</h3>
      <div
        className={`upload-area ${dragActive ? 'active' : ''}`}
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
      >
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".pdf,.docx,.txt,.html"
          onChange={handleChange}
          disabled={loading}
          style={{ display: 'none' }}
        />
        <div className="upload-content">
          <p className="upload-icon">📄</p>
          <p className="upload-text">
            {loading ? 'Uploading...' : 'Drag files here or click to select'}
          </p>
          <p className="upload-hint">Supported: PDF, DOCX, TXT, HTML</p>
        </div>
      </div>

      {error && <div className="error-message">{error}</div>}
      {success && <div className="success-message">{success}</div>}
    </div>
  );
}
