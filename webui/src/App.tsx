import { useCallback, useContext, createContext, useState, type ReactNode } from "react"
import {
  Routes,
  Route,
  Navigate,
  NavLink,
  useNavigate,
  useParams,
} from "react-router-dom"
import type { TaskEvent, TaskState } from "./types/task"
import { useTaskWS } from "./hooks/useTaskWS"
import { ToastProvider } from "./components/Toast"
import TaskNew from "./pages/TaskNew"
import TaskList from "./pages/TaskList"
import TaskDetail from "./pages/TaskDetail"

interface AppData {
  refreshKey: number
  bumpRefresh: () => void
  wsTasks: Record<string, { state: TaskState }>
}

const AppDataContext = createContext<AppData | null>(null)

function useAppData(): AppData {
  const ctx = useContext(AppDataContext)
  if (!ctx) throw new Error("useAppData must be used within AppDataProvider")
  return ctx
}

function DataProvider({ children }: { children: ReactNode }) {
  const [refreshKey, setRefreshKey] = useState(0)
  const [wsTasks, setWsTasks] = useState<Record<string, { state: TaskState }>>({})

  const handleTaskWs = useCallback((message: TaskEvent) => {
    const event = message.event.TaskStateChanged
    if (!event) return
    setWsTasks((prev) => ({
      ...prev,
      [event.task_id]: { state: event.state },
    }))
  }, [])

  useTaskWS(handleTaskWs)

  return (
    <AppDataContext.Provider
      value={{
        refreshKey,
        bumpRefresh: () => setRefreshKey((k) => k + 1),
        wsTasks,
      }}
    >
      {children}
    </AppDataContext.Provider>
  )
}

const tabLinkClass = ({ isActive }: { isActive: boolean }) =>
  isActive ? "text-blue-600 font-medium" : "text-gray-500 hover:text-gray-700"

function TasksHome() {
  const { refreshKey, bumpRefresh, wsTasks } = useAppData()
  const navigate = useNavigate()
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
      <div className="md:col-span-1">
        <TaskNew onCreated={bumpRefresh} />
      </div>
      <div className="md:col-span-2 space-y-4">
        <TaskList
          refreshKey={refreshKey}
          onSelect={(id) => navigate(`/tasks/${id}`)}
          wsUpdates={wsTasks}
        />
      </div>
    </div>
  )
}

function TaskDetailPage() {
  const { wsTasks } = useAppData()
  const { taskId } = useParams()
  const navigate = useNavigate()
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
      <div className="md:col-span-1" />
      <div className="md:col-span-2 space-y-4">
        <TaskDetail
          taskId={taskId || null}
          onBack={() => navigate("/tasks")}
          liveUpdates={wsTasks}
        />
      </div>
    </div>
  )
}

function Layout() {
  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b px-6 py-3 flex items-center justify-between">
        <h1 className="text-xl font-bold text-gray-800">Robot Task Console</h1>
        <div className="flex gap-4 items-center">
          <NavLink to="/tasks" className={tabLinkClass}>
            Tasks
          </NavLink>
        </div>
      </header>

      <main className="max-w-4xl mx-auto p-6">
        <Routes>
          <Route path="/" element={<Navigate to="/tasks" replace />} />
          <Route path="/tasks" element={<TasksHome />} />
          <Route path="/tasks/:taskId" element={<TaskDetailPage />} />
          <Route path="*" element={<Navigate to="/tasks" replace />} />
        </Routes>
      </main>
    </div>
  )
}

export default function App() {
  return (
    <ToastProvider>
      <DataProvider>
        <Layout />
      </DataProvider>
    </ToastProvider>
  )
}
