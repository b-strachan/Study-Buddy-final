const API_BASE = import.meta.env.DEV ? 'http://localhost:8000' : window.location.origin;

export const api = {
  // Health check
  async checkHealth() {
    const response = await fetch(`${API_BASE}/health`, {
      credentials: 'include'
    });
    return response.json();
  },

  async getCurrentUser() {
    const response = await fetch(`${API_BASE}/api/lti/me`, {
      credentials: 'include'
    });
    return response.json();
  },

  async logout() {
    const response = await fetch(`${API_BASE}/api/lti/logout`, {
      method: 'POST',
      credentials: 'include'
    });
    return response.json();
  },

  // Chat with streaming
  async chatStream(studentId, courseId, query, modelName = 'ollama/llama3', apiBase = 'http://host.docker.internal:11434') {
    return fetch(`${API_BASE}/api/v1/chat`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        student_id: studentId,
        course_id: courseId,
        query: query,
        model_name: modelName,
        api_base: apiBase
      })
    });
  },

  // Upload documents
  async uploadDocuments(courseId, files) {
    const formData = new FormData();
    formData.append('course_id', courseId);

    files.forEach(file => {
      formData.append('files', file);
    });

    const response = await fetch(`${API_BASE}/api/v1/teacher/upload`, {
      method: 'POST',
      credentials: 'include',
      body: formData
    });

    return response.json();
  }
};

// Helper to read SSE stream
export async function* readSSEStream(response) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    const chunk = decoder.decode(value, { stream: true });
    const lines = chunk.split('\n');


    let emitted = false;
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const data = line.slice(6);
        if (data) {
          emitted = true;
          yield data;
        }
      }
    }

    // Fallback for plain chunked text streams that are not SSE-formatted.
    if (!emitted && chunk.trim()) {
      yield chunk;
    }
  }
}
