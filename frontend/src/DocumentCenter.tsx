import { useCallback, useEffect, useState, type FormEvent } from 'react'

type User = { id: number; full_name: string; email: string; role: string }
type CourseOption = { id: number; code: string; title: string; level: string | null }
type Doc = {
  id: number; title: string; description?: string | null; original_filename: string
  file_size: number; page_count: number; uploaded_by_id: number; course_id?: number | null
  visibility: 'course' | 'department' | 'faculty' | 'university' | 'private'
  status: 'draft' | 'pending_review' | 'verified' | 'rejected' | 'superseded'
  created_at: string; updated_at: string; relevance?: string | null
}
type Review = { id: number; document_id: number; reviewer_id: number; action: string; comments?: string | null; created_at: string }
type Page = 'home' | 'login' | 'signup' | 'forgot' | 'reset' | 'verify' | 'catalog' | 'dashboard' | 'profile' | 'documents'
const API_BASE = (import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000').replace(/\/$/, '')

async function request<T>(path: string, token: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers)
  headers.set('Authorization', `Bearer ${token}`)
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    const detail = body?.detail
    const message = Array.isArray(detail) ? detail.map((x: { msg?: string }) => x.msg).filter(Boolean).join('; ')
      : typeof detail === 'string' ? detail : 'The request could not be completed. Please try again.'
    throw new Error(message)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

const statusLabel: Record<Doc['status'], string> = {
  draft: 'Draft', pending_review: 'Pending review', verified: 'Verified',
  rejected: 'Rejected', superseded: 'Superseded',
}
const formatDate = (value: string) => new Date(value).toLocaleString()
const formatBytes = (value: number) => value < 1024 * 1024 ? `${(value / 1024).toFixed(0)} KB` : `${(value / (1024 * 1024)).toFixed(1)} MB`

export default function DocumentCenter({ user, token, onNavigate }: {
  user: User | null; token: string | null; onNavigate: (page: Page) => void
}) {
  const [mine, setMine] = useState<Doc[]>([])
  const [published, setPublished] = useState<Doc[]>([])
  const [courses, setCourses] = useState<CourseOption[]>([])
  const [queue, setQueue] = useState<Doc[]>([])
  const [selected, setSelected] = useState<Doc | null>(null)
  const [reviews, setReviews] = useState<Review[]>([])
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [courseId, setCourseId] = useState('')
  const [visibility, setVisibility] = useState<Doc['visibility']>('course')
  const [reviewComment, setReviewComment] = useState('')
  const [reviewAction, setReviewAction] = useState<'approve' | 'reject' | 'request_correction'>('approve')
  const [permissionUser, setPermissionUser] = useState('')
  const [permission, setPermission] = useState<'view' | 'download' | 'edit'>('view')
  const [versionFile, setVersionFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [verificationRequired, setVerificationRequired] = useState(false)
  const isReviewer = user?.role === 'department_reviewer' || user?.role === 'administrator'
  const isLecturer = user?.role === 'lecturer'
  const isStudent = user?.role === 'student'
  const canUpload = isLecturer

  const load = useCallback(async () => {
    if (!token) return
    setError(''); setVerificationRequired(false)
    try {
      const [publishedResult, mineResult, lecturerProfile, courseResult] = await Promise.all([
        request<Doc[]>('/api/documents/published', token),
        isStudent ? Promise.resolve([] as Doc[]) : request<Doc[]>('/api/documents/mine', token),
        isLecturer
          ? request<{ assigned_course_ids: number[] }>('/api/lecturers/me', token)
          : Promise.resolve(null),
        isLecturer
          ? request<{ items: CourseOption[] }>('/api/academic/courses?skip=0&limit=200', token)
          : Promise.resolve({ items: [] as CourseOption[] }),
      ])
      setPublished(publishedResult)
      setMine(mineResult)
      const assignedCourseIds = new Set(lecturerProfile?.assigned_course_ids || [])
      setCourses(courseResult.items.filter(course => assignedCourseIds.has(course.id)))
      if (isReviewer) setQueue(await request<Doc[]>('/api/documents/review-queue', token))
      else setQueue([])
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Could not load documents.'
      setError(message)
      setVerificationRequired(message.toLowerCase().includes('verify your academic affiliation'))
    }
  }, [token, isReviewer, isStudent, isLecturer])

  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { void load() }, [load])

  async function upload(e: FormEvent) {
    e.preventDefault()
    if (!token || !file) { setError('Choose a PDF file before uploading.'); return }
    if (!courseId) { setError('Choose one of your assigned courses before uploading.'); return }
    if (file.type !== 'application/pdf' && !file.name.toLowerCase().endsWith('.pdf')) {
      setError('Only PDF files are accepted.'); return
    }
    const body = new FormData()
    body.append('title', title.trim())
    if (description.trim()) body.append('description', description.trim())
    body.append('course_id', courseId)
    body.append('visibility', visibility)
    body.append('file', file)
    setBusy(true); setError(''); setNotice('')
    try {
      const created = await request<Doc>('/api/documents/upload', token, { method: 'POST', body })
      setNotice(`“${created.title}” uploaded. Current status: ${statusLabel[created.status]}.`)
      setTitle(''); setDescription(''); setFile(null); setCourseId(''); setVisibility('course')
      const form = document.getElementById('document-upload-form') as HTMLFormElement | null
      form?.reset()
      await load()
    } catch (e) { setError(e instanceof Error ? e.message : 'Upload failed.') }
    finally { setBusy(false) }
  }

  async function submitForReview(doc: Doc) {
    if (!token) return
    setBusy(true); setError(''); setNotice('')
    try {
      await request<Doc>(`/api/documents/${doc.id}/submit`, token, { method: 'POST' })
      setNotice(`“${doc.title}” was submitted for review.`); await load()
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not submit document.') }
    finally { setBusy(false) }
  }

  async function openDetails(doc: Doc) {
    if (!token) return
    setSelected(doc); setReviews([]); setError('')
    try {
      const [detail, history] = await Promise.all([
        request<Doc>(`/api/documents/${doc.id}`, token),
        request<Review[]>(`/api/documents/${doc.id}/reviews`, token),
      ])
      setSelected(detail); setReviews(history)
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not load document details.') }
  }

  async function reviewDocument(e: FormEvent) {
    e.preventDefault()
    if (!token || !selected) return
    if (reviewAction !== 'approve' && !reviewComment.trim()) {
      setError('A comment is required when rejecting or requesting corrections.'); return
    }
    const body = new FormData()
    body.append('action', reviewAction)
    if (reviewComment.trim()) body.append('comments', reviewComment.trim())
    setBusy(true); setError(''); setNotice('')
    try {
      await request<Review>(`/api/documents/${selected.id}/review`, token, { method: 'POST', body })
      setNotice(`Review decision saved for “${selected.title}”.`)
      setReviewComment(''); setSelected(null); await load()
    } catch (e) { setError(e instanceof Error ? e.message : 'Review action failed.') }
    finally { setBusy(false) }
  }

  async function grantPermission(e: FormEvent) {
    e.preventDefault()
    if (!token || !selected) return
    const id = Number(permissionUser)
    if (!Number.isInteger(id) || id < 1) { setError('Enter a valid user ID.'); return }
    const body = new FormData()
    body.append('user_id', String(id)); body.append('permission', permission)
    setBusy(true); setError(''); setNotice('')
    try {
      await request(`/api/documents/${selected.id}/permissions`, token, { method: 'POST', body })
      setNotice(`${permission} permission saved for user ${id}.`)
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not save permission.') }
    finally { setBusy(false) }
  }

  async function uploadVersion(e: FormEvent) {
    e.preventDefault()
    if (!token || !selected || !versionFile) { setError('Choose a replacement PDF first.'); return }
    const body = new FormData(); body.append('file', versionFile)
    setBusy(true); setError(''); setNotice('')
    try {
      const updated = await request<Doc>(`/api/documents/${selected.id}/versions`, token, { method: 'POST', body })
      setSelected(updated); setVersionFile(null)
      setNotice('New version uploaded. The document has returned to pending review.')
      await load()
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not upload new version.') }
    finally { setBusy(false) }
  }

  async function download(doc: Doc) {
    if (!token) return
    setBusy(true); setError('')
    try {
      const response = await fetch(`${API_BASE}/api/documents/${doc.id}/download`, { headers: { Authorization: `Bearer ${token}` } })
      if (!response.ok) {
        const body = await response.json().catch(() => ({}))
        throw new Error(typeof body?.detail === 'string' ? body.detail : 'Download failed.')
      }
      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url; anchor.download = doc.original_filename || `${doc.title}.pdf`
      document.body.appendChild(anchor); anchor.click(); anchor.remove()
      URL.revokeObjectURL(url)
    } catch (e) { setError(e instanceof Error ? e.message : 'Download failed.') }
    finally { setBusy(false) }
  }

  if (!token) return <section className="page-container inner-page"><h1 className="inner-title">Document centre<span>.</span></h1><p>Sign in to manage academic documents.</p><button className="button" onClick={() => onNavigate('login')}>Sign in</button></section>

  return <section className="page-container inner-page doc-center">
    <div className="page-kicker">ACADEMIC MATERIALS</div>
    <h1 className="inner-title">Document centre<span>.</span></h1>
    <p className="inner-lede">{isStudent ? 'Browse approved academic materials, with your department and level resources shown first.' : 'Upload, review and manage academic documents. Access is controlled by your account role and each document’s permissions.'}</p>
    {error && <div className="form-alert form-error doc-alert" role="alert">{error}</div>}
    {notice && <div className="form-alert form-success doc-alert" role="status">{notice}</div>}
    {isStudent && verificationRequired && <div className="form-alert form-warning doc-alert">Verify your university, faculty, department, programme and level before browsing approved materials. <button className="text-button" onClick={() => onNavigate('profile')}>Open academic affiliation settings</button></div>}
    {isStudent ? <div className="doc-panel"><div className="doc-toolbar"><div><h2>Approved learning materials</h2><p>Only documents approved for publication are shown.</p></div><button className="button button-outline" onClick={() => void load()} disabled={busy}>Refresh</button></div>{published.length ? <div className="doc-list">{published.map(doc => <DocumentRow key={doc.id} doc={doc} busy={busy} onDetails={openDetails} onDownload={download} onSubmit={submitForReview}/>)}</div> : <div className="empty-preview"><b>No approved materials are available yet.</b><p>Published documents will appear here after an authorised lecturer or reviewer approves them.</p></div>}</div> :
      <><div className="doc-toolbar"><div><h2>My documents</h2><p>Documents you uploaded.</p></div><button className="button button-outline" onClick={() => void load()} disabled={busy}>Refresh</button></div>
      {mine.length ? <div className="doc-list">{mine.map(doc => <DocumentRow key={doc.id} doc={doc} busy={busy} onDetails={openDetails} onDownload={download} onSubmit={submitForReview}/>)}</div> : <div className="empty-preview"><b>No documents uploaded yet.</b><p>Your uploads and their review status will appear here.</p></div>}</>}

    {!isStudent && published.length > 0 && <div className="doc-panel"><div className="doc-toolbar"><div><h2>Published materials</h2><p>Approved documents visible to students.</p></div></div><div className="doc-list">{published.map(doc => <DocumentRow key={`published-${doc.id}`} doc={doc} busy={busy} onDetails={openDetails} onDownload={download} onSubmit={submitForReview}/>)}</div></div>}

    {canUpload && <div className="doc-panel"><h2>Upload academic material</h2><p>PDF only. Uploads stay private until an assigned reviewer or administrator approves them.</p>
      <form id="document-upload-form" className="doc-form" onSubmit={upload}>
        <label>Document title<input value={title} onChange={e => setTitle(e.target.value)} required minLength={2} maxLength={200} placeholder="e.g. COS 101 Lecture Notes"/></label>
        <label>Description (optional)<textarea value={description} onChange={e => setDescription(e.target.value)} rows={3} maxLength={2000} placeholder="Briefly describe this material"/></label>
        <label>Assigned course<select required value={courseId} onChange={e => setCourseId(e.target.value)}><option value="">Select a course</option>{courses.map(course => <option key={course.id} value={course.id}>{course.code} · {course.title}{course.level ? ` · ${course.level}` : ''}</option>)}</select></label>
        <label>Who can access this material<select value={visibility} onChange={e => setVisibility(e.target.value as Doc['visibility'])}><option value="course">Enrolled students in this course</option><option value="department">Students in this department</option><option value="faculty">Students in this faculty</option><option value="university">Students in this university</option><option value="private">Only people explicitly granted access</option></select></label>
        {!courses.length && <p className="form-alert form-warning">No courses are assigned to your lecturer account. Ask an administrator to assign your courses before uploading materials.</p>}
        <label>PDF file<input type="file" accept="application/pdf,.pdf" required onChange={e => setFile(e.target.files?.[0] || null)}/></label>
        <button className="button" disabled={busy || !file || !courseId}>{busy ? 'Working…' : 'Upload PDF'}</button>
      </form>
    </div>}

    {isReviewer && <div className="doc-panel"><div className="doc-toolbar"><div><h2>Reviewer queue</h2><p>Pending documents awaiting a decision.</p></div><span className="doc-count">{queue.length} pending</span></div>
      {queue.length ? <div className="doc-list">{queue.map(doc => <DocumentRow key={doc.id} doc={doc} busy={busy} onDetails={openDetails} onDownload={download} onSubmit={submitForReview} reviewer/>)}</div> : <div className="notice">There are no documents waiting for review.</div>}
    </div>}

    {selected && <div className="doc-modal-backdrop" role="presentation" onMouseDown={e => { if (e.target === e.currentTarget) setSelected(null) }}>
      <section className="doc-modal" role="dialog" aria-modal="true" aria-labelledby="doc-modal-title">
        <div className="doc-modal-head"><div><div className="page-kicker">DOCUMENT DETAILS</div><h2 id="doc-modal-title">{selected.title}</h2></div><button className="icon-button" onClick={() => setSelected(null)} aria-label="Close">×</button></div>
        <p className="doc-muted">{selected.description || 'No description provided.'}</p>
        <div className="doc-meta"><span>ID: {selected.id}</span><span>{selected.page_count} pages</span><span>{formatBytes(selected.file_size)}</span><span>Uploaded: {formatDate(selected.created_at)}</span></div>
        <p><b>Status:</b> <span className={`status-pill status-${selected.status}`}>{statusLabel[selected.status]}</span></p>
        <button className="button button-outline" disabled={busy} onClick={() => void download(selected)}>Download PDF</button>
        <h3>Review history</h3>
        {reviews.length ? <ul className="review-history">{reviews.map(r => <li key={r.id}><b>{r.action.replaceAll('_', ' ')}</b><span>{r.comments || 'No comment'}</span><small>Reviewer {r.reviewer_id} · {formatDate(r.created_at)}</small></li>)}</ul> : <p className="doc-muted">No review decisions recorded.</p>}
        {isReviewer && selected.status === 'pending_review' && <form className="doc-form doc-action-form" onSubmit={reviewDocument}>
          <h3>Record review decision</h3>
          <label>Decision<select value={reviewAction} onChange={e => setReviewAction(e.target.value as typeof reviewAction)}><option value="approve">Approve</option><option value="reject">Reject</option><option value="request_correction">Request correction</option></select></label>
          <label>Comments{reviewAction !== 'approve' ? ' (required)' : ' (optional)'}<textarea rows={3} value={reviewComment} onChange={e => setReviewComment(e.target.value)} placeholder="Add a note for the uploader"/></label>
          <button className="button" disabled={busy}>Save review decision</button>
        </form>}
        {isReviewer && <form className="doc-form doc-action-form" onSubmit={grantPermission}>
          <h3>Grant document permission</h3>
          <label>Recipient user ID<input type="number" min="1" value={permissionUser} onChange={e => setPermissionUser(e.target.value)} required/></label>
          <label>Permission<select value={permission} onChange={e => setPermission(e.target.value as typeof permission)}><option value="view">View</option><option value="download">Download</option><option value="edit">Edit</option></select></label>
          <button className="button button-outline" disabled={busy}>Save permission</button>
        </form>}
        {(selected.uploaded_by_id === user?.id || isReviewer) && <form className="doc-form doc-action-form" onSubmit={uploadVersion}>
          <h3>Upload a new version</h3><p className="doc-muted">A new version sends the document back for review.</p>
          <label>Replacement PDF<input type="file" accept="application/pdf,.pdf" required onChange={e => setVersionFile(e.target.files?.[0] || null)}/></label>
          <button className="button button-outline" disabled={busy || !versionFile}>Upload new version</button>
        </form>}
      </section>
    </div>}
  </section>
}

function DocumentRow({ doc, busy, onDetails, onDownload, onSubmit, reviewer = false }: {
  doc: Doc; busy: boolean; reviewer?: boolean; onDetails: (doc: Doc) => void
  onDownload: (doc: Doc) => void; onSubmit: (doc: Doc) => void
}) {
  return <article className="doc-row">
    <div className="doc-file-icon">PDF</div>
    <div className="doc-row-main"><b>{doc.title}</b><span>{doc.original_filename} · {doc.page_count} pages · {formatBytes(doc.file_size)}</span><small>{formatDate(doc.updated_at)}</small>{doc.relevance && <small className="relevance-tag">{doc.relevance}</small>}</div>
    <span className={`status-pill status-${doc.status}`}>{statusLabel[doc.status]}</span>
    <div className="doc-row-actions"><button className="text-button" onClick={() => onDetails(doc)}>Details</button>
      {doc.status === 'verified' && <button className="text-button" disabled={busy} onClick={() => void onDownload(doc)}>Download</button>}
      {!reviewer && (doc.status === 'draft' || doc.status === 'rejected') && <button className="text-button" disabled={busy} onClick={() => void onSubmit(doc)}>Submit</button>}
    </div>
  </article>
}
