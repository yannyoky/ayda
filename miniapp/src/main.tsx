import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from './app/App'
import './fonts'
import './styles.css'
import { signalReady } from './telegram/webapp'

const root = document.getElementById('root')
if (!root) throw new Error('#root is missing')

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
signalReady()
