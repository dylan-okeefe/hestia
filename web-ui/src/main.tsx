import React from 'react';
import ReactDOM from 'react-dom/client';
import { ThemeProvider } from '@openuidev/react-ui';
import App from './App';
import ErrorBoundary from './components/layout/ErrorBoundary';
import { hestiaTheme } from './theme';
import './index.css';
import './styles/global.css';
import './styles/utilities.css';
import './styles/components.css';
import './components/ResponsiveTable.css';
import './components/Modal.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ThemeProvider lightTheme={hestiaTheme}>
      <ErrorBoundary>
        <App />
      </ErrorBoundary>
    </ThemeProvider>
  </React.StrictMode>
);
