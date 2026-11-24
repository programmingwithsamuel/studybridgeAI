import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import './App.css'
import DocumentCenter from './DocumentCenter'

type User = { id: number; full_name: string; email: string; role: string; is_active: boolean; created_at: string }
type Course = { id: number; code: string; title: string; level?: string | null; semester?: string | null; credit_units?: number | null; department_id: number; department_assignment_status?: string; topics?: { id: number; title: string; description?: string | null; position: number }[] }
type Page = 'home' | 'login' | 'signup' | 'forgot' | 'reset' | 'verify' | 'lecturer-activate' | 'catalog' | 'dashboard' | 'profile' | 'documents' | 'lecturer' | 'admin' | 'admin-members' | 'admin-activity' | 'chat'
const API_BASE = (import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000').replace(/\/$/, '')
const TOKEN_KEY = 'studybridge_access_token'
const THEME_KEY = 'studybridge_theme'

async function api<T>(path: string, options: RequestInit = {}, token?: string): Promise<T> {
  const headers = new Headers(options.headers)
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = data?.detail
    if (typeof detail === 'string') throw new Error(detail)
    if (detail && typeof detail === 'object' && 'message' in detail) {
      const error = new Error(String(detail.message)) as Error & { suggestedEmail?: string; enteredEmail?: string }
      error.suggestedEmail = typeof detail.suggested_email === 'string' ? detail.suggested_email : undefined
      error.enteredEmail = typeof detail.entered_email === 'string' ? detail.entered_email : undefined
      throw error
    }
    throw new Error('Request failed. Please try again.')
  }
  return data as T
}

function Icon({ name }: { name: string }) {
  const paths: Record<string, string> = {
    book: 'M4 5.5A2.5 2.5 0 0 1 6.5 3H20v17H6.5A2.5 2.5 0 0 0 4 22V5.5ZM4 18.5A2.5 2.5 0 0 1 6.5 16H20',
    spark: 'm12 3 1.9 5.8L20 11l-6.1 2.2L12 19l-1.9-5.8L4 11l6.1-2.2L12 3Z',
    shield: 'M12 22s8-4 8-11V5l-8-3-8 3v6c0 7 8 11 8 11Z',
    search: 'm21 21-4.3-4.3M19 10.5a8.5 8.5 0 1 1-17 0 8.5 8.5 0 0 1 17 0Z',
    moon: 'M20.9 13A9 9 0 0 1 11 3.1 9 9 0 1 0 20.9 13Z',
    sun: 'M12 3v2m0 14v2M3 12h2m14 0h2M5.6 5.6 7 7m10 10 1.4 1.4m0-12.8L17 7M7 17l-1.4 1.4M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z',
    arrow: 'M5 12h14m-6-6 6 6-6 6',
    check: 'm5 12 4 4L19 6',
    menu: 'M4 6h16M4 12h16M4 18h16',
    close: 'm18 6-12 12M6 6l12 12',
    user: 'M20 21a8 8 0 0 0-16 0m8-10a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z',
    lock: 'M5 11h14v10H5zM8 11V7a4 4 0 1 1 8 0v4',
    upload: 'M12 16V4m-5 5 5-5 5 5M4 20h16',
  }
  return <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name] || paths.spark} /></svg>
}

function App() {
  const [page, setPage] = useState<Page>(() => {
    const path = window.location.pathname.replace(/^\//, '')
    if (path === 'reset-password') return 'reset'
    if (path === 'verify-email') return 'verify'
    if (path === 'lecturer-activate') return 'lecturer-activate'
    return 'home'
  })
  const [theme, setTheme] = useState<'light' | 'dark'>(() => (localStorage.getItem(THEME_KEY) as 'light' | 'dark') || 'light')
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_KEY))
  const [user, setUser] = useState<User | null>(null)
  const [courses, setCourses] = useState<Course[]>([])
  const [courseLoading, setCourseLoading] = useState(false)
  const [courseError, setCourseError] = useState('')
  const [mobileOpen, setMobileOpen] = useState(false)

  useEffect(() => { document.documentElement.dataset.theme = theme; localStorage.setItem(THEME_KEY, theme) }, [theme])
  useEffect(() => {
    if (!token) return
    api<User>('/api/auth/me', {}, token).then(setUser).catch(() => { localStorage.removeItem(TOKEN_KEY); setToken(null); setUser(null) })
  }, [token])
  useEffect(() => {
    if (page !== 'catalog' && page !== 'home') return
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setCourseLoading(true); setCourseError('')
    api<{ items: Course[] }>('/api/academic/courses?skip=0&limit=100')
      .then(result => setCourses(result.items || []))
      .catch(() => setCourseError('The academic catalogue is temporarily unavailable. You can still explore the public StudyBridge pages.'))
      .finally(() => setCourseLoading(false))
  }, [page])

  const navigate = (next: Page) => { setPage(next); setMobileOpen(false); window.scrollTo({ top: 0, behavior: 'smooth' }) }
  const signOut = () => {
    if (token) void api('/api/auth/logout', { method: 'POST' }, token).catch(() => undefined)
    localStorage.removeItem(TOKEN_KEY)
    setToken(null)
    setUser(null)
    navigate('home')
  }
  const onAuthenticated = (accessToken: string) => {
    localStorage.setItem(TOKEN_KEY, accessToken)
    setToken(accessToken)
    void api<User>('/api/auth/me', {}, accessToken).then(account => {
      setUser(account)
      if (account.role === 'administrator') navigate('admin')
      else if (account.role === 'lecturer') navigate('lecturer')
      else navigate('dashboard')
    })
  }

  return <div className={`app-shell ${page === 'chat' ? 'app-shell-chat' : ''}`}>
    <header className="topbar">
      <button className="brand" onClick={() => navigate('home')} aria-label="StudyBridge home"><span className="brand-mark"><Icon name="book" /></span><span>StudyBridge<span className="brand-ai"> AI</span></span></button>
      <nav className={`nav-links ${mobileOpen ? 'nav-open' : ''}`}>
        <button onClick={() => navigate('home')}>Home</button>
        <button onClick={() => navigate('catalog')}>Explore courses</button>
        <a href="#how-it-works" onClick={() => navigate('home')}>How it works</a>
        {user ? <>
          {user.role === 'administrator' ? <><button onClick={() => navigate('admin')}>Admin</button><button onClick={() => navigate('admin-members')}>Members</button><button onClick={() => navigate('admin-activity')}>Activity</button></> : null}
          {user.role === 'lecturer' ? <button onClick={() => navigate('lecturer')}>Lecturer</button> : null}
          {user.role === 'student' ? <button onClick={() => navigate('dashboard')}>Dashboard</button> : null}
          {user.role === 'student' ? <button onClick={() => navigate('chat')}>Study assistant</button> : null}
          <button onClick={() => navigate('documents')}>Documents</button>
        </> : null}
      </nav>
      <div className="top-actions">
        <button className="icon-button theme-toggle" onClick={() => setTheme(theme === 'light' ? 'dark' : 'light')} aria-label="Toggle appearance"><Icon name={theme === 'light' ? 'moon' : 'sun'} /></button>
        {user ? <><button className="text-button user-chip" onClick={() => navigate('profile')}><span className="avatar">{user.full_name.slice(0,1).toUpperCase()}</span>{user.full_name.split(' ')[0]}</button><button className="button button-small button-outline" onClick={signOut}>Sign out</button></> : <><button className="text-button login-link" onClick={() => navigate('login')}>Log in</button><button className="button button-small" onClick={() => navigate('signup')}>Get started <Icon name="arrow" /></button></>}
        <button className="icon-button mobile-menu" onClick={() => setMobileOpen(!mobileOpen)} aria-label="Toggle menu"><Icon name={mobileOpen ? 'close' : 'menu'} /></button>
      </div>
    </header>

    <main className={page === 'chat' ? 'app-main-chat' : undefined}>
      {page === 'home' && <Home courses={courses} loading={courseLoading} onNavigate={navigate} />}
      {page === 'login' && <AuthPage mode="login" onNavigate={navigate} onAuthenticated={onAuthenticated} />}
      {page === 'signup' && <AuthPage mode="signup" onNavigate={navigate} onAuthenticated={onAuthenticated} />}
      {page === 'forgot' && <RecoveryPage mode="forgot" onNavigate={navigate} />}
      {page === 'reset' && <RecoveryPage mode="reset" onNavigate={navigate} />}
      {page === 'verify' && <VerificationPage onNavigate={navigate} />}
      {page === 'lecturer-activate' && <LecturerActivationPage onNavigate={navigate} />}
      {page === 'catalog' && <Catalog courses={courses} loading={courseLoading} error={courseError} onNavigate={navigate} />}
      {page === 'dashboard' && <Dashboard user={user} token={token} onNavigate={navigate} />}
      {page === 'chat' && <AcademicChat token={token} />}
      {page === 'profile' && <Profile user={user} token={token} onNavigate={navigate} onSignOut={signOut} />}
      {page === 'documents' && <DocumentCenter user={user} token={token} onNavigate={navigate} />}
      {page === 'lecturer' && <LecturerDashboard token={token} onNavigate={navigate} />}
      {page === 'admin' && <><AdminDashboard token={token} onNavigate={navigate} /><AdminAcademicAccess token={token} /></>}
      {page === 'admin-members' && <AdminMemberDirectory token={token} />}
      {page === 'admin-activity' && <AdminActivityLog token={token} />}
    </main>
    <Footer onNavigate={navigate} />
  </div>
}

