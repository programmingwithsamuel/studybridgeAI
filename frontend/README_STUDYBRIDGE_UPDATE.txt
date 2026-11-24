STUDYBRIDGE AI FRONTEND UPDATE

This package adds a Document Centre to the existing React/Vite frontend.

Included:
- Student document list and PDF upload
- Draft/rejected document submission for review
- Reviewer queue for department_reviewer and administrator roles
- Document details and review history
- Approve, reject, and request-correction actions
- Grant view/download/edit permission to a user ID
- Download approved PDFs (backend permission checks remain authoritative)
- Upload a new document version (returns document to pending_review)

IMPORTANT LIMITATIONS:
- This frontend uses the existing backend endpoints. It does not replace backend files.
- Reviewer access is currently role-based globally. Department-specific reviewer assignment must be implemented and enforced in the backend before production use.
- The permission form asks for a user ID because the current backend has no user-search endpoint.
- Version history is uploaded through the existing endpoint, but the backend currently has no endpoint to list/download older versions.
- AI tutoring, course-resource search, and full library discovery are not implemented in this update.

INSTALL:
1. Stop the frontend dev server (Ctrl+C).
2. Back up your current frontend folder.
3. Extract this package. Copy its src folder and package.json/package-lock.json into C:\studybridgeAi\frontend, replacing the matching files.
4. Do NOT copy node_modules, dist, or any .env file from an old archive.
5. In PowerShell:
   cd C:\studybridgeAi\frontend
   npm.cmd ci
   npm.cmd run build
   npm.cmd run lint
   npm.cmd run dev
6. Open http://localhost:5173 and sign in.

API CONFIGURATION:
The app defaults to http://127.0.0.1:8000. If needed, create your own frontend/.env.local with:
VITE_API_URL=http://127.0.0.1:8000
Do not put API keys, passwords, or private backend secrets in a VITE_ variable.

TESTING:
- Student: Documents -> upload a small valid PDF -> Submit when status is draft -> verify status updates.
- Reviewer: sign in as department_reviewer -> Documents -> open a pending item -> approve/reject/request correction.
- Permission: reviewer opens verified document -> grant permission using target user ID.
- Download: test with an account that has download/edit permission or is the uploader/reviewer as allowed by backend rules.

QUALITY NOTES:
TypeScript project build check (tsc -b) passed in the inspection environment.
ESLint passed for App.tsx, DocumentCenter.tsx, and main.tsx.
The Vite production bundler could not be executed in the Linux inspection environment because the archive contains Windows-installed optional native Rolldown dependencies. Run npm.cmd ci and npm.cmd run build on the target Windows machine to verify the platform-native production bundle.
