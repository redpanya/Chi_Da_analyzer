'use strict';
const { contextBridge, ipcRenderer } = require('electron');

if (process.isMainFrame) {
  const bridge = {};
  for (const name of ['state', 'check', 'download', 'cancel', 'apply', 'reveal', 'notices']) {
    bridge[name] = () => ipcRenderer.invoke('chida:' + name);
  }
  contextBridge.exposeInMainWorld('chidaDesktop', bridge);
}
