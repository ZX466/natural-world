import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import { runtime } from './game/runtime';
import './index.css';

runtime.start();

createRoot(document.getElementById('root') as HTMLElement).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
