// ws.js — WebSocket 连接/重连/消息分发
export function connectWS({ url, onOpen, onMessage, onClose, reconnectMs = 2000 } = {}) {
  let ws;
  let closed = false;

  function connect() {
    if (closed) return;
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    ws = new WebSocket(`${proto}://${location.host}${url}`);

    ws.onopen = () => { if (onOpen) onOpen(ws); };

    ws.onmessage = (e) => {
      const msg = JSON.parse(e.data);
      if (onMessage) onMessage(msg, ws);
    };

    ws.onclose = () => {
      if (!closed && reconnectMs > 0) setTimeout(connect, reconnectMs);
      if (onClose) onClose();
    };
  }

  connect();

  return {
    send(data) {
      if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(data));
    },
    close() {
      closed = true;
      if (ws) ws.close();
    },
    getSocket() { return ws; },
  };
}
