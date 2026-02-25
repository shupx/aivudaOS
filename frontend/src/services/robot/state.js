import { reactive } from 'vue'

const initialState = () => ({
  username: 'admin',
  password: 'admin123',
  token: localStorage.getItem('token') || '',
  me: null,
  loginError: '',
  busy: false,
  config: null,
  configText: '',
  saveError: '',
  saveOk: '',
  snapshot: null,
  wsStatus: 'disconnected',
  telemetry: null,
  reconnectAttempt: 0,
  appCatalog: [],
  installedApps: [],
  appTaskById: {},
  appConfigById: {},
  appsError: '',
})

export const robotState = reactive(initialState())

export function resetStateForLogout() {
  robotState.token = ''
  localStorage.removeItem('token')
  robotState.me = null
  robotState.config = null
  robotState.configText = ''
  robotState.snapshot = null
  robotState.telemetry = null
  robotState.wsStatus = 'disconnected'
  robotState.reconnectAttempt = 0
  robotState.appCatalog = []
  robotState.installedApps = []
  robotState.appTaskById = {}
  robotState.appConfigById = {}
  robotState.appsError = ''
}
