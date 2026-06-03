const { app, BrowserWindow, dialog, shell } = require('electron')
const path = require('path')
const { spawn } = require('child_process')

let mainWindow = null
let backendProcess = null

// 后端启动配置
const BACKEND_PORT = 8000
const BACKEND_DIR = path.join(__dirname, '..', '..', 'backend')

function startBackend() {
  const pythonCmd = process.platform === 'win32' ? 'python' : 'python3'

  backendProcess = spawn(pythonCmd, ['-m', 'uvicorn', 'backend.main:app',
    '--host', '127.0.0.1',
    '--port', String(BACKEND_PORT),
    '--no-access-log',
  ], {
    cwd: path.join(BACKEND_DIR, '..'),
    stdio: ['pipe', 'pipe', 'pipe'],
    env: { ...process.env },
  })

  backendProcess.stdout.on('data', (data) => {
    console.log(`[Backend] ${data.toString().trim()}`)
  })

  backendProcess.stderr.on('data', (data) => {
    console.log(`[Backend] ${data.toString().trim()}`)
  })

  backendProcess.on('error', (err) => {
    console.error('Backend start failed:', err.message)
  })

  backendProcess.on('close', (code) => {
    console.log(`Backend exited with code ${code}`)
    backendProcess = null
  })
}

function stopBackend() {
  if (backendProcess) {
    backendProcess.kill('SIGTERM')
    try {
      // Windows: kill process tree
      require('child_process').exec(`taskkill /F /T /PID ${backendProcess.pid} 2>nul`)
    } catch { }
    backendProcess = null
  }
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 900,
    minWidth: 960,
    minHeight: 640,
    title: '游戏包名爬虫系统 v2.0',
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
    },
    icon: path.join(__dirname, '..', 'public', 'icon.png'),
  })

  // 开发模式：加载 Vite dev server
  const isDev = process.env.NODE_ENV !== 'production'
  if (isDev) {
    mainWindow.loadURL('http://localhost:5173')
    mainWindow.webContents.openDevTools({ mode: 'detach' })
  } else {
    // 生产模式：加载打包后的静态文件
    mainWindow.loadFile(path.join(__dirname, '..', 'dist', 'index.html'))
  }

  mainWindow.on('closed', () => {
    mainWindow = null
  })
}

// 应用事件
app.whenReady().then(() => {
  startBackend()

  // 等待后端启动完成
  const http = require('http')
  let retries = 0
  const checkBackend = () => {
    http.get(`http://127.0.0.1:${BACKEND_PORT}/api/health`, (res) => {
      if (res.statusCode === 200) {
        console.log('Backend is ready')
        createWindow()
      } else if (retries < 30) {
        retries++
        setTimeout(checkBackend, 500)
      }
    }).on('error', () => {
      if (retries < 30) {
        retries++
        setTimeout(checkBackend, 500)
      }
    })
  }
  setTimeout(checkBackend, 1500)
})

app.on('window-all-closed', () => {
  stopBackend()
  if (process.platform !== 'darwin') {
    app.quit()
  }
})

app.on('activate', () => {
  if (!mainWindow) {
    createWindow()
  }
})

app.on('before-quit', () => {
  stopBackend()
})
