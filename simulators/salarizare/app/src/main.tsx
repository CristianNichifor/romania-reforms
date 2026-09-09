import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import App from './App';
import '@cristiannichifor/civic-ui/styles.css';
import './styles.css';
import './civic-pilot.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
