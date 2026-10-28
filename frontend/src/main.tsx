import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import AuthGate from './components/AuthGate';
import ErrorBoundary from './components/ErrorBoundary';
import './styles.css';

ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><ErrorBoundary><BrowserRouter><AuthGate/></BrowserRouter></ErrorBoundary></React.StrictMode>);
