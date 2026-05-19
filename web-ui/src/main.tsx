import React from 'react';
import ReactDOM from 'react-dom/client';
import { ThemeProvider } from '@openuidev/react-ui';
import App from './App';
import { hestiaTheme } from './theme';
import './index.css';
import './styles/global.css';
import './styles/utilities.css';
import './styles/components.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ThemeProvider lightTheme={hestiaTheme}>
      <App />
    </ThemeProvider>
  </React.StrictMode>
);