function Home({ courses, loading, onNavigate }: { courses: Course[]; loading: boolean; onNavigate: (p: Page) => void }) {
  return <div>
    <section className="hero-section page-container">
      <div className="hero-copy"><div className="eyebrow"><span className="eyebrow-dot" /> YOUR ACADEMIC WORLD, CONNECTED</div>
        <h1>Learn smarter.<br/><span>Go further.</span></h1>
        <p className="hero-lede">One trusted space for your courses, learning materials and AI-powered academic support. Make every study session count.</p>
        <div className="hero-actions"><button className="button button-large" onClick={() => onNavigate('signup')}>Create your free account <Icon name="arrow" /></button><button className="button button-large button-outline" onClick={() => onNavigate('catalog')}>Explore as guest</button></div>
        <div className="trust-row"><span><Icon name="shield"/> Source-aware learning</span><span><Icon name="check"/> Built for university learning</span></div>
      </div>
      <div className="hero-visual"><div className="visual-glow" /><div className="study-card card-main"><div className="card-topline"><span className="mini-brand"><span className="mini-mark">S</span> StudyBridge AI</span><span className="live-pill">ACADEMIC SPACE</span></div><div className="visual-title">Your learning,<br/>in one place.</div><div className="progress-label"><span>Learning journey</span><b>Stay on track</b></div><div className="progress-track"><span /></div><div className="visual-bottom"><div className="course-icon">∑</div><div><b>Course resources</b><small>Organised around your programme</small></div><span className="round-arrow"><Icon name="arrow"/></span></div></div><div className="floating-note"><span className="float-icon"><Icon name="spark"/></span><div><b>AI study companion</b><small>Answers grounded in learning sources</small></div></div><div className="floating-stat"><b>{courses.length || '—'}</b><small>courses available</small></div></div>
    </section>
    <section className="metrics-band"><div className="page-container metrics-grid"><div><b>01</b><span>Discover academic resources</span></div><div><b>02</b><span>Understand difficult topics</span></div><div><b>03</b><span>Build confidence through practice</span></div><div><b>04</b><span>Track your learning journey</span></div></div></section>
    <section className="section page-container" id="how-it-works"><div className="section-heading"><div><div className="eyebrow">A BETTER WAY TO STUDY</div><h2>Everything you need to<br/><span>move forward.</span></h2></div><p>StudyBridge brings academic structure and intelligent study tools together, so you spend less time searching and more time learning.</p></div>
      <div className="feature-grid"><Feature icon="book" number="01" title="Your academic library" desc="Find course materials and learning resources organised around your academic programme."/><Feature icon="spark" number="02" title="AI-powered study support" desc="Get help understanding concepts with answers designed to reference supporting sources."/><Feature icon="search" number="03" title="Discover what matters" desc="Explore courses and topics in a structured academic catalogue."/><Feature icon="shield" number="04" title="Trusted academic content" desc="Academic submissions can be reviewed before becoming part of the shared knowledge base."/></div>
    </section>
    <section className="catalog-preview"><div className="page-container"><div className="section-heading"><div><div className="eyebrow">START EXPLORING</div><h2>Explore the academic<br/><span>catalogue.</span></h2></div><button className="button button-outline" onClick={() => onNavigate('catalog')}>Browse courses <Icon name="arrow"/></button></div>
      {loading ? <p className="muted">Loading available courses…</p> : courses.length ? <div className="course-grid">{courses.slice(0,3).map(c => <CourseCard key={c.id} course={c}/>)}</div> : <div className="empty-preview"><div className="empty-icon"><Icon name="book"/></div><b>Your academic catalogue starts here.</b><p>Explore available public courses. More learning resources will appear as they are approved and published.</p><button className="text-button" onClick={() => onNavigate('catalog')}>Open catalogue <Icon name="arrow"/></button></div>}
    </div></section>
    <section className="cta-section page-container"><div className="cta-panel"><div className="eyebrow eyebrow-light">YOUR NEXT CHAPTER STARTS HERE</div><h2>Make learning work<br/>better for you.</h2><p>Create an account to keep your academic journey connected.</p><button className="button button-white" onClick={() => onNavigate('signup')}>Join StudyBridge <Icon name="arrow"/></button></div></section>
  </div>
}

