import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Navbar from './components/Navbar'
import Dashboard from './pages/Dashboard'
import Wallet from './pages/Wallet'
import History from './pages/History'
import Settings from './pages/Settings'

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-bg lg:flex">
        <Navbar />
        <main className="min-h-screen lg:flex-1 lg:ml-56">
          <div className="max-w-6xl mx-auto px-4 pt-20 pb-28 sm:px-6 lg:px-10 lg:pt-10 lg:pb-16">
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/wallet" element={<Wallet />} />
              <Route path="/history" element={<History />} />
              <Route path="/settings" element={<Settings />} />
            </Routes>
          </div>
        </main>
      </div>
    </BrowserRouter>
  )
}
