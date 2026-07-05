'use strict';

const http = require('http');
const { WebSocket, WebSocketServer } = require('ws');

function formatListenUrl(address, configuredPort) {
	if (!address || typeof address === 'string') {
		return `ws://localhost:${configuredPort}`;
	}

	const host =
		address.address === '::' || address.address === '0.0.0.0'
			? 'localhost'
			: address.address;
	return `ws://${host}:${address.port}`;
}

function createWebSocketHub({
	port,
	host,
	logger = console,
	healthPath = '/health',
} = {}) {
	const clients = new Set();
	const connectionHandlers = new Set();
	let listening = false;

	const server = http.createServer((req, res) => {
		if (req.url === healthPath) {
			const body = JSON.stringify({
				ok: true,
				clients: clients.size,
				ts: Date.now(),
			});
			res.writeHead(200, {
				'content-type': 'application/json',
				'content-length': Buffer.byteLength(body),
			});
			res.end(body);
			return;
		}

		res.writeHead(404, { 'content-type': 'text/plain' });
		res.end('SISP bridge WebSocket server\n');
	});

	const wss = new WebSocketServer({ noServer: true });

	function dropClient(ws, reason) {
		clients.delete(ws);
		if (reason) logger.warn?.(`[SISP] Dropped client: ${reason}`);
		try {
			if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CLOSING) {
				ws.close();
			}
		} catch (_) {
			// Client is already gone.
		}
	}

	function sendJson(ws, msg) {
		if (!ws || ws.readyState !== WebSocket.OPEN) return false;

		let json;
		try {
			json = JSON.stringify(msg);
		} catch (e) {
			logger.warn?.(`[SISP] Failed to serialize message: ${e.message}`);
			return false;
		}

		try {
			ws.send(json, (err) => {
				if (err) dropClient(ws, err.message);
			});
			return true;
		} catch (e) {
			dropClient(ws, e.message);
			return false;
		}
	}

	function broadcast(msg) {
		for (const ws of Array.from(clients)) {
			sendJson(ws, msg);
		}
	}

	server.on('upgrade', (req, socket, head) => {
		wss.handleUpgrade(req, socket, head, (ws) => {
			wss.emit('connection', ws, req);
		});
	});

	wss.on('connection', (ws, req) => {
		clients.add(ws);
		ws.on('close', () => clients.delete(ws));
		ws.on('error', (e) => dropClient(ws, e?.message || 'socket error'));

		for (const handler of connectionHandlers) {
			try {
				handler(ws, req);
			} catch (e) {
				logger.error?.('[SISP] Connection handler failed:', e);
				dropClient(ws, e?.message || 'connection handler failed');
			}
		}
	});

	function listen() {
		return new Promise((resolve, reject) => {
			let settled = false;
			const onError = (e) => {
				if (!settled) {
					settled = true;
					reject(e);
					return;
				}
				logger.error?.('[SISP] WebSocket server error:', e);
			};

			server.once('error', onError);
			const onListening = () => {
				settled = true;
				listening = true;
				server.off('error', onError);
				server.on('error', onError);
				resolve({
					address: server.address(),
					url: formatListenUrl(server.address(), port),
				});
			};

			if (host) server.listen(port, host, onListening);
			else server.listen(port, onListening);
		});
	}

	function close() {
		for (const ws of Array.from(clients)) dropClient(ws);
		wss.close();
		if (listening) server.close();
		listening = false;
	}

	return {
		broadcast,
		close,
		listen,
		onConnection(handler) {
			connectionHandlers.add(handler);
			return () => connectionHandlers.delete(handler);
		},
		sendJson,
		clientCount() {
			return clients.size;
		},
	};
}

module.exports = {
	createWebSocketHub,
};
