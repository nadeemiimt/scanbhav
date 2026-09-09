import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import ErrorBoundary from './components/ErrorBoundary'
import { AuthProvider } from './context/AuthContext'
import LoginModal from './components/auth/LoginModal'
import './site.css'
import './future-theme.css'
import './theme-overrides.css'
import { applySettings, loadSettings } from './lib/siteSettings'

applySettings(loadSettings())

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <ErrorBoundary>
      <AuthProvider>
        <App />
        <LoginModal />
      </AuthProvider>
    </ErrorBoundary>
  </StrictMode>,
)
