import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

const vscode = acquireVsCodeApi()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App vscode={vscode}/>
  </StrictMode>,
)
