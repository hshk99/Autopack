const { app, BrowserWindow } = require('electron');
const path = require('path');
const { spawn } = require('child_process');

let mainWindow;
let backendProcess;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false,
    },
  });

  // Load React dev server in development
  const startUrl = process.env.ELECTRON_START_URL || 'http://localhost:3000';
  mainWindow.loadURL(startUrl);

  // Open DevTools in development
  if (process.env.NODE_ENV === 'development') {
    mainWindow.webContents.openDevTools();
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

function startBackend() {
  // Start Python backend subprocess
  const backendPath = path.join(__dirname, '../../backend');
  const pythonPath = process.platform === 'win32'
    ? path.join(backendPath, 'venv', 'Scripts', 'python.exe')
    : path.join(backendPath, 'venv', 'bin', 'python');

  backendProcess = spawn(pythonPath, ['main.py'], {
    cwd: backendPath,
    stdio: 'inherit',
  });

  backendProcess.on('error', (err) => {
    console.error('Failed to start backend:', err);
  });
}

function stopBackend() {
  if (backendProcess) {
    backendProcess.kill();
  }
}

app.on('ready', () => {
  startBackend();
  // Wait 2 seconds for backend to start
  setTimeout(createWindow, 2000);
});

app.on('window-all-closed', () => {
  stopBackend();
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('activate', () => {
  if (mainWindow === null) {
    createWindow();
  }
});

app.on('before-quit', () => {
  stopBackend();
});
