import React, { useEffect, useState } from 'react';
import { Chat } from './components/Chat.jsx';
import { FileUpload } from './components/FileUpload.jsx';
import { api } from './services/api.js';
import './App.css';

function App() {
  const [studentId, setStudentId] = useState('');
  const [courseId, setCourseId] = useState('');
  const [role, setRole] = useState('student');
  const [mode, setMode] = useState('chat');
  const [isConfigured, setIsConfigured] = useState(false);
  const [isLtiSession, setIsLtiSession] = useState(false);
  const [authLoading, setAuthLoading] = useState(true);

  useEffect(() => {
    async function bootstrapFromLtiSession() {
      try {
        const session = await api.getCurrentUser();
        if (session?.authenticated && session.user) {
          setIsLtiSession(true);
          setStudentId(session.user.user_id || 'lti-user');
          setCourseId(session.user.course_id || 'lti-course');
          setRole(session.user.role || 'student');
          setMode(session.user.role === 'teacher' ? 'upload' : 'chat');
          setIsConfigured(true);
        }
      } catch (err) {
        console.error('LTI session bootstrap failed:', err);
      } finally {
        setAuthLoading(false);
      }
    }

    bootstrapFromLtiSession();
  }, []);

  const handleConfigSubmit = (e) => {
    e.preventDefault();
    if (studentId.trim() && courseId.trim()) {
      setRole('student');
      setIsLtiSession(false);
      setIsConfigured(true);
    }
  };

  const handleReset = async () => {
    if (isLtiSession) {
      await api.logout();
    }
    setIsConfigured(false);
    setIsLtiSession(false);
    setStudentId('');
    setCourseId('');
    setRole('student');
    setMode('chat');
  };

  if (authLoading) {
    return (
      <div className="app-shell app-shell--loading">
        <div className="loading-card">
          <div className="brand-mark" />
          <div>
            <h1>AI Study Buddy</h1>
            <p>Connecting to your course workspace...</p>
          </div>
        </div>
      </div>
    );
  }

  if (!isConfigured) {
    return (
      <div className="app-shell app-shell--setup">
        <div className="setup-card">
          <div className="setup-header">
            <div className="brand-mark" />
            <div>
              <h1>AI Study Buddy</h1>
              <p>Private, course-aware tutoring inside Moodle</p>
            </div>
          </div>

          <form onSubmit={handleConfigSubmit} className="setup-form">
            <div className="form-group">
              <label htmlFor="studentId">Student ID</label>
              <input
                type="text"
                id="studentId"
                value={studentId}
                onChange={(e) => setStudentId(e.target.value)}
                placeholder="Enter your student ID"
                required
              />
            </div>

            <div className="form-group">
              <label htmlFor="courseId">Course ID</label>
              <input
                type="text"
                id="courseId"
                value={courseId}
                onChange={(e) => setCourseId(e.target.value)}
                placeholder="Enter your course ID"
                required
              />
            </div>

            <button type="submit" className="primary-button">
              Open Study Buddy
            </button>
          </form>
        </div>
      </div>
    );
  }

  return (
    <div className="app-shell app-shell--widget">
      <header className="widget-header">
        <div className="widget-title-wrap">
          <div className="brand-mark brand-mark--small" />
          <div>
            <h1>AI Study Buddy</h1>
            <p>
              {courseId ? `Course ${courseId}` : 'Course workspace'} · {role}
            </p>
          </div>
        </div>
        <div className="widget-actions">
          {role === 'teacher' && (
            <button
              className={`tab-button ${mode === 'upload' ? 'active' : ''}`}
              onClick={() => setMode('upload')}
              type="button"
            >
              Upload
            </button>
          )}
          <button onClick={handleReset} className="ghost-button" type="button">
            {isLtiSession ? 'Logout' : 'Reset'}
          </button>
        </div>
      </header>

      <main className="widget-body">
        {mode === 'chat' ? (
          <Chat studentId={studentId} courseId={courseId} />
        ) : (
          <FileUpload
            courseId={courseId}
            onUploadSuccess={() => {
              setMode('chat');
            }}
          />
        )}
      </main>
    </div>
  );
}

export default App;
