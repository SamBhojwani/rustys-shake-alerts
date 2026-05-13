import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import { initTheme } from './theme'
import App from './App.jsx'

// Set saved theme as early as possible (before render) to avoid
// a flash of the wrong theme. CSS handles the OS-driven default,
// so this is only needed when the user has an explicit preference.
initTheme()

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
