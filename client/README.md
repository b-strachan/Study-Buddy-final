# Study Buddy UI

A modern React-based frontend for the Study Buddy AI learning assistant API.

## Features

- 💬 **Real-time Chat**: Stream AI responses as they're generated
- 📤 **File Upload**: Upload course materials (PDF, DOCX, TXT, HTML)
- 🎓 **Multi-tenant**: Support for multiple students and courses
- 📱 **Responsive Design**: Works on desktop and mobile devices
- ⚡ **Fast**: Built with Vite for optimal performance

## Prerequisites

- Node.js 16+ and npm
- Study Buddy backend API running on `http://localhost:8000`

## Installation

```bash
cd client
npm install
```

## Development

Start the development server:

```bash
npm run dev
```

The app will be available at `http://localhost:5173` (or `http://localhost:3000` if port 5173 is in use).

The dev server includes a proxy to the backend API, so you can make requests to `/api/*` endpoints.

## Building for Production

```bash
npm run build
```

This creates an optimized production build in the `dist/` directory.

Preview the production build:

```bash
npm run preview
```

## How to Use

1. **Enter Course Details**: On startup, enter your Student ID and Course ID
2. **Upload Materials**: Switch to the "Upload Materials" tab and upload course documents (PDF, DOCX, etc.)
3. **Ask Questions**: In the Chat tab, ask questions about your course materials
4. **Get Answers**: The AI will retrieve relevant course content and provide helpful explanations

## API Integration

The UI communicates with the Study Buddy backend via:

- `POST /api/v1/chat` - Chat with streaming responses (Server-Sent Events)
- `POST /api/v1/teacher/upload` - Upload course materials
- `GET /health` - Health check

## Architecture

```
src/
├── components/
│   ├── Chat.jsx         # Chat interface with message display
│   └── FileUpload.jsx   # File upload component
├── services/
│   └── api.js           # API client and SSE streaming
├── App.jsx              # Main app component
├── App.css              # Styling
└── main.jsx             # React entry point
```

## Technologies

- **React 18** - UI framework
- **Vite** - Build tool and dev server
- **CSS3** - Styling with gradients and animations
- **Server-Sent Events** - Real-time streaming responses

## Troubleshooting

### Backend Connection Error

Make sure the Study Buddy API is running on `http://localhost:8000`:

```bash
# In the backend directory
python -m uvicorn app.main:app --reload
```

### Port Already in Use

If port 5173 is already in use, Vite will automatically try the next available port. Check the terminal output for the actual port.

### CORS Issues

If you encounter CORS errors, ensure the backend has CORS middleware enabled for `http://localhost:3000` and `http://localhost:5173`.

## Contributing

This is a demo frontend for the Study Buddy API. Feel free to modify styling, add features, or improve the user interface.

## License

Same as Study Buddy main project
