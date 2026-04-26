import ReactDOM from 'react-dom/client'
import App from './App.tsx'
import { AuthProvider } from './components/auth/AuthContext'
import './index.css'

// 确保DOM已加载
document.addEventListener('DOMContentLoaded', () => {
  const rootElement = document.getElementById('root')
  
  if (!rootElement) {
    throw new Error('Root element not found')
  }

  const root = ReactDOM.createRoot(rootElement)
  
  root.render(
    <AuthProvider>
      <App />
    </AuthProvider>,
  )
})
