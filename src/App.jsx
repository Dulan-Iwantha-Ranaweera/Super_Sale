import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import { useAuth } from './context/AuthContext'
import { Spinner } from './components/ui'
import Customers from './pages/Customers'
import Dashboard from './pages/Dashboard'
import DetailsInput from './pages/DetailsInput'
import Inventory from './pages/Inventory'
import IPF from './pages/IPF'
import Login from './pages/Login'
import POS from './pages/POS'
import Reports from './pages/Reports'
import SalesHistory from './pages/SalesHistory'
import Settings from './pages/Settings'

function OwnerRoute({ children }) {
  const { isOwner } = useAuth()
  return isOwner ? children : <Navigate to="/" replace />
}

export default function App() {
  const { user, checking } = useAuth()

  if (checking) {
    return (
      <div className="flex h-full items-center justify-center">
        <Spinner label="Restoring your session…" />
      </div>
    )
  }

  if (!user) return <Login />

  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="inventory" element={<Inventory />} />
        <Route path="pos" element={<POS />} />
        <Route path="sales-history" element={<SalesHistory />} />
        <Route path="customers" element={<Customers />} />
        <Route
          path="reports"
          element={
            <OwnerRoute>
              <Reports />
            </OwnerRoute>
          }
        />
        <Route
          path="ipf"
          element={
            <OwnerRoute>
              <IPF />
            </OwnerRoute>
          }
        />
        <Route
          path="details-input"
          element={
            <OwnerRoute>
              <DetailsInput />
            </OwnerRoute>
          }
        />
        <Route path="settings" element={<Settings />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
