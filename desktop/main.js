// 墨尺 · Electron 主进程
// ─────────────────────────────────────────────────────────────
// 职责只有三件：spawn 评分核心（sidecar）、挑一个空闲端口、开窗口加载
// http://127.0.0.1:PORT/。评分逻辑全部在 Python 侧（qc_core.py），壳不参与
// 任何计算——口径唯一，与浏览器方案完全一致。
//
// 安全模型：加载的是本机回环地址，无远程内容；webPreferences 保持 Electron
// 默认（contextIsolation: true / nodeIntegration: false / sandbox: true）。
const { app, BrowserWindow, shell } = require('electron');
const { spawn } = require('child_process');
const net = require('net');
const http = require('http');
const path = require('path');

const isDev = !app.isPackaged;
let sidecar = null;
let win = null;

// 随机空闲端口：多实例 / 端口冲突都不可能发生
function freePort() {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.listen(0, '127.0.0.1', () => {
      const port = srv.address().port;
      srv.close(() => resolve(port));
    });
    srv.on('error', reject);
  });
}

// 轮询等 sidecar 就绪（PyInstaller onefile 首次解包可能要几秒）
function waitForServer(port, tries = 80) {
  return new Promise((resolve, reject) => {
    const ping = n => {
      if (n <= 0) return reject(new Error('评分核心启动超时'));
      const req = http.get({ host: '127.0.0.1', port, path: '/', timeout: 1000 },
        res => { res.resume(); resolve(); });
      req.on('error', () => setTimeout(() => ping(n - 1), 250));
      req.on('timeout', () => { req.destroy(); setTimeout(() => ping(n - 1), 250); });
    };
    ping(tries);
  });
}

function sidecarPath() {
  const exe = process.platform === 'win32' ? 'mochi-server.exe' : 'mochi-server';
  return path.join(process.resourcesPath, 'sidecar', exe);
}

// Windows 上 PyInstaller onefile 是引导器 + 子进程，taskkill /T 才杀得干净
function killSidecar() {
  if (!sidecar) return;
  if (process.platform === 'win32') {
    spawn('taskkill', ['/pid', String(sidecar.pid), '/T', '/F'], { stdio: 'ignore' });
  } else {
    sidecar.kill();
  }
  sidecar = null;
}

async function createWindow() {
  const port = await freePort();
  if (isDev) {
    // 开发模式：直接用仓库根的 server.py（需要本机 python3）
    sidecar = spawn('python3', [path.join(__dirname, '..', 'server.py'), String(port)],
      { stdio: 'inherit' });
  } else {
    sidecar = spawn(sidecarPath(), [String(port)], { stdio: 'ignore' });
  }
  await waitForServer(port);

  win = new BrowserWindow({
    width: 1320,
    height: 900,
    minWidth: 980,
    minHeight: 640,
    title: '墨尺 · 网文质检',
    backgroundColor: '#f3efe4',
    show: false,
  });
  win.once('ready-to-show', () => win.show());
  win.loadURL(`http://127.0.0.1:${port}/`);
  // 壳内只允许本地服务；外部链接交给系统浏览器
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (!url.startsWith(`http://127.0.0.1:${port}`)) {
      shell.openExternal(url);
      return { action: 'deny' };
    }
    return { action: 'allow' };
  });
  win.on('closed', () => { win = null; });
}

// 单实例：重复启动把已有窗口调到前台
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (win) {
      if (win.isMinimized()) win.restore();
      win.focus();
    }
  });
  app.whenReady().then(createWindow);
  app.on('window-all-closed', () => {
    killSidecar();
    app.quit();
  });
  app.on('before-quit', killSidecar);
}
