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
  appCatalog: [],
  installedApps: [],
  appTaskById: {},
  appConfigById: {},
  appVersionsByAppId: {},
  appsError: '',
})

export const robotState = reactive(initialState())

export function resetStateForLogout() {
  robotState.token = ''
  localStorage.removeItem('token')
  robotState.me = null
  robotState.config = null
  robotState.configText = ''
  robotState.appCatalog = []
  robotState.installedApps = []
  robotState.appTaskById = {}
  robotState.appConfigById = {}
  robotState.appVersionsByAppId = {}
  robotState.appsError = ''
}