function Feature({ icon, number, title, desc }: { icon: string; number: string; title: string; desc: string }) {
  return <article className="feature-card"><div className="feature-head"><span className="feature-icon"><Icon name={icon}/></span><span>{number}</span></div><h3>{title}</h3><p>{desc}</p></article>
}
function CourseCard({ course }: { course: Course }) {
  return <article className="course-card"><div className="course-card-top"><span className="course-code">{course.code}</span><span className="course-units">{course.credit_units ?? '—'} units</span></div><h3>{course.title}</h3><div className="course-meta"><span>{course.level || 'Undergraduate'}</span><span>{course.semester || 'Semester not set'}</span></div><div className="course-card-bottom"><span>{course.topics?.length || 0} topics listed</span><span className="course-arrow"><Icon name="arrow"/></span></div></article>
}
function Catalog({ courses, loading, error, onNavigate }: { courses: Course[]; loading: boolean; error: string; onNavigate: (p: Page) => void }) {
  const [query, setQuery] = useState('')
  const filtered = useMemo(() => courses.filter(c => `${c.code} ${c.title}`.toLowerCase().includes(query.toLowerCase())), [courses, query])
  return <section className="page-container inner-page"><div className="page-kicker">PUBLIC ACADEMIC CATALOGUE</div><h1 className="inner-title">Explore courses<span>.</span></h1><p className="inner-lede">Browse the academic courses currently available in StudyBridge. Sign in for your personal learning space.</p><div className="catalog-toolbar"><div className="search-field"><Icon name="search"/><input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search course code or title"/></div><button className="button button-outline" onClick={() => onNavigate('signup')}>Create account</button></div>
    {loading ? <div className="notice">Loading academic courses…</div> : error ? <div className="notice notice-warning">{error}</div> : filtered.length ? <div className="course-grid">{filtered.map(c => <CourseCard key={c.id} course={c}/>)}</div> : <div className="empty-preview"><b>{courses.length ? 'No matching courses found.' : 'No public courses are available yet.'}</b><p>Check back after academic materials have been reviewed and published.</p></div>}
    <p className="guest-note"><Icon name="shield"/> Guest browsing is limited to information made public by the university or its authorised reviewers.</p>
  </section>
}
function AuthPage({ mode, onNavigate, onAuthenticated }: { mode: 'login' | 'signup'; onNavigate: (p: Page) => void; onAuthenticated: (t: string) => void }) {
  const isSignup = mode === 'signup'
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [suggestedEmail, setSuggestedEmail] = useState('')
  const [allowEmailTypo, setAllowEmailTypo] = useState(false)
  const [pendingVerification, setPendingVerification] = useState(false)
  const [developmentVerificationUrl, setDevelopmentVerificationUrl] = useState('')
  async function resendVerification() {
    setBusy(true); setError(''); setSuccess('')
    try {
      const result = await api<{ development_verification_url?: string }>('/api/auth/verification/resend', { method: 'POST', body: JSON.stringify({ email: email.trim(), allow_email_typo: allowEmailTypo }) })
      setDevelopmentVerificationUrl(result.development_verification_url || '')
      setSuccess(result.development_verification_url
        ? 'Email delivery is in console mode, so no email was sent. Use the local verification link below.'
        : 'A verification email was requested. Please check your inbox and spam/junk folder.')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not resend verification email.')
    } finally { setBusy(false) }
  }
  async function submit(e: FormEvent) {
    e.preventDefault(); setError(''); setSuccess('')
    if (isSignup && password !== confirm) { setError('Your passwords do not match.'); return }
    if (isSignup) {
      if (password.length < 8) { setError('Use a password with at least 8 characters.'); return }
      if (!/[a-z]/.test(password) || !/[A-Z]/.test(password) || !/[0-9]/.test(password) || !/[^A-Za-z0-9]/.test(password)) {
        setError('Use 8+ characters with uppercase, lowercase, a number and a special character.')
        return
      }
    }
    setBusy(true)
    try {
      if (!allowEmailTypo) {
        const emailCheck = await api<{ suggested_email?: string }>('/api/auth/email/check', { method: 'POST', body: JSON.stringify({ email: email.trim() }) })
        if (emailCheck.suggested_email) {
          setSuggestedEmail(emailCheck.suggested_email)
          setBusy(false)
          return
        }
      }
      if (isSignup) {
        const result = await api<User & { development_verification_url?: string }>('/api/auth/register', { method: 'POST', body: JSON.stringify({ full_name: fullName.trim(), email: email.trim(), password }) })
        setPendingVerification(true)
        setDevelopmentVerificationUrl(result.development_verification_url || '')
        setSuccess(result.development_verification_url
          ? 'Your account was created. Email delivery is in console mode, so no email was sent. Use the local verification link below.'
          : 'Your account was created. Check your inbox and spam/junk folder for the verification email.')
      } else {
        const result = await api<{ access_token: string }>('/api/auth/login', { method: 'POST', body: JSON.stringify({ email: email.trim(), password, allow_email_typo: allowEmailTypo }) })
        onAuthenticated(result.access_token)
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Something went wrong.'
      setError(message)
      if (!isSignup && message.toLowerCase().includes('verify your email')) setPendingVerification(true)
    }
    finally { setBusy(false) }
  }
  return <section className="auth-layout"><div className="auth-aside"><div className="auth-aside-content"><div className="eyebrow eyebrow-light">YOUR ACADEMIC WORLD, CONNECTED</div><h2>{isSignup ? 'Build a stronger\\nlearning journey.' : 'Welcome back to\\nyour learning space.'}</h2><p>One place for your academic resources, learning tools and progress.</p><div className="auth-aside-points"><span><Icon name="check"/> Organised academic resources</span><span><Icon name="check"/> Intelligent study support</span><span><Icon name="check"/> Your learning journey, connected</span></div></div><div className="auth-aside-foot">StudyBridge AI · Learn smarter. Go further.</div></div>
    <div className="auth-main"><div className="auth-form-wrap"><div className="auth-mobile-brand"><span className="brand-mark"><Icon name="book"/></span> StudyBridge AI</div><div className="page-kicker">{isSignup ? 'GET STARTED' : 'GOOD TO SEE YOU AGAIN'}</div><h1>{isSignup ? 'Create your account' : 'Sign in to StudyBridge'}</h1><p className="form-intro">{isSignup ? 'Create your account to start your academic journey.' : 'Enter your details to access your learning space.'}</p>
      <form onSubmit={submit} className="form-stack">
        {isSignup && <label>Full name<input autoComplete="name" value={fullName} onChange={e => setFullName(e.target.value)} placeholder="Your full name" required minLength={2}/></label>}
        <label>Email address<input type="email" autoComplete="email" value={email} onChange={e => { setEmail(e.target.value); setSuggestedEmail(''); setAllowEmailTypo(false) }} placeholder="you@example.com" required/></label>
        {suggestedEmail && <div className="form-alert typo-suggestion"><span>Did you mean <b>{suggestedEmail}</b> instead of <b>{email}</b>?</span><div className="typo-actions"><button type="button" className="text-button" onClick={() => { setEmail(suggestedEmail); setSuggestedEmail(''); setAllowEmailTypo(false) }}>Use suggested email</button><button type="button" className="text-button" onClick={() => { setSuggestedEmail(''); setAllowEmailTypo(true) }}>Keep entered email</button></div></div>}
        <label>Password<div className="password-wrap"><input type={showPassword ? 'text' : 'password'} autoComplete={isSignup ? 'new-password' : 'current-password'} value={password} onChange={e => setPassword(e.target.value)} placeholder="At least 8 characters" required minLength={8}/><button type="button" className="show-password" onClick={() => setShowPassword(!showPassword)}>{showPassword ? 'Hide' : 'Show'}</button></div></label>
        {isSignup && <p className="password-guidance">Use 8+ characters with uppercase, lowercase, a number and a special character.</p>}
        {isSignup && <label>Confirm password<input type="password" autoComplete="new-password" value={confirm} onChange={e => setConfirm(e.target.value)} placeholder="Enter password again" required minLength={8}/></label>}
        {!isSignup && <div className="form-row-end"><button type="button" className="text-button" onClick={() => onNavigate('forgot')}>Forgot password?</button></div>}
        {error && <div className="form-alert form-error">{error}</div>}{success && <div className="form-alert form-success">{success}</div>}
        {developmentVerificationUrl && <a className="development-verification-link" href={developmentVerificationUrl}>Open local verification link</a>}
        {pendingVerification && <button type="button" className="button button-outline button-submit" disabled={busy} onClick={resendVerification}>Resend verification email</button>}
        <button className="button button-submit" disabled={busy}>{busy ? 'Please wait…' : isSignup ? 'Create account' : 'Sign in'} <Icon name="arrow"/></button>
      </form>
      <p className="auth-switch">{isSignup ? 'Already have an account?' : 'New to StudyBridge?'} <button className="text-button" onClick={() => onNavigate(isSignup ? 'login' : 'signup')}>{isSignup ? 'Sign in' : 'Create an account'}</button></p>
      <button className="guest-back" onClick={() => onNavigate('catalog')}>Continue exploring as a guest <Icon name="arrow"/></button>
      <p className="legal-note">By continuing, you agree to use StudyBridge responsibly and respect academic content ownership.</p>
    </div></div>
  </section>
}
function VerificationPage({ onNavigate }: { onNavigate: (p: Page) => void }) {
  const [status, setStatus] = useState<'loading' | 'success' | 'expired' | 'invalid'>(() => new URLSearchParams(window.location.search).get('token') ? 'loading' : 'invalid')
  const verificationStarted = useRef(false)
  useEffect(() => {
    const token = new URLSearchParams(window.location.search).get('token')
    if (!token || verificationStarted.current) return
    verificationStarted.current = true
    api<{ message: string }>(`/api/auth/verify-email?token=${encodeURIComponent(token)}`)
      .then(() => setStatus('success'))
      .catch((err: Error & { status?: number }) => {
        setStatus(err.message.toLowerCase().includes('expired') ? 'expired' : 'invalid')
      })
  }, [])
  const copy = status === 'success'
    ? { kicker: 'EMAIL VERIFIED', title: 'Email address confirmed', text: 'Your account is verified. You can now sign in and access your StudyBridge learning space.' }
    : status === 'expired'
      ? { kicker: 'LINK EXPIRED', title: 'Verification link expired', text: 'This verification link is no longer valid. Request a new verification email from the sign-in or account page.' }
      : status === 'invalid'
        ? { kicker: 'INVALID LINK', title: 'We could not verify this email', text: 'This link is invalid or has already been used. Request a fresh verification email and try again.' }
        : { kicker: 'VERIFYING EMAIL', title: 'Confirming your address', text: 'Please wait while we validate your secure verification link.' }
  return <section className="recovery-page page-container"><div className="recovery-card"><div className="recovery-icon"><Icon name={status === 'success' ? 'check' : 'shield'}/></div><div className="page-kicker">{copy.kicker}</div><h1>{copy.title}</h1><p>{copy.text}</p><button className="button button-submit" onClick={() => onNavigate(status === 'success' ? 'login' : 'login')}>Continue to sign in</button></div></section>
}
function RecoveryPage({ mode, onNavigate }: { mode: 'forgot' | 'reset'; onNavigate: (p: Page) => void }) {
  const [email, setEmail] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [suggestedEmail, setSuggestedEmail] = useState('')
  const [allowEmailTypo, setAllowEmailTypo] = useState(false)
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [resetComplete, setResetComplete] = useState(false)
  const isForgot = mode === 'forgot'
  async function submitForgot(e: FormEvent) {
    e.preventDefault(); setError(''); setMessage(''); setBusy(true)
    try {
      if (!allowEmailTypo) {
        const check = await api<{ suggested_email?: string }>('/api/auth/email/check', { method: 'POST', body: JSON.stringify({ email: email.trim() }) })
        if (check.suggested_email) { setSuggestedEmail(check.suggested_email); setBusy(false); return }
      }
      const result = await api<{ message: string }>('/api/auth/forgot-password', { method: 'POST', body: JSON.stringify({ email: email.trim(), allow_email_typo: allowEmailTypo }) })
      setMessage(result.message)
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not request password reset.') }
    finally { setBusy(false) }
  }
  async function submitReset(e: FormEvent) {
    e.preventDefault(); setError(''); setMessage('')
    if (password !== confirm) { setError('Your passwords do not match.'); return }
    if (!/[a-z]/.test(password) || !/[A-Z]/.test(password) || !/[0-9]/.test(password) || !/[^A-Za-z0-9]/.test(password) || password.length < 8) {
      setError('Use 8+ characters with uppercase, lowercase, a number and a special character.')
      return
    }
    const token = new URLSearchParams(window.location.search).get('token')
    if (!token) { setError('This password reset link is invalid or incomplete.'); return }
    setBusy(true)
    try {
      const result = await api<{ message: string }>('/api/auth/reset-password', { method: 'POST', body: JSON.stringify({ token, password }) })
      setMessage(result.message); setResetComplete(true)
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not reset password.') }
    finally { setBusy(false) }
  }
  return <section className="recovery-page page-container"><div className="recovery-card"><div className="recovery-icon"><Icon name="lock"/></div><div className="page-kicker">ACCOUNT SECURITY</div><h1>{isForgot ? 'Reset your password' : resetComplete ? 'Password updated' : 'Choose a new password'}</h1><p>{isForgot ? 'Enter your account email to request a secure password reset link.' : resetComplete ? 'You can now sign in using your new password.' : 'Create a strong new password for your account.'}</p>
    {isForgot ? <form className="form-stack" onSubmit={submitForgot}>
      <label>Email address<input type="email" autoComplete="email" value={email} onChange={e => { setEmail(e.target.value); setSuggestedEmail(''); setAllowEmailTypo(false) }} placeholder="you@example.com" required/></label>
      {suggestedEmail && <div className="form-alert typo-suggestion"><span>Did you mean <b>{suggestedEmail}</b> instead of <b>{email}</b>?</span><div className="typo-actions"><button type="button" className="text-button" onClick={() => { setEmail(suggestedEmail); setSuggestedEmail(''); setAllowEmailTypo(false) }}>Use suggested email</button><button type="button" className="text-button" onClick={() => { setSuggestedEmail(''); setAllowEmailTypo(true) }}>Keep entered email</button></div></div>}
      <button className="button button-submit" disabled={busy}>{busy ? 'Please wait…' : 'Request reset link'}</button>
    </form> : resetComplete ? <button className="button button-submit" onClick={() => onNavigate('login')}>Sign in</button> : <form className="form-stack" onSubmit={submitReset}>
      <label>New password<div className="password-wrap"><input type={showPassword ? 'text' : 'password'} value={password} onChange={e => setPassword(e.target.value)} autoComplete="new-password" required minLength={8}/><button type="button" className="show-password" onClick={() => setShowPassword(!showPassword)}>{showPassword ? 'Hide' : 'Show'}</button></div></label>
      <label>Confirm new password<input type="password" value={confirm} onChange={e => setConfirm(e.target.value)} autoComplete="new-password" required minLength={8}/></label>
      <p className="password-guidance">Use 8+ characters with uppercase, lowercase, a number and a special character.</p>
      <button className="button button-submit" disabled={busy}>{busy ? 'Please wait…' : 'Update password'}</button>
    </form>}
    {error && <div className="form-alert form-error">{error}</div>}{message && <div className="form-alert form-success">{message}</div>}
    <button className="text-button back-login" onClick={() => onNavigate('login')}>Back to sign in</button>
  </div></section>
}
function Dashboard({ user, token, onNavigate }: { user: User | null; token: string | null; onNavigate: (p: Page) => void }) {
  if (!token) return <section className="page-container inner-page"><h1 className="inner-title">Your learning space<span>.</span></h1><p>Please sign in to access your dashboard.</p><button className="button" onClick={() => onNavigate('login')}>Sign in</button></section>
  return <section className="page-container inner-page"><div className="dashboard-welcome"><div><div className="page-kicker">YOUR STUDYBRIDGE SPACE</div><h1 className="inner-title">Welcome{user ? `, ${user.full_name.split(' ')[0]}` : ''}<span>.</span></h1><p className="inner-lede">Your academic journey starts here. Explore courses and discover learning resources.</p></div><div className="dashboard-avatar">{user?.full_name.slice(0,1).toUpperCase() || 'S'}</div></div><div className="dashboard-grid"><div className="dashboard-tile"><span className="tile-icon"><Icon name="book"/></span><h3>Explore courses</h3><p>Browse available academic courses and topics.</p><button className="text-button" onClick={() => onNavigate('catalog')}>Open catalogue <Icon name="arrow"/></button></div><div className="dashboard-tile"><span className="tile-icon"><Icon name="spark"/></span><h3>AI study companion</h3><p>Ask questions, get step-by-step explanations and study from approved course materials.</p><button className="text-button" onClick={() => onNavigate('chat')}>Open study assistant <Icon name="arrow"/></button></div><div className="dashboard-tile"><span className="tile-icon"><Icon name="upload"/></span><h3>Academic materials</h3><p>Browse approved learning resources and track document review status.</p><button className="text-button" onClick={() => onNavigate('documents')}>Open document centre <Icon name="arrow"/></button></div></div><div className="account-strip"><div><b>Account</b><span>{user?.email || 'Loading account…'} · {user?.role || 'Member'}</span></div><button className="button button-outline" onClick={() => onNavigate('profile')}>View profile</button></div></section>
}

type ChatSource = { document_id: number; document_title: string; page_number: number; excerpt: string; course_code: string | null; university: string | null; faculty: string | null; department: string | null }
type ChatEntry = { id: number; role: 'user' | 'assistant'; content: string; created_at: string; sources: ChatSource[] }
type ChatSessionRow = { id: number; title: string | null; created_at: string; message_count: number }
type ChatStreamEvent =
  | { type: 'start'; user_message: ChatEntry }
  | { type: 'delta'; text: string }
  | { type: 'done'; assistant_message: ChatEntry }
  | { type: 'error'; detail: string }

function formatChatText(content: string) {
  return content.split(/\n{2,}/).map((block, blockIndex) => {
    const lines = block.split('\n')
    const heading = lines[0].match(/^(#{1,3})\s+(.+)$/)
    if (heading && lines.length === 1) {
      const Heading = heading[1].length === 1 ? 'h3' : 'h4'
      return <Heading key={blockIndex}>{heading[2]}</Heading>
    }

    if (lines.every(line => /^(?:[-*+]|\d+[.)])\s+/.test(line))) {
      return <ul key={blockIndex}>{lines.map((line, lineIndex) => (
        <li key={lineIndex}>{formatInlineChatText(line.replace(/^(?:[-*+]|\d+[.)])\s+/, ''))}</li>
      ))}</ul>
    }

    return <p key={blockIndex}>{lines.map((line, lineIndex) => (
      <Fragment key={lineIndex}>{lineIndex > 0 && <br />}{formatInlineChatText(line)}</Fragment>
    ))}</p>
  })
}

function formatInlineChatText(text: string) {
  return text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).map((part, index) => {
    if (part.startsWith('**') && part.endsWith('**')) return <strong key={index}>{part.slice(2, -2)}</strong>
    if (part.startsWith('`') && part.endsWith('`')) return <code key={index}>{part.slice(1, -1)}</code>
    return part
  })
}

async function streamChatMessage(
  sessionId: number,
  message: string,
  token: string,
  onEvent: (event: ChatStreamEvent) => void,
) {
  const response = await fetch(`${API_BASE}/api/chat/sessions/${sessionId}/messages/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ message }),
  })
  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    throw new Error(typeof data?.detail === 'string' ? data.detail : 'Could not get a study assistant response.')
  }
  if (!response.body) throw new Error('Streaming is not supported by this browser.')

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let completed = false
  function dispatch(frame: string) {
    const payload = frame.split('\n')
      .filter(line => line.startsWith('data:'))
      .map(line => line.slice(5).trimStart())
      .join('\n')
    if (!payload) return
    const event = JSON.parse(payload) as ChatStreamEvent
    if (event.type === 'error') throw new Error(event.detail)
    if (event.type === 'done') completed = true
    onEvent(event)
  }

  try {
    while (true) {
      const { value, done } = await reader.read()
      buffer += decoder.decode(value, { stream: !done }).replace(/\r\n/g, '\n')
      let frameEnd = buffer.indexOf('\n\n')
      while (frameEnd !== -1) {
        dispatch(buffer.slice(0, frameEnd))
        buffer = buffer.slice(frameEnd + 2)
        frameEnd = buffer.indexOf('\n\n')
      }
      if (done) break
    }
    if (buffer.trim()) dispatch(buffer)
  } finally {
    reader.releaseLock()
  }
  if (!completed) throw new Error('The study assistant stream ended before the answer was saved.')
}

function AcademicChat({ token }: { token: string | null }) {
  const [sessions, setSessions] = useState<ChatSessionRow[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [messages, setMessages] = useState<ChatEntry[]>([])
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [chatStatus, setChatStatus] = useState('')
  const messageListRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const list = messageListRef.current
    if (list) list.scrollTop = list.scrollHeight
  }, [messages, chatStatus])

  const loadSessions = useCallback(async () => {
    if (!token) return
    try {
      const result = await api<{ items: ChatSessionRow[] }>('/api/chat/sessions', {}, token)
      setSessions(result.items)
      return result.items
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load chat history.')
      return []
    } finally {
      setLoading(false)
    }
  }, [token])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadSessions().then(rows => {
      if (rows?.length) setSelectedId(current => current ?? rows[0].id)
    })
  }, [loadSessions])

  useEffect(() => {
    if (!token || selectedId === null) return
    let active = true
    api<{ messages: ChatEntry[] }>(`/api/chat/sessions/${selectedId}`, {}, token)
      .then(result => { if (active) setMessages(result.messages) })
      .catch(err => { if (active) setError(err instanceof Error ? err.message : 'Could not load this conversation.') })
    return () => { active = false }
  }, [selectedId, token])

  async function createSession() {
    if (!token) return
    setBusy(true)
    setError('')
    try {
      const session = await api<ChatSessionRow>('/api/chat/sessions', {
        method: 'POST',
        body: JSON.stringify({}),
      }, token)
      setSessions(previous => [session, ...previous])
      setSelectedId(session.id)
      setMessages([])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not start a conversation.')
    } finally {
      setBusy(false)
    }
  }

  async function deleteSession(sessionId: number) {
    if (!token || busy) return
    setBusy(true)
    setError('')
    try {
      await api(`/api/chat/sessions/${sessionId}`, { method: 'DELETE' }, token)
      const remaining = sessions.filter(session => session.id !== sessionId)
      setSessions(remaining)
      if (selectedId === sessionId) {
        setSelectedId(remaining[0]?.id ?? null)
        setMessages([])
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not delete this conversation.')
    } finally {
      setBusy(false)
    }
  }

  async function sendMessage(event: FormEvent) {
    event.preventDefault()
    if (!token || !draft.trim() || busy) return
    setBusy(true)
    setError('')
    setChatStatus('Searching approved course materials…')
    const messageText = draft.trim()
    const optimisticUserId = -Date.now()
    let streamingAssistantId: number | null = null
    try {
      let sessionId = selectedId
      if (sessionId === null) {
        const session = await api<ChatSessionRow>('/api/chat/sessions', {
          method: 'POST',
          body: JSON.stringify({}),
        }, token)
        sessionId = session.id
        setSelectedId(sessionId)
        setSessions(previous => [session, ...previous])
      }
      setMessages(previous => [...previous, {
        id: optimisticUserId,
        role: 'user',
        content: messageText,
        created_at: new Date().toISOString(),
        sources: [],
      }])
      await streamChatMessage(sessionId, messageText, token, streamEvent => {
        if (streamEvent.type === 'start') {
          setDraft('')
          setMessages(previous => previous.map(message => (
            message.id === optimisticUserId ? streamEvent.user_message : message
          )))
        } else if (streamEvent.type === 'delta') {
          setChatStatus('')
          if (streamingAssistantId === null) streamingAssistantId = -Date.now() - 1
          const assistantId = streamingAssistantId
          setMessages(previous => {
            const existing = previous.find(message => message.id === assistantId)
            if (!existing) return [...previous, {
              id: assistantId,
              role: 'assistant',
              content: streamEvent.text,
              created_at: new Date().toISOString(),
              sources: [],
            }]
            return previous.map(message => message.id === assistantId
              ? { ...message, content: message.content + streamEvent.text }
              : message)
          })
        } else if (streamEvent.type === 'done') {
          setChatStatus('')
          const assistantMessage = streamEvent.assistant_message
          setMessages(previous => streamingAssistantId === null
            ? [...previous, assistantMessage]
            : previous.map(message => message.id === streamingAssistantId ? assistantMessage : message))
        }
      })
      await loadSessions()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not get a study assistant response.')
    } finally {
      setBusy(false)
      setChatStatus('')
    }
  }

  if (!token) return <section className="page-container inner-page"><h1 className="inner-title">Study assistant<span>.</span></h1><p>Sign in to use the academic assistant.</p></section>
  const activeSession = sessions.find(session => session.id === selectedId)
  return <section className="page-container inner-page academic-chat-page">
    <div className="chat-page-heading">
      <div><div className="page-kicker">YOUR AI STUDY COMPANION</div><h1 className="inner-title">Study assistant<span>.</span></h1></div>
      <p className="inner-lede">A focused space to understand course topics, review notes and prepare for exams.</p>
    </div>
    {error && <div className="form-alert form-error" role="alert">{error}</div>}
    <div className="academic-chat-layout">
      <aside className="chat-sessions-panel">
        <div className="chat-sidebar-heading"><div><b>Your conversations</b><small>{sessions.length} saved</small></div><button className="button chat-new-button" disabled={busy} onClick={() => void createSession()} aria-label="Start a new conversation">+</button></div>
        <div className="chat-session-list">
          {loading && <p className="doc-muted">Loading conversations…</p>}
          {sessions.map(session => <div className={`chat-session-item ${selectedId === session.id ? 'chat-session-active' : ''}`} key={session.id}>
            <button type="button" onClick={() => { setMessages([]); setSelectedId(session.id) }}>
              <b>{session.title || 'New conversation'}</b>
              <small>{new Date(session.created_at).toLocaleDateString()} · {session.message_count} messages</small>
            </button>
            <button type="button" className="chat-delete-button" disabled={busy} aria-label={`Delete ${session.title || 'conversation'}`} onClick={() => void deleteSession(session.id)}>×</button>
          </div>)}
          {!loading && sessions.length === 0 && <p className="doc-muted">Your conversations will appear here.</p>}
        </div>
      </aside>
      <div className="academic-chat-main">
        <div className="chat-conversation-heading">
          <div><span className="chat-context-label">STUDY SESSION</span><h2>{activeSession?.title || 'New conversation'}</h2><p>Answers are grounded in material you’re allowed to access.</p></div>
          <span className="chat-assistant-status"><i /> Academic assistant</span>
        </div>
        <div className="chat-message-list" aria-live="polite" ref={messageListRef}>
          {!messages.length && <div className="chat-empty-state"><span className="tile-icon"><Icon name="spark"/></span><h2>What would you like to study?</h2><p>Choose a prompt to get started, or ask your own question.</p><div className="chat-suggestion-grid">
            {['Explain a topic step by step', 'Summarise my course notes', 'Create revision questions'].map(prompt => <button type="button" key={prompt} onClick={() => setDraft(prompt)}>{prompt}<span>↗</span></button>)}
          </div></div>}
          {messages.map(message => <article className={`chat-message chat-message-${message.role}`} key={message.id}>
            <div className="chat-message-avatar" aria-hidden="true">{message.role === 'assistant' ? <Icon name="spark" /> : 'Y'}</div>
            <div className="chat-message-body"><div className="chat-message-meta"><b>{message.role === 'assistant' ? 'StudyBridge' : 'You'}</b><time>{new Date(message.created_at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}</time></div>
            <div className="chat-message-content">{message.role === 'assistant' ? formatChatText(message.content) : message.content}</div>
            {message.sources?.length > 0 && <div className="chat-sources"><b>StudyBridge sources</b>{message.sources.map((source, index) => <details key={`${source.document_id}-${source.page_number}-${index}`}>
              <summary>{source.document_title} · page {source.page_number}{source.course_code ? ` · ${source.course_code}` : ''}</summary>
              <p>{source.excerpt}</p>
            </details>)}</div>}
            </div>
          </article>)}
          {busy && chatStatus && <div className="chat-thinking" role="status"><span className="chat-thinking-dots"><i/><i/><i/></span>{chatStatus}</div>}
        </div>
        <form className="chat-compose" onSubmit={sendMessage}>
          <label className="sr-only" htmlFor="academic-chat-input">Your question</label>
          <textarea id="academic-chat-input" rows={2} value={draft} onChange={event => setDraft(event.target.value)} onKeyDown={event => {
            if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault()
              event.currentTarget.form?.requestSubmit()
            }
          }} placeholder="Message your study assistant…" maxLength={6000} disabled={busy} />
          <div className="chat-compose-footer"><span><kbd>Enter</kbd> to send · <kbd>Shift + Enter</kbd> for a new line</span><button className="button" type="submit" disabled={busy || !draft.trim()}>{busy ? 'Working…' : 'Send'} <Icon name="arrow" /></button></div>
        </form>
      </div>
    </div>
  </section>
}
function Profile({ user, token, onNavigate, onSignOut }: { user: User | null; token: string | null; onNavigate: (p: Page) => void; onSignOut: () => void }) {
  const [newEmail, setNewEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [suggestedEmail, setSuggestedEmail] = useState('')
  const [allowEmailTypo, setAllowEmailTypo] = useState(false)
  async function submitEmailChange(e: FormEvent) {
    e.preventDefault(); setError(''); setMessage(''); setBusy(true)
    try {
      const check = await api<{ suggested_email?: string }>('/api/auth/email/check', { method: 'POST', body: JSON.stringify({ email: newEmail.trim() }) })
      if (check.suggested_email && !allowEmailTypo) { setSuggestedEmail(check.suggested_email); setBusy(false); return }
      const result = await api<{ message: string }>('/api/auth/email/change', { method: 'POST', body: JSON.stringify({ email: newEmail.trim(), password, allow_email_typo: allowEmailTypo }) }, token || undefined)
      setMessage(result.message)
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not request email change.') }
    finally { setBusy(false) }
  }
  return <section className="page-container inner-page"><div className="page-kicker">ACCOUNT SETTINGS</div><h1 className="inner-title">Your profile<span>.</span></h1><div className="profile-card"><div className="profile-avatar">{user?.full_name.slice(0,1).toUpperCase() || 'S'}</div><div><h3>{user?.full_name || 'Loading profile'}</h3><p>{user?.email}</p><span className="role-pill">{user?.role || 'Member'}</span></div></div>
    <form className="form-stack profile-email-form" onSubmit={submitEmailChange}><b>Change email address</b><label>New email address<input type="email" value={newEmail} onChange={e => { setNewEmail(e.target.value); setSuggestedEmail(''); setAllowEmailTypo(false) }} required/></label>{suggestedEmail && <div className="form-alert typo-suggestion"><span>Did you mean <b>{suggestedEmail}</b> instead of <b>{newEmail}</b>?</span><div className="typo-actions"><button type="button" className="text-button" onClick={() => { setNewEmail(suggestedEmail); setSuggestedEmail(''); setAllowEmailTypo(false) }}>Use suggested email</button><button type="button" className="text-button" onClick={() => { setSuggestedEmail(''); setAllowEmailTypo(true) }}>Keep entered email</button></div></div>}<label>Current password<input type="password" value={password} onChange={e => setPassword(e.target.value)} required/></label>{error && <div className="form-alert form-error">{error}</div>}{message && <div className="form-alert form-success">{message}</div>}<button className="button" disabled={busy}>{busy ? 'Please wait…' : 'Send confirmation email'}</button></form>
    {user && user.role !== 'administrator' && <AcademicAffiliationForm user={user} token={token} />}
    <div className="profile-actions"><button className="button button-outline" onClick={() => onNavigate('dashboard')}>Back to dashboard</button><button className="button button-danger" onClick={onSignOut}>Sign out</button></div></section>
}

function AcademicAffiliationForm({ user, token }: { user: User; token: string | null }) {
  type Department = { id: number; name: string; faculty_id: number }
  type Programme = { id: number; name: string; department_id: number; level: string }
  type Affiliation = {
    status: string; department_id: number | null; department_name: string | null
    faculty_name: string | null; university_name: string | null; programme_id: number | null
    programme_name: string | null; level: string | null; review_note: string | null
    department_locked: boolean
  }
  const [departments, setDepartments] = useState<Department[]>([])
  const [programmes, setProgrammes] = useState<Programme[]>([])
  const [affiliation, setAffiliation] = useState<Affiliation | null>(null)
  const [departmentId, setDepartmentId] = useState('')
  const [programmeId, setProgrammeId] = useState('')
  const [level, setLevel] = useState('')
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    if (!token) return
    try {
      const [departmentRows, programmeRows, current] = await Promise.all([
        api<Department[]>('/api/academic/departments'),
        api<Programme[]>('/api/academic/programmes'),
        api<Affiliation>('/api/academic/affiliation/me', {}, token),
      ])
      setDepartments(departmentRows)
      setProgrammes(programmeRows)
      setAffiliation(current)
      setDepartmentId(current.department_id ? String(current.department_id) : '')
      setProgrammeId(current.programme_id ? String(current.programme_id) : '')
      setLevel(current.level || '')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load academic affiliation.')
    }
  }, [token])

  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { void load() }, [load])

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!token || !departmentId) return
    setBusy(true); setError(''); setMessage('')
    try {
      const result = await api<Affiliation>('/api/academic/affiliation/me', {
        method: 'PUT',
        body: JSON.stringify({
          department_id: Number(departmentId),
          programme_id: programmeId ? Number(programmeId) : null,
          level: level.trim() || null,
        }),
      }, token)
      setAffiliation(result)
      setMessage(result.status === 'verified'
        ? 'Your academic affiliation is verified.'
        : 'Your affiliation was submitted for administrator verification.')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not submit academic affiliation.')
    } finally { setBusy(false) }
  }

  const availableProgrammes = programmes.filter(programme => programme.department_id === Number(departmentId))
  return <section className="doc-panel affiliation-panel">
    <div className="doc-toolbar"><div><h2>Academic affiliation</h2><p>Choose your university department and programme. An administrator must verify the details before academic access is enabled.</p></div><span className={`status-pill status-${affiliation?.status || 'draft'}`}>{affiliation?.status?.replaceAll('_', ' ') || 'Loading'}</span></div>
    {affiliation?.university_name && <p className="affiliation-summary"><b>{affiliation.university_name}</b> · {affiliation.faculty_name} · {affiliation.department_name}{affiliation.programme_name ? ` · ${affiliation.programme_name}` : ''}{affiliation.level ? ` · ${affiliation.level}` : ''}</p>}
    {affiliation?.review_note && <div className="form-alert form-warning">{affiliation.review_note}</div>}
    {error && <div className="form-alert form-error" role="alert">{error}</div>}
    {message && <div className="form-alert form-success" role="status">{message}</div>}
    <form className="doc-form" onSubmit={submit}>
      <label>Department<select required value={departmentId} disabled={busy || affiliation?.department_locked} onChange={event => { setDepartmentId(event.target.value); setProgrammeId('') }}><option value="">Select department</option>{departments.map(department => <option key={department.id} value={department.id}>{department.name}</option>)}</select></label>
      {user.role === 'student' && <>
        <label>Programme<select required value={programmeId} onChange={event => setProgrammeId(event.target.value)}><option value="">Select programme</option>{availableProgrammes.map(programme => <option key={programme.id} value={programme.id}>{programme.name}</option>)}</select></label>
        <label>Current academic level<input required value={level} onChange={event => setLevel(event.target.value)} placeholder="e.g. 200 Level" maxLength={20}/></label>
      </>}
      <button className="button" disabled={busy || !departmentId}>{busy ? 'Submitting…' : affiliation?.status === 'verified' ? 'Update affiliation' : 'Submit for verification'}</button>
    </form>
  </section>
}

function LecturerActivationPage({ onNavigate }: { onNavigate: (p: Page) => void }) {
  const token = new URLSearchParams(window.location.search).get('token') || ''
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  async function activate(e: FormEvent) {
    e.preventDefault()
    setError(''); setMessage('')
    if (password !== confirm) { setError('Passwords do not match.'); return }
    setBusy(true)
    try {
      const result = await api<{ message: string }>('/api/lecturers/activate', { method: 'POST', body: JSON.stringify({ token, password }) })
      setMessage(result.message)
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not activate account.') }
    finally { setBusy(false) }
  }
  return <section className="recovery-page"><div className="recovery-card"><div className="recovery-icon"><Icon name="lock"/></div><h1>Activate lecturer account</h1><p>Set a strong password to complete your invitation.</p>{message ? <><div className="form-alert form-success">{message}</div><button className="button button-submit" onClick={() => onNavigate('login')}>Sign in</button></> : <form className="form-stack" onSubmit={activate}><label>New password<input type="password" value={password} onChange={e => setPassword(e.target.value)} minLength={8} required/></label><label>Confirm password<input type="password" value={confirm} onChange={e => setConfirm(e.target.value)} minLength={8} required/></label>{error && <div className="form-alert form-error">{error}</div>}<button className="button button-submit" disabled={busy || !token}>{busy ? 'Activating…' : 'Activate account'}</button></form>}{!token && <div className="form-alert form-error">This activation link is invalid.</div>}</div></section>
}

function LecturerDashboard({ token, onNavigate }: { token: string | null; onNavigate: (p: Page) => void }) {
  type LecturerProfileData = {
    lecturer_id: string; official_name: string; staff_number: string; username: string; email: string
    phone?: string; department_id?: number; title?: string; biography?: string
    qualifications?: string; office_location?: string; assigned_course_ids: number[]
    email_verified: boolean; is_active: boolean
  }
  const [profile, setProfile] = useState<LecturerProfileData | null>(null)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [phone, setPhone] = useState('')
  const [biography, setBiography] = useState('')
  const [qualifications, setQualifications] = useState('')
  const [office, setOffice] = useState('')
  useEffect(() => {
    if (!token) return
    api<LecturerProfileData>('/api/lecturers/me', {}, token)
      .then(data => { setProfile(data); setPhone(data.phone || ''); setBiography(data.biography || ''); setQualifications(data.qualifications || ''); setOffice(data.office_location || '') })
      .catch(err => setError(err instanceof Error ? err.message : 'Could not load lecturer profile'))
  }, [token])
  async function save(e: FormEvent) {
    e.preventDefault(); setError(''); setMessage('')
    try {
      await api('/api/lecturers/me', { method: 'PUT', body: JSON.stringify({ phone, biography, qualifications, office_location: office }) }, token || undefined)
      setMessage('Profile updated.')
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not update profile.') }
  }
  if (!token) return <section className="page-container inner-page"><h1>Lecturer dashboard</h1><button className="button" onClick={() => onNavigate('login')}>Sign in</button></section>
  return <section className="page-container inner-page"><div className="page-kicker">LECTURER DASHBOARD</div><h1 className="inner-title">Lecturer profile<span>.</span></h1>{error && <div className="form-alert form-error">{error}</div>}{message && <div className="form-alert form-success">{message}</div>}<div className="profile-card"><div className="profile-avatar">{profile?.official_name?.slice(0,1).toUpperCase() || 'L'}</div><div><h3>{profile?.official_name || 'Loading profile'}</h3><p>{profile?.lecturer_id} · {profile?.staff_number}</p><p>{profile?.email}</p><span className="role-pill">{profile?.is_active ? 'Active' : 'Inactive'} · {profile?.email_verified ? 'Verified' : 'Unverified'}</span></div></div><div className="account-strip"><div><b>Department</b><span>ID {profile?.department_id ?? 'Not assigned'} · {profile?.title || 'No academic title'}</span></div><div><b>Assigned courses</b><span>{profile?.assigned_course_ids?.length ? profile.assigned_course_ids.join(', ') : 'No courses assigned'}</span></div></div><form className="form-stack profile-email-form" onSubmit={save}><b>Editable profile details</b><label>Phone number (unverified)<input value={phone} onChange={e => setPhone(e.target.value)} placeholder="+234…"/></label><label>Biography<textarea value={biography} onChange={e => setBiography(e.target.value)} rows={4}/></label><label>Qualifications<textarea value={qualifications} onChange={e => setQualifications(e.target.value)} rows={4}/></label><label>Office location / consultation<textarea value={office} onChange={e => setOffice(e.target.value)} rows={3}/></label><div className="profile-actions"><button className="button" type="submit">Save profile</button><button className="button button-outline" type="button" onClick={() => onNavigate('profile')}>Account settings</button></div></form></section>
}

function AdminDashboard({ token }: { token: string | null; onNavigate: (p: Page) => void }) {
  type DepartmentRow = { id: number; name: string }
  type CourseRow = { id: number; code: string; title: string; level: string | null; department_id: number }
  type LecturerRow = { id: number; lecturer_id: string; full_name: string; username: string; email: string; staff_number: string; department_id: number; invitation_status: string; email_verified: boolean; is_active: boolean; assigned_course_ids: number[] }
  const [lecturers, setLecturers] = useState<LecturerRow[]>([])
  const [departments, setDepartments] = useState<DepartmentRow[]>([])
  const [courses, setCourses] = useState<CourseRow[]>([])
  const [search, setSearch] = useState('')
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [fullName, setFullName] = useState('')
  const [staffNumber, setStaffNumber] = useState('')
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [phone, setPhone] = useState('')
  const [departmentId, setDepartmentId] = useState('')
  const [courseIds, setCourseIds] = useState<number[]>([])
  const [editingLecturerId, setEditingLecturerId] = useState<number | null>(null)
  const [editDepartmentId, setEditDepartmentId] = useState('')
  const [editCourseIds, setEditCourseIds] = useState<number[]>([])
  const [title, setTitle] = useState('')
  const [invitationLink, setInvitationLink] = useState('')
  const load = useCallback(async (query = '') => {
    if (!token) return
    try {
      const [result, departmentResult, courseResult] = await Promise.all([
        api<{ items: LecturerRow[] }>(`/api/admin/lecturers?search=${encodeURIComponent(query)}`, {}, token),
        api<DepartmentRow[]>('/api/academic/departments', {}, token),
        api<{ items: CourseRow[] }>('/api/academic/courses?skip=0&limit=200', {}, token),
      ])
      setLecturers(result.items)
      setDepartments(departmentResult)
      setCourses(courseResult.items)
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not load lecturers.') }
  }, [token])
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { void load() }, [load])
  const createCourses = courses.filter(course => course.department_id === Number(departmentId))
  const editCourses = courses.filter(course => course.department_id === Number(editDepartmentId))
  async function saveCourseAssignments(event: FormEvent) {
    event.preventDefault()
    if (!token || editingLecturerId === null || !editDepartmentId) return
    setError(''); setMessage('')
    try {
      await api(`/api/admin/lecturers/${editingLecturerId}`, {
        method: 'PUT',
        body: JSON.stringify({ department_id: Number(editDepartmentId), course_ids: editCourseIds }),
      }, token)
      setEditingLecturerId(null)
      setMessage('Lecturer department and course assignments updated.')
      await load(search)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not update lecturer assignments.')
    }
  }
  return <section className="page-container inner-page">
    <div className="page-kicker">ADMINISTRATION</div><h1 className="inner-title">Lecturer administration<span>.</span></h1>
    {error && <div className="form-alert form-error" role="alert">{error}</div>}{message && <div className="form-alert form-success" role="status">{message}</div>}
    <form className="form-stack profile-email-form" onSubmit={async event => {
      event.preventDefault(); setError(''); setMessage('')
      try {
        const created = await api<{ development_invitation_url?: string }>('/api/admin/lecturers', {
          method: 'POST',
          body: JSON.stringify({
            full_name: fullName, staff_number: staffNumber, username, email,
            phone: phone || null, department_id: Number(departmentId),
            title: title || null, course_ids: courseIds,
          }),
        }, token || undefined)
        setInvitationLink(created.development_invitation_url || '')
        setMessage(created.development_invitation_url
          ? 'Lecturer account created. Open the local invitation link below to activate it.'
          : 'Lecturer account created and invitation sent.')
        setFullName(''); setStaffNumber(''); setUsername(''); setEmail(''); setPhone(''); setTitle('')
        setDepartmentId(''); setCourseIds([])
        await load()
      } catch (err) { setError(err instanceof Error ? err.message : 'Could not create lecturer.') }
    }}>
      <b>Create lecturer account</b>
      <div className="dashboard-grid">
        <label>Official full name<input value={fullName} onChange={event => setFullName(event.target.value)} required/></label>
        <label>Staff number<input value={staffNumber} onChange={event => setStaffNumber(event.target.value)} required/></label>
        <label>Username<input value={username} onChange={event => setUsername(event.target.value)} required/></label>
        <label>Email<input type="email" value={email} onChange={event => setEmail(event.target.value)} required/></label>
        <label>Phone (optional)<input value={phone} onChange={event => setPhone(event.target.value)} /></label>
        <label>Department<select required value={departmentId} onChange={event => { setDepartmentId(event.target.value); setCourseIds([]) }}><option value="">Select department</option>{departments.map(department => <option key={department.id} value={department.id}>{department.name}</option>)}</select></label>
        <label>Academic title<input value={title} onChange={event => setTitle(event.target.value)} /></label>
      </div>
      <label className="admin-course-select">Assigned courses (optional, select multiple)<select multiple size={Math.min(6, Math.max(2, createCourses.length))} value={courseIds.map(String)} onChange={event => setCourseIds(Array.from(event.currentTarget.selectedOptions, option => Number(option.value)))}>{createCourses.map(course => <option key={course.id} value={course.id}>{course.code} · {course.title}</option>)}</select></label>
      <button className="button" disabled={!departmentId}>Create lecturer</button>
    </form>
    {invitationLink && <div className="form-alert form-warning"><b>Local console invitation</b><br/><a className="development-verification-link" href={invitationLink}>Open lecturer activation link</a></div>}
    <div className="catalog-toolbar"><div className="search-field"><Icon name="search"/><input value={search} onChange={event => setSearch(event.target.value)} placeholder="Search name, email, staff number or username"/></div><button className="button button-outline" onClick={() => void load(search)}>Search</button></div>
    <div className="doc-list">{lecturers.map(row => <Fragment key={row.id}>
      <article className="doc-row admin-academic-row"><div className="doc-row-main"><b>{row.full_name}</b><span>{row.lecturer_id} · {row.email}</span><small>{row.staff_number} · Department {departments.find(department => department.id === row.department_id)?.name || row.department_id} · {row.invitation_status} · {row.is_active ? 'Active' : 'Inactive'}</small><small>Assigned courses: {row.assigned_course_ids.length ? row.assigned_course_ids.map(id => courses.find(course => course.id === id)?.code || id).join(', ') : 'None'}</small></div>
        <div className="doc-row-actions">
          <button className="button button-small button-outline" onClick={() => { setEditingLecturerId(row.id); setEditDepartmentId(String(row.department_id)); setEditCourseIds(row.assigned_course_ids || []) }}>Edit assignments</button>
          <button className="button button-small button-outline" onClick={async () => {
            try {
              const resent = await api<{ message: string; development_invitation_url?: string }>(`/api/admin/lecturers/${row.id}/resend-invitation`, { method: 'POST' }, token || undefined)
              setInvitationLink(resent.development_invitation_url || '')
              setMessage(resent.development_invitation_url ? 'Invitation resent. Open the local activation link below.' : resent.message)
            } catch (err) {
              setError(err instanceof Error ? err.message : 'Could not resend invitation.')
            }
          }}>Resend</button>
          <button className="button button-small" onClick={async () => {
            try {
              await api(`/api/admin/lecturers/${row.id}/${row.is_active ? 'suspend' : 'reactivate'}`, { method: 'POST' }, token || undefined)
              await load(search)
            } catch (err) {
              setError(err instanceof Error ? err.message : 'Could not update account.')
            }
          }}>{row.is_active ? 'Suspend' : 'Reactivate'}</button>
        </div>
      </article>
      {editingLecturerId === row.id && <form className="doc-panel doc-form admin-assignment-form" onSubmit={saveCourseAssignments}>
        <h2>Update {row.full_name}'s assignments</h2>
        <label>Department<select required value={editDepartmentId} onChange={event => { setEditDepartmentId(event.target.value); setEditCourseIds([]) }}>{departments.map(department => <option key={department.id} value={department.id}>{department.name}</option>)}</select></label>
        <label>Assigned courses (select multiple)<select multiple size={Math.min(6, Math.max(2, editCourses.length))} value={editCourseIds.map(String)} onChange={event => setEditCourseIds(Array.from(event.currentTarget.selectedOptions, option => Number(option.value)))}>{editCourses.map(course => <option key={course.id} value={course.id}>{course.code} · {course.title}</option>)}</select></label>
        <p className="doc-muted">Changing a lecturer’s department returns their affiliation to pending verification.</p>
        <div className="doc-row-actions"><button className="button" type="submit">Save assignments</button><button className="button button-outline" type="button" onClick={() => setEditingLecturerId(null)}>Cancel</button></div>
      </form>}
    </Fragment>)}</div>
  </section>
}

function AdminMemberDirectory({ token }: { token: string | null }) {
  type Member = { id: number; full_name: string; username: string | null; email: string; role: string; is_active: boolean; email_verified: boolean; created_at: string; has_lecturer_profile: boolean; academic_status: string; academic_department_id: number | null }
  const [members, setMembers] = useState<Member[]>([])
  const [memberSearch, setMemberSearch] = useState('')
  const [memberSkip, setMemberSkip] = useState(0)
  const [memberTotal, setMemberTotal] = useState(0)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [pendingMemberAction, setPendingMemberAction] = useState<{ member: Member; action: 'disable' | 'reactivate' } | null>(null)
  const [actionReason, setActionReason] = useState('')
  const [actionBusy, setActionBusy] = useState(false)
  const [pendingDeleteMember, setPendingDeleteMember] = useState<Member | null>(null)
  const [deleteEmail, setDeleteEmail] = useState('')
  const [deleteBusy, setDeleteBusy] = useState(false)
  const pageSize = 100

  const loadMembers = useCallback(async (query: string, skip = 0, append = false) => {
    if (!token) return
    try {
      const result = await api<{ items: Member[]; total: number }>(
        `/api/admin/members?search=${encodeURIComponent(query)}&skip=${skip}&limit=${pageSize}`,
        {}, token,
      )
      setMembers(previous => append ? [...previous, ...result.items] : result.items)
      setMemberTotal(result.total)
      setMemberSkip(skip + result.items.length)
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not load member directory.') }
  }, [token])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadMembers('', 0, false)
  }, [loadMembers])

  async function updateRole(member: Member, role: string) {
    if (!token || role === member.role) return
    setError(''); setNotice('')
    try {
      await api(`/api/admin/members/${member.id}/role`, { method: 'PUT', body: JSON.stringify({ role }) }, token)
      setNotice(`${member.full_name}'s role changed. Their existing sessions were revoked.`)
      await loadMembers(memberSearch)
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not update role.') }
  }

  function toggleAccess(member: Member) {
    setError('')
    setNotice('')
    setActionReason('')
    setPendingMemberAction({ member, action: member.is_active ? 'disable' : 'reactivate' })
  }

  async function submitMemberAction(event: FormEvent) {
    event.preventDefault()
    if (!token || !pendingMemberAction) return
    const { member, action } = pendingMemberAction
    const reason = actionReason.trim()
    if (action === 'disable' && reason.length < 5) {
      setError('Enter a reason with at least 5 characters.')
      return
    }
    setActionBusy(true)
    setError('')
    setNotice('')
    try {
      if (action === 'disable') {
        await api(`/api/admin/members/${member.id}/suspend`, {
          method: 'POST',
          body: JSON.stringify({ reason }),
        }, token)
        setNotice('Account access disabled and sessions revoked. Records were retained.')
      } else {
        await api(`/api/admin/members/${member.id}/reactivate`, { method: 'POST' }, token)
        setNotice('Account reactivated.')
      }
      setPendingMemberAction(null)
      setActionReason('')
      await loadMembers(memberSearch)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not update account access.')
    } finally {
      setActionBusy(false)
    }
  }

  function requestMemberDeletion(member: Member) {
    setError('')
    setNotice('')
    setDeleteEmail('')
    setPendingDeleteMember(member)
  }

  async function submitMemberDeletion(event: FormEvent) {
    event.preventDefault()
    if (!token || !pendingDeleteMember) return
    if (deleteEmail.trim().toLowerCase() !== pendingDeleteMember.email.toLowerCase()) {
      setError('Type the account email exactly to confirm deletion.')
      return
    }
    setDeleteBusy(true)
    setError('')
    setNotice('')
    try {
      await api(`/api/admin/members/${pendingDeleteMember.id}`, { method: 'DELETE' }, token)
      setPendingDeleteMember(null)
      setDeleteEmail('')
      setNotice('Account identity removed and email released. Uploaded documents and audit history were retained.')
      await loadMembers(memberSearch)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not delete the account.')
    } finally {
      setDeleteBusy(false)
    }
  }

  return <section className="page-container inner-page">
    <div className="page-kicker">PLATFORM OVERSIGHT</div>
    <h1 className="inner-title">Member directory<span>.</span></h1>
    <p className="inner-lede">Manage registered accounts, roles, and sign-in access. Role changes revoke existing sessions.</p>
    {error && <div className="form-alert form-error" role="alert">{error}</div>}
    {notice && <div className="form-alert form-success" role="status">{notice}</div>}

    <div className="doc-panel">
      <div className="doc-toolbar"><div><h2>Member directory</h2><p>{memberTotal} accounts · role changes revoke active sessions.</p></div></div>
      <div className="catalog-toolbar">
        <div className="search-field"><Icon name="search"/><input value={memberSearch} onChange={event => setMemberSearch(event.target.value)} placeholder="Search name, username or email"/></div>
        <button className="button button-outline" onClick={() => void loadMembers(memberSearch)}>Search</button>
      </div>
      <div className="doc-list">{members.map(member => <article className="doc-row admin-member-row" key={member.id}>
        <div className="doc-row-main"><b>{member.full_name}</b><span>{member.email}{member.username ? ` · @${member.username}` : ''}</span><small>{member.role} · {member.email_verified ? 'Email verified' : 'Unverified'} · Academic affiliation: {member.academic_status.replaceAll('_', ' ')} · {member.is_active ? 'Active' : 'Disabled'} · Joined {new Date(member.created_at).toLocaleDateString()}</small></div>
        <div className="doc-row-actions">
          {member.role !== 'administrator' ? <label className="admin-role-control">Role<select value={member.role} onChange={event => void updateRole(member, event.target.value)}><option value="student">Student</option>{member.has_lecturer_profile && <option value="lecturer">Lecturer</option>}<option value="department_reviewer" disabled={member.academic_status !== 'verified' && member.role !== 'department_reviewer'}>Department reviewer</option></select></label> : <span className="role-pill">Administrator</span>}
          {member.role !== 'administrator' && <>
            <button className={`button button-small ${member.is_active ? 'button-danger' : 'button-outline'}`} onClick={() => toggleAccess(member)}>{member.is_active ? 'Disable access' : 'Reactivate'}</button>
            <button className="button button-small button-danger" onClick={() => requestMemberDeletion(member)}>Delete account</button>
          </>}
        </div>
      </article>)}</div>
      {memberSkip < memberTotal && <button className="button button-outline" onClick={() => void loadMembers(memberSearch, memberSkip, true)}>Load more members</button>}
      {!members.length && <div className="notice">No accounts matched that search.</div>}
    </div>

    {pendingMemberAction && <div className="doc-modal-backdrop" role="presentation" onMouseDown={event => {
      if (event.target === event.currentTarget && !actionBusy) setPendingMemberAction(null)
    }}>
      <section className="doc-modal" role="dialog" aria-modal="true" aria-labelledby="admin-member-action-title">
        <div className="doc-modal-head">
          <div>
            <div className="page-kicker">MEMBER ACCESS</div>
            <h2 id="admin-member-action-title">{pendingMemberAction.action === 'disable' ? 'Disable account access?' : 'Reactivate account?'}</h2>
          </div>
          <button className="icon-button" type="button" disabled={actionBusy} onClick={() => setPendingMemberAction(null)} aria-label="Close">×</button>
        </div>
        <p className="doc-muted">{pendingMemberAction.action === 'disable'
          ? `Disable sign-in for ${pendingMemberAction.member.full_name}? Account data and audit history will be retained.`
          : `Allow ${pendingMemberAction.member.full_name} to sign in again?`}</p>
        <form className="doc-form" onSubmit={submitMemberAction}>
          {pendingMemberAction.action === 'disable' && <label>Reason for disabling access
            <textarea autoFocus rows={3} value={actionReason} onChange={event => setActionReason(event.target.value)} required minLength={5} />
          </label>}
          {error && <div className="form-alert form-error" role="alert">{error}</div>}
          <div className="doc-row-actions">
            <button className="button button-outline" type="button" disabled={actionBusy} onClick={() => setPendingMemberAction(null)}>Cancel</button>
            <button className={`button ${pendingMemberAction.action === 'disable' ? 'button-danger' : ''}`} type="submit" disabled={actionBusy}>
              {actionBusy ? 'Updating…' : pendingMemberAction.action === 'disable' ? 'Disable access' : 'Reactivate account'}
            </button>
          </div>
        </form>
      </section>
    </div>}
    {pendingDeleteMember && <div className="doc-modal-backdrop" role="presentation" onMouseDown={event => {
      if (event.target === event.currentTarget && !deleteBusy) setPendingDeleteMember(null)
    }}>
      <section className="doc-modal" role="dialog" aria-modal="true" aria-labelledby="admin-delete-member-title">
        <div className="doc-modal-head">
          <div>
            <div className="page-kicker">PERMANENT ACCOUNT ACTION</div>
            <h2 id="admin-delete-member-title">Delete account?</h2>
          </div>
          <button className="icon-button" type="button" disabled={deleteBusy} onClick={() => setPendingDeleteMember(null)} aria-label="Close">×</button>
        </div>
        <p className="doc-muted">
          Remove {pendingDeleteMember.full_name}'s identity and release the email for a new registration.
          Uploaded documents remain attributed to an anonymized account, and audit history is retained.
        </p>
        <form className="doc-form" onSubmit={submitMemberDeletion}>
          <label>Type {pendingDeleteMember.email} to confirm
            <input autoFocus autoComplete="off" value={deleteEmail} onChange={event => setDeleteEmail(event.target.value)} />
          </label>
          {error && <div className="form-alert form-error" role="alert">{error}</div>}
          <div className="doc-row-actions">
            <button className="button button-outline" type="button" disabled={deleteBusy} onClick={() => setPendingDeleteMember(null)}>Cancel</button>
            <button className="button button-danger" type="submit" disabled={deleteBusy || deleteEmail.trim().toLowerCase() !== pendingDeleteMember.email.toLowerCase()}>
              {deleteBusy ? 'Deleting…' : 'Delete account & release email'}
            </button>
          </div>
        </form>
      </section>
    </div>}
  </section>
}

function AdminActivityLog({ token }: { token: string | null }) {
  type Activity = {
    id: number
    user_id: number | null
    action: string
    entity_type: string | null
    entity_id: number | null
    details: string | null
    created_at: string
    archived_at: string | null
    archived_by: number | null
  }
  const [activities, setActivities] = useState<Activity[]>([])
  const [activitySkip, setActivitySkip] = useState(0)
  const [activityTotal, setActivityTotal] = useState(0)
  const [activityFilter, setActivityFilter] = useState('')
  const [showArchived, setShowArchived] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const pageSize = 50

  const loadActivities = useCallback(async (skip = 0, append = false, filter = '') => {
    if (!token) return
    try {
      const result = await api<{ items: Activity[]; total: number }>(
        `/api/admin/audit?skip=${skip}&limit=${pageSize}&archived=${showArchived}${filter ? `&action=${encodeURIComponent(filter)}` : ''}`,
        {}, token,
      )
      setActivities(previous => append ? [...previous, ...result.items] : result.items)
      setActivityTotal(result.total)
      setActivitySkip(skip + result.items.length)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load activity log.')
    }
  }, [token, showArchived])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadActivities()
  }, [loadActivities])

  async function setActivityArchived(activity: Activity, archived: boolean) {
    if (!token) return
    setError('')
    setNotice('')
    try {
      await api(`/api/admin/audit/${activity.id}/${archived ? 'archive' : 'restore'}`, { method: 'POST' }, token)
      setNotice(archived
        ? 'Activity archived. The audit record has been retained.'
        : 'Activity restored to the active log.')
      await loadActivities(0, false, activityFilter)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not update activity record.')
    }
  }

  function switchActivityView(archived: boolean) {
    if (archived === showArchived) return
    setShowArchived(archived)
    setActivityFilter('')
    setActivitySkip(0)
    setError('')
    setNotice('')
  }

  return <section className="page-container inner-page admin-activity-page">
    <div className="page-kicker">PLATFORM OVERSIGHT</div>
    <h1 className="inner-title">Activity log<span>.</span></h1>
    <p className="inner-lede">Review security, document, and administration events. Archiving hides an entry from the active list without deleting its audit record.</p>
    {error && <div className="form-alert form-error" role="alert">{error}</div>}
    {notice && <div className="form-alert form-success" role="status">{notice}</div>}

    <div className="doc-panel">
      <div className="doc-toolbar activity-toolbar">
        <div>
          <h2>{showArchived ? 'Archived activity' : 'Recent activity'}</h2>
          <p>{activityTotal} {showArchived ? 'archived' : 'active'} records · newest first.</p>
        </div>
        <div className="activity-tabs" role="tablist" aria-label="Activity status">
          <button type="button" role="tab" aria-selected={!showArchived} onClick={() => switchActivityView(false)}>Active</button>
          <button type="button" role="tab" aria-selected={showArchived} onClick={() => switchActivityView(true)}>Archived</button>
        </div>
      </div>
      <div className="catalog-toolbar">
        <div className="search-field"><Icon name="search"/><input value={activityFilter} onChange={event => setActivityFilter(event.target.value)} placeholder="Filter by action, e.g. document"/></div>
        <button className="button button-outline" onClick={() => void loadActivities(0, false, activityFilter)}>Apply filter</button>
      </div>
      <div className="doc-list">{activities.map(activity => <article className="doc-row activity-row" key={activity.id}>
        <div className="doc-row-main">
          <b>{activity.action.replaceAll('.', ' ')}</b>
          <span>Actor {activity.user_id ?? 'system'} · {activity.entity_type || 'event'}{activity.entity_id ? ` #${activity.entity_id}` : ''}</span>
          {activity.details && <small>{activity.details}</small>}
          <small>{new Date(activity.created_at).toLocaleString()}</small>
        </div>
        <div className="doc-row-actions">
          {showArchived && <span className="status-pill status-rejected">Archived</span>}
          {activity.action.startsWith('audit.activity.')
            ? <span className="status-pill">Retained audit entry</span>
            : <button
              className="button button-small button-outline"
              aria-label={`${showArchived ? 'Restore' : 'Archive'} activity event ${activity.id}`}
              onClick={() => void setActivityArchived(activity, !showArchived)}
            >{showArchived ? 'Restore' : 'Archive'}</button>}
        </div>
      </article>)}</div>
      {activitySkip < activityTotal && <button className="button button-outline" onClick={() => void loadActivities(activitySkip, true, activityFilter)}>Load {showArchived ? 'older archived' : 'older'} activity</button>}
      {!activities.length && <div className="notice">{showArchived ? 'No activity has been archived.' : 'No activity has been recorded yet.'}</div>}
    </div>
  </section>
}

