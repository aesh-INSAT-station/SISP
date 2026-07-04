'use strict';

const fs = require('fs');
const path = require('path');

function loadEnvFile(filePath, target = process.env) {
	if (!fs.existsSync(filePath)) return 0;

	let loaded = 0;
	const lines = fs.readFileSync(filePath, 'utf8').split(/\r?\n/);
	for (const line of lines) {
		const trimmed = line.trim();
		if (!trimmed || trimmed.startsWith('#')) continue;

		const eq = trimmed.indexOf('=');
		if (eq <= 0) continue;

		const key = trimmed.slice(0, eq).trim();
		const value = trimmed
			.slice(eq + 1)
			.trim()
			.replace(/^['"]|['"]$/g, '');

		if (!target[key]) {
			target[key] = value;
			loaded++;
		}
	}

	return loaded;
}

function loadBridgeEnv({ rootDir, serverDir } = {}) {
	const resolvedRoot = rootDir || path.resolve(__dirname, '..', '..');
	const resolvedServer = serverDir || path.resolve(__dirname, '..');

	return {
		rootLoaded: loadEnvFile(path.join(resolvedRoot, '.env')),
		serverLoaded: loadEnvFile(path.join(resolvedServer, '.env')),
	};
}

function parsePort(value, fallback = 3001) {
	const port = Number(value);
	if (Number.isInteger(port) && port > 0 && port <= 65535) return port;
	return fallback;
}

module.exports = {
	loadEnvFile,
	loadBridgeEnv,
	parsePort,
};
