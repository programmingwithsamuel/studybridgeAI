# Document access policy

Document listings, details, downloads, review previews, and academic-chat retrieval use the same backend access check.

## Visibility scopes

Lecturers choose a scope when uploading a document:

- `course`: students must have a verified academic affiliation whose selected programme includes the document course.
- `department`: the student's verified department must match the course department.
- `faculty`: the student's verified faculty must match the course faculty.
- `university`: the student's verified university must match the course university.
- `private`: only users with an explicit document permission can view it.

For student access, a course's configured academic level must match the student's verified level. Access is checked before relevance ranking: enrolled-course material ranks first, followed by department, faculty, and university material.

The current project has no separate per-student course-enrolment table. Course access therefore uses the existing `AcademicAffiliation.programme_id` and `ProgrammeCourse` curriculum mapping as its membership source. This represents programme curriculum membership, not individual semester registration.

Explicit `view`, `download`, and `edit` permissions grant access only to active, approved documents. A `view` permission does not grant download access. Owners, administrators, and assigned reviewers retain the existing management/review access. Unapproved and withdrawn material is excluded from ordinary student access and AI retrieval.

## Existing database upgrade

On startup, the backend adds the `documents.visibility` column if it is missing. Existing documents receive the conservative `course` scope; no document files or rows are deleted. Ensure a verified `ProgrammeCourse` row exists for each course that should be visible to students in a programme.

Retrieved document text is sent as quoted, untrusted reference data. The Gemini provider also receives a separate system instruction that forbids following instructions found in document excerpts or conversation history.
