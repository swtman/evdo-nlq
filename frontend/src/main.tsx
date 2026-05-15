/**
 * Application entry point.
 *
 * This is the first file Vite executes. It mounts the root <App/> component
 * into the <div id="root"> element defined in index.html.
 *
 * StrictMode deliberately runs effects and renders twice in development to
 * surface bugs early (e.g. missing cleanup in useEffect). It has no effect
 * in production builds.
 *
 * The `!` after getElementById is a TypeScript non-null assertion — safe here
 * because index.html always contains <div id="root">.
 */

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