function AdminAcademicAccess({ token }: { token: string | null }) {
  type Affiliation = {
    id: number; user_id: number; full_name: string; email: string; role: string
    status: string; department_id: number; department_name: string; faculty_name: string
    university_name: string; programme_name: string | null; level: string | null
    submitted_at: string; review_note: string | null
  }
  type Member = {
    id: number; full_name: string; email: string; role: string; is_active: boolean
    academic_status: string; academic_department_id: number | null
  }
  type Department = { id: number; name: string }
  type CourseRow = { id: number; code: string; title: string; department_id: number }
  type Assignment = {
    id: number; user_id: number; reviewer_name: string; reviewer_email: string
    department_id: number | null; department_name: string | null
    course_id: number | null; course_code: string | null; course_title: string | null; active: boolean
  }
  const [affiliations, setAffiliations] = useState<Affiliation[]>([])
  const [reviewers, setReviewers] = useState<Member[]>([])
  const [departments, setDepartments] = useState<Department[]>([])
  const [courses, setCourses] = useState<CourseRow[]>([])
  const [assignments, setAssignments] = useState<Assignment[]>([])
  const [reviewerId, setReviewerId] = useState('')
  const [scopeType, setScopeType] = useState<'department' | 'course'>('department')
  const [scopeId, setScopeId] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [pendingReview, setPendingReview] = useState<Affiliation | null>(null)
  const [reviewNote, setReviewNote] = useState('')
  const [pendingRevoke, setPendingRevoke] = useState<Assignment | null>(null)

  const load = useCallback(async () => {
    if (!token) return
    setError('')
    try {
      const [affiliationResult, memberResult, departmentResult, courseResult, assignmentResult] = await Promise.all([
        api<{ items: Affiliation[] }>('/api/admin/academic-affiliations?status_filter=pending', {}, token),
        api<{ items: Member[] }>('/api/admin/members?role=department_reviewer&limit=200', {}, token),
        api<Department[]>('/api/academic/departments', {}, token),
        api<{ items: CourseRow[] }>('/api/academic/courses?limit=200', {}, token),
        api<{ items: Assignment[] }>('/api/admin/reviewer-assignments', {}, token),
      ])
      setAffiliations(affiliationResult.items)
      setReviewers(memberResult.items)
      setDepartments(departmentResult)
      setCourses(courseResult.items)
      setAssignments(assignmentResult.items)
      if (!reviewerId) {
        const eligible = memberResult.items.find(member => member.is_active && member.academic_status === 'verified')
        if (eligible) setReviewerId(String(eligible.id))
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load academic access settings.')
    }
  }, [token, reviewerId])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load()
  }, [load])

  async function reviewAffiliation(item: Affiliation, decision: 'verified' | 'rejected') {
    if (!token) return
    if (decision === 'rejected') {
      setError('')
      setNotice('')
      setReviewNote('')
      setPendingReview(item)
      return
    }
    await saveAffiliationReview(item, decision)
  }

  async function saveAffiliationReview(item: Affiliation, decision: 'verified' | 'rejected', note = '') {
    if (!token) return
    if (decision === 'rejected' && !note.trim()) {
      setError('Enter a reason for rejecting this affiliation.')
      return
    }
    setBusy(true); setError(''); setNotice('')
    try {
      await api(`/api/admin/academic-affiliations/${item.id}/review`, {
        method: 'POST',
        body: JSON.stringify({ decision, note: note?.trim() || null }),
      }, token)
      setNotice(`${item.full_name}'s academic affiliation was ${decision}.`)
      setPendingReview(null)
      setReviewNote('')
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not review academic affiliation.')
    } finally { setBusy(false) }
  }

  async function assignReviewer(event: FormEvent) {
    event.preventDefault()
    if (!token || !reviewerId || !scopeId) return
    setBusy(true); setError(''); setNotice('')
    const payload = scopeType === 'department'
      ? { user_id: Number(reviewerId), department_id: Number(scopeId), course_id: null }
      : { user_id: Number(reviewerId), department_id: null, course_id: Number(scopeId) }
    try {
      await api('/api/admin/reviewer-assignments', { method: 'POST', body: JSON.stringify(payload) }, token)
      setNotice('Reviewer assignment saved. The reviewer can now moderate only this scope.')
      setScopeId('')
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not assign reviewer.')
    } finally { setBusy(false) }
  }

  function revokeAssignment(assignment: Assignment) {
    setError('')
    setNotice('')
    setPendingRevoke(assignment)
  }

  async function confirmRevokeAssignment() {
    if (!token || !pendingRevoke) return
    setBusy(true); setError(''); setNotice('')
    try {
      await api(`/api/admin/reviewer-assignments/${pendingRevoke.id}/revoke`, { method: 'POST' }, token)
      setNotice('Reviewer scope revoked.')
      setPendingRevoke(null)
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not revoke reviewer scope.')
    } finally { setBusy(false) }
  }

  const eligibleReviewers = reviewers.filter(member =>
    member.is_active && member.academic_status === 'verified',
  )
  const selectedReviewer = eligibleReviewers.find(member => String(member.id) === reviewerId)
  const availableDepartments = departments.filter(department =>
    !selectedReviewer || department.id === selectedReviewer.academic_department_id,
  )
  const availableCourses = courses.filter(course =>
    !selectedReviewer || course.department_id === selectedReviewer.academic_department_id,
  )

  return <section className="page-container inner-page admin-academic-access">
    <div className="page-kicker">ACADEMIC ACCESS CONTROL</div>
    <h1 className="inner-title">Affiliations & reviewer scopes<span>.</span></h1>
    <p className="inner-lede">Verify member-submitted school, faculty and department details, then assign reviewers only within verified academic scopes.</p>
    {error && <div className="form-alert form-error" role="alert">{error}</div>}
    {notice && <div className="form-alert form-success" role="status">{notice}</div>}

    <div className="doc-panel">
      <div className="doc-toolbar"><div><h2>Affiliation verification queue</h2><p>{affiliations.length} pending requests · verify details against official records.</p></div><button className="button button-outline" disabled={busy} onClick={() => void load()}>Refresh</button></div>
      {affiliations.length ? <div className="doc-list">{affiliations.map(item => <article className="doc-row admin-academic-row" key={item.id}>
        <div className="doc-row-main"><b>{item.full_name} · {item.role.replaceAll('_', ' ')}</b><span>{item.email}</span><small>{item.university_name} · {item.faculty_name} · {item.department_name}{item.programme_name ? ` · ${item.programme_name}` : ''}{item.level ? ` · ${item.level}` : ''}</small><small>Submitted {new Date(item.submitted_at).toLocaleString()}</small></div>
        <div className="doc-row-actions"><button className="button button-small" disabled={busy} onClick={() => void reviewAffiliation(item, 'verified')}>Verify</button><button className="button button-small button-danger" disabled={busy} onClick={() => void reviewAffiliation(item, 'rejected')}>Reject</button></div>
      </article>)}</div> : <div className="notice">No academic affiliations are waiting for review.</div>}
    </div>

    <div className="doc-panel">
      <div className="doc-toolbar"><div><h2>Assign reviewer scope</h2><p>Reviewers must have a verified affiliation and can only be assigned to their own department or its courses.</p></div></div>
      <form className="doc-form" onSubmit={assignReviewer}>
        <label>Verified reviewer<select required value={reviewerId} onChange={event => { setReviewerId(event.target.value); setScopeId('') }}><option value="">Select reviewer</option>{eligibleReviewers.map(member => <option key={member.id} value={member.id}>{member.full_name} · {member.email}</option>)}</select></label>
        <label>Scope type<select value={scopeType} onChange={event => { setScopeType(event.target.value as typeof scopeType); setScopeId('') }}><option value="department">Department</option><option value="course">Course</option></select></label>
        <label>{scopeType === 'department' ? 'Department scope' : 'Course scope'}<select required value={scopeId} onChange={event => setScopeId(event.target.value)}><option value="">Select {scopeType}</option>{scopeType === 'department' ? availableDepartments.map(department => <option key={department.id} value={department.id}>{department.name}</option>) : availableCourses.map(course => <option key={course.id} value={course.id}>{course.code} · {course.title}</option>)}</select></label>
        {!eligibleReviewers.length && <p className="form-alert form-warning">No active reviewers with verified academic affiliations are available. Review a pending affiliation, then assign the reviewer role in the member directory.</p>}
        <button className="button" disabled={busy || !reviewerId || !scopeId}>Assign reviewer</button>
      </form>
    </div>

    <div className="doc-panel">
      <div className="doc-toolbar"><div><h2>Current assignments</h2><p>{assignments.filter(item => item.active).length} active scopes.</p></div></div>
      {assignments.length ? <div className="doc-list">{assignments.map(assignment => <article className="doc-row admin-academic-row" key={assignment.id}>
        <div className="doc-row-main"><b>{assignment.reviewer_name}</b><span>{assignment.reviewer_email}</span><small>{assignment.department_name ? `Department: ${assignment.department_name}` : `Course: ${assignment.course_code} · ${assignment.course_title}`}</small></div>
        <div className="doc-row-actions"><span className={`status-pill status-${assignment.active ? 'verified' : 'rejected'}`}>{assignment.active ? 'Active' : 'Revoked'}</span>{assignment.active && <button className="button button-small button-outline" disabled={busy} onClick={() => void revokeAssignment(assignment)}>Revoke</button>}</div>
      </article>)}</div> : <div className="notice">No reviewer scopes have been assigned yet.</div>}
    </div>
    {pendingReview && <div className="doc-modal-backdrop" role="presentation" onMouseDown={event => {
      if (event.target === event.currentTarget && !busy) setPendingReview(null)
    }}>
      <section className="doc-modal" role="dialog" aria-modal="true" aria-labelledby="admin-review-title">
        <div className="doc-modal-head">
          <div>
            <div className="page-kicker">AFFILIATION REVIEW</div>
            <h2 id="admin-review-title">Reject affiliation?</h2>
          </div>
          <button className="icon-button" type="button" disabled={busy} onClick={() => setPendingReview(null)} aria-label="Close">×</button>
        </div>
        <p className="doc-muted">Provide a reason for rejecting {pendingReview.full_name}'s submitted academic affiliation.</p>
        <form className="doc-form" onSubmit={event => {
          event.preventDefault()
          void saveAffiliationReview(pendingReview, 'rejected', reviewNote)
        }}>
          <label>Reason for rejection
            <textarea autoFocus rows={3} value={reviewNote} onChange={event => setReviewNote(event.target.value)} required />
          </label>
          {error && <div className="form-alert form-error" role="alert">{error}</div>}
          <div className="doc-row-actions">
            <button className="button button-outline" type="button" disabled={busy} onClick={() => setPendingReview(null)}>Cancel</button>
            <button className="button button-danger" type="submit" disabled={busy}>{busy ? 'Saving…' : 'Reject affiliation'}</button>
          </div>
        </form>
      </section>
    </div>}
    {pendingRevoke && <div className="doc-modal-backdrop" role="presentation" onMouseDown={event => {
      if (event.target === event.currentTarget && !busy) setPendingRevoke(null)
    }}>
      <section className="doc-modal" role="dialog" aria-modal="true" aria-labelledby="admin-revoke-title">
        <div className="doc-modal-head">
          <div>
            <div className="page-kicker">REVIEWER ACCESS</div>
            <h2 id="admin-revoke-title">Revoke reviewer scope?</h2>
          </div>
          <button className="icon-button" type="button" disabled={busy} onClick={() => setPendingRevoke(null)} aria-label="Close">×</button>
        </div>
        <p className="doc-muted">Remove {pendingRevoke.reviewer_name}'s access to {pendingRevoke.department_name ? `the ${pendingRevoke.department_name} department` : `${pendingRevoke.course_code} · ${pendingRevoke.course_title}`} review queue?</p>
        {error && <div className="form-alert form-error" role="alert">{error}</div>}
        <div className="doc-row-actions">
          <button className="button button-outline" type="button" disabled={busy} onClick={() => setPendingRevoke(null)}>Cancel</button>
          <button className="button button-danger" type="button" disabled={busy} onClick={() => void confirmRevokeAssignment()}>{busy ? 'Saving…' : 'Revoke scope'}</button>
        </div>
      </section>
    </div>}
  </section>
}

function Footer({ onNavigate }: { onNavigate: (p: Page) => void }) {
  return <footer className="footer"><div className="page-container footer-main"><div><button className="brand footer-brand" onClick={() => onNavigate('home')}><span className="brand-mark"><Icon name="book"/></span><span>StudyBridge<span className="brand-ai"> AI</span></span></button><p>A connected academic learning space built to help students learn smarter and go further.</p></div><div className="footer-links"><div><b>Explore</b><button onClick={() => onNavigate('catalog')}>Academic catalogue</button><button onClick={() => onNavigate('signup')}>Create account</button></div><div><b>Account</b><button onClick={() => onNavigate('login')}>Sign in</button><button onClick={() => onNavigate('forgot')}>Password recovery</button></div></div></div><div className="page-container footer-bottom"><span>© {new Date().getFullYear()} StudyBridge AI. All rights reserved.</span><span>Built for better learning.</span></div></footer>
}
export default App
