import React, { useEffect, useRef } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { SimClock } from '../sim/SimClock.js';
import { SimulationEngine } from '../sim/engine.js';
import {
	getPositionAtTime,
	eciToEcef,
	getOrbitPoints,
	latLonToEcef,
	gmstRad,
} from '../sim/keplerian.js';
import { sunDirectionFixed, isInSunlight } from '../utils/sun.js';
import {
	SAT_CONFIG,
	STATE_COLOR_HEX,
	SERVICE_COLOR,
	GROUND_STATIONS,
} from '../constants/index.js';

const R_EARTH = 6378137;
const S = 1 / R_EARTH; // 1 Three.js unit = R_EARTH metres
const EARTH_TEXTURES = {
	color: 'https://threejs.org/examples/textures/planets/earth_atmos_2048.jpg',
	normal: 'https://threejs.org/examples/textures/planets/earth_normal_2048.jpg',
	specular:
		'https://threejs.org/examples/textures/planets/earth_specular_2048.jpg',
	clouds: 'https://threejs.org/examples/textures/planets/earth_clouds_1024.png',
	lights:
		'https://cdn.apewebapps.com/threejs/156/examples/textures/planets/earth_lights_2048.png',
};

// ECEF/ECI metres → Three.js Vector3.  Earth's Z (north pole) → Three.js Y.
function toScene(p) {
	return new THREE.Vector3(p.x * S, p.z * S, -p.y * S);
}

// Visual-only altitude exaggeration. The simulation keeps true ECEF positions,
// but LEO satellites need a little breathing room to remain readable at Earth scale.
function toOrbitScene(p) {
	const v = toScene(p);
	const radius = v.length();
	if (radius <= 1.01) return v;
	const altitude = radius - 1;
	const visualAltitude = Math.max(altitude, 0.18 + altitude * 0.6);
	return v.normalize().multiplyScalar(1 + visualAltitude);
}

// Ground-segment reference position (null-island at surface)
const GROUND_ECEF = latLonToEcef(0, 0);

function bezierLerp(p0, ctrl, p2, t) {
	const inv = 1 - t;
	return {
		x: inv * inv * p0.x + 2 * inv * t * ctrl.x + t * t * p2.x,
		y: inv * inv * p0.y + 2 * inv * t * ctrl.y + t * t * p2.y,
		z: inv * inv * p0.z + 2 * inv * t * ctrl.z + t * t * p2.z,
	};
}

function buildCtrl(from, to) {
	const mx = (from.x + to.x) / 2,
		my = (from.y + to.y) / 2,
		mz = (from.z + to.z) / 2;
	const mLen = Math.sqrt(mx * mx + my * my + mz * mz) || 1;
	const dist = Math.sqrt(
		(to.x - from.x) ** 2 + (to.y - from.y) ** 2 + (to.z - from.z) ** 2,
	);
	const lift = Math.max(dist * 0.2, R_EARTH * 0.15);
	return {
		x: mx + (mx / mLen) * lift,
		y: my + (my / mLen) * lift,
		z: mz + (mz / mLen) * lift,
	};
}

function buildEarthGeometry() {
	return new THREE.SphereGeometry(1, 192, 128);
}

function loadPlanetTexture(loader, url, color = false) {
	const texture = loader.load(url);
	texture.anisotropy = 8;
	if (color) texture.colorSpace = THREE.SRGBColorSpace;
	return texture;
}

function createSatelliteModel(color) {
	const root = new THREE.Group();
	root.userData.satId = null;

	const bodyMat = new THREE.MeshStandardMaterial({
		color,
		metalness: 0.55,
		roughness: 0.38,
	});
	const panelMat = new THREE.MeshStandardMaterial({
		color: 0x1d5d96,
		emissive: 0x04172a,
		metalness: 0.2,
		roughness: 0.28,
	});
	const trimMat = new THREE.MeshBasicMaterial({ color: 0xd4eeff });

	const body = new THREE.Mesh(
		new THREE.BoxGeometry(0.04, 0.026, 0.026),
		bodyMat,
	);
	root.add(body);

	const leftPanel = new THREE.Mesh(
		new THREE.BoxGeometry(0.07, 0.0025, 0.032),
		panelMat,
	);
	const rightPanel = leftPanel.clone();
	leftPanel.position.x = -0.062;
	rightPanel.position.x = 0.062;
	root.add(leftPanel, rightPanel);

	const boom = new THREE.Mesh(
		new THREE.CylinderGeometry(0.002, 0.002, 0.075, 8),
		trimMat,
	);
	boom.rotation.z = Math.PI * 0.5;
	root.add(boom);

	const antenna = new THREE.Mesh(
		new THREE.ConeGeometry(0.011, 0.026, 16),
		trimMat,
	);
	antenna.position.z = 0.027;
	antenna.rotation.x = Math.PI * 0.5;
	root.add(antenna);

	const glow = new THREE.Mesh(
		new THREE.SphereGeometry(0.05, 16, 16),
		new THREE.MeshBasicMaterial({
			color,
			transparent: true,
			opacity: 0.16,
			depthWrite: false,
		}),
	);
	root.add(glow);
	root.userData.statusMaterials = [bodyMat];
	root.userData.glow = glow;
	return root;
}

// ── GlobeScene ───────────────────────────────────────────────────────────────
// All Three.js work lives here; ThreeGlobe is just the React wrapper.

class GlobeScene {
	constructor(canvas, onSelect) {
		this.canvas = canvas;
		this.onSelect = onSelect;
		this._selectedId = null;
		this._trackedId = null;
		this._trackingFocus = new THREE.Vector3();
		this._lastSun = null;
		this._rafId = null;

		this._setupRenderer();
		this._buildEarth();
		this._buildAtmosphere();
		this._buildStars();
		this._buildLighting();
		this._buildOrbits();
		this._buildSatellites();
		this._buildGroundStations();
		this._setupInteraction();

		this.simClock = new SimClock();
		this.engine = new SimulationEngine(this.simClock);

		this._stopTick = this.simClock.setInterval(2, () => this.engine.tick());
		this._stopMinute = this.simClock.setInterval(60, () =>
			this.engine.recordMinute(),
		);

		this._packetViz = new Map(); // pktId -> { line, glow, from, ctrl, to }
		this._fadingPkt = new Map(); // pktId → fadeEndSimSec

		this._render = this._render.bind(this);
		this._rafId = requestAnimationFrame(this._render);
		window.addEventListener('resize', (this._onResize = () => this._resize()));
	}

	// ── Builders ───────────────────────────────────────────────────────────────

	_setupRenderer() {
		const { canvas } = this;
		const w = canvas.clientWidth || window.innerWidth;
		const h = canvas.clientHeight || window.innerHeight;

		this.scene = new THREE.Scene();
		this.camera = new THREE.PerspectiveCamera(45, w / h, 0.005, 120);
		this.camera.position.set(0, 2.5, 14);

		this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
		this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
		this.renderer.setSize(w, h, false);
		this.renderer.setClearColor(0x00040c);
		this.renderer.outputColorSpace = THREE.SRGBColorSpace;

		this.controls = new OrbitControls(this.camera, this.renderer.domElement);
		this.controls.enableDamping = true;
		this.controls.dampingFactor = 0.06;
		this.controls.minDistance = 1.5;
		this.controls.maxDistance = 24;
		this.controls.rotateSpeed = 0.45;
		this.controls.enablePan = false;
		this.controls.zoomToCursor = false;
		this.controls.target.set(0, 0, 0);
		this.controls.addEventListener('start', () => {
			if (this._trackedId != null) {
				this.onSelect(null);
				this.setTracked(null);
			}
		});
	}

	_buildEarth() {
		const loader = new THREE.TextureLoader();
		loader.setCrossOrigin('anonymous');
		const earthMap = loadPlanetTexture(loader, EARTH_TEXTURES.color, true);
		const normalMap = loadPlanetTexture(loader, EARTH_TEXTURES.normal);
		const specularMap = loadPlanetTexture(loader, EARTH_TEXTURES.specular);

		this.earth = new THREE.Mesh(
			buildEarthGeometry(),
			new THREE.MeshPhongMaterial({
				map: earthMap,
				normalMap,
				normalScale: new THREE.Vector2(0.55, 0.55),
				specularMap,
				specular: new THREE.Color(0x2f6ea6),
				shininess: 22,
			}),
		);
		this.scene.add(this.earth);

		this.clouds = new THREE.Mesh(
			new THREE.SphereGeometry(1.017, 128, 80),
			new THREE.MeshPhongMaterial({
				map: loadPlanetTexture(loader, EARTH_TEXTURES.clouds, true),
				transparent: true,
				opacity: 0.34,
				depthWrite: false,
			}),
		);
		this.scene.add(this.clouds);

		this.nightLights = new THREE.Mesh(
			new THREE.SphereGeometry(1.006, 128, 80),
			new THREE.ShaderMaterial({
				uniforms: {
					lightsMap: {
						value: loadPlanetTexture(loader, EARTH_TEXTURES.lights, true),
					},
					sunDir: { value: new THREE.Vector3(1, 0, 0) },
				},
				vertexShader: `
          varying vec2 vUv;
          varying vec3 vWorldNormal;
          void main() {
            vUv = uv;
            vec4 worldPos = modelMatrix * vec4(position, 1.0);
            vWorldNormal = normalize(worldPos.xyz);
            gl_Position = projectionMatrix * viewMatrix * worldPos;
          }
        `,
				fragmentShader: `
          uniform sampler2D lightsMap;
          uniform vec3 sunDir;
          varying vec2 vUv;
          varying vec3 vWorldNormal;
          void main() {
            float facingSun = dot(normalize(vWorldNormal), normalize(sunDir));
            float night = 1.0 - smoothstep(-0.18, 0.10, facingSun);
            vec3 lights = texture2D(lightsMap, vUv).rgb;
            float alpha = night * smoothstep(0.04, 0.55, max(max(lights.r, lights.g), lights.b));
            gl_FragColor = vec4(lights * 1.45, alpha * 0.82);
          }
        `,
				transparent: true,
				blending: THREE.AdditiveBlending,
				depthWrite: false,
			}),
		);
		this.scene.add(this.nightLights);

		// Lat/lon grid
		const gridMat = new THREE.LineBasicMaterial({
			color: 0x4a9eff,
			transparent: true,
			opacity: 0.13,
		});
		for (let lat = -80; lat <= 80; lat += 20) {
			const pts = [];
			for (let lon = 0; lon <= 361; lon += 3)
				pts.push(toScene(latLonToEcef(lat, lon)));
			this.scene.add(
				new THREE.Line(
					new THREE.BufferGeometry().setFromPoints(pts),
					gridMat.clone(),
				),
			);
		}
		for (let lon = 0; lon < 360; lon += 30) {
			const pts = [];
			for (let lat = -90; lat <= 90; lat += 3)
				pts.push(toScene(latLonToEcef(lat, lon)));
			this.scene.add(
				new THREE.Line(
					new THREE.BufferGeometry().setFromPoints(pts),
					gridMat.clone(),
				),
			);
		}
	}

	_buildAtmosphere() {
		this.scene.add(
			new THREE.Mesh(
				new THREE.SphereGeometry(1.055, 36, 36),
				new THREE.MeshPhongMaterial({
					color: 0x0055bb,
					transparent: true,
					opacity: 0.07,
					side: THREE.BackSide,
				}),
			),
		);
	}

	_buildStars() {
		const n = 2800,
			pos = new Float32Array(n * 3);
		for (let i = 0; i < n; i++) {
			const phi = Math.acos(2 * Math.random() - 1);
			const theta = Math.random() * Math.PI * 2;
			const r = 50 + Math.random() * 10;
			pos[i * 3] = r * Math.sin(phi) * Math.cos(theta);
			pos[i * 3 + 1] = r * Math.cos(phi);
			pos[i * 3 + 2] = r * Math.sin(phi) * Math.sin(theta);
		}
		const geo = new THREE.BufferGeometry();
		geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
		this.scene.add(
			new THREE.Points(
				geo,
				new THREE.PointsMaterial({ color: 0x88bbff, size: 0.045 }),
			),
		);
	}

	_buildLighting() {
		this.sunLight = new THREE.DirectionalLight(0xffe8cc, 2.2);
		this.sunLight.position.set(10, 5, 6);
		this.scene.add(this.sunLight);
		this.scene.add(new THREE.AmbientLight(0x183654, 0.95));
	}

	_buildOrbits() {
		// Orbit ellipses are in ECI. orbitGroup is rotated by -GMST each frame
		// to convert ECI → ECEF in Three.js space.
		this.orbitGroup = new THREE.Group();
		this.scene.add(this.orbitGroup);
		this._orbitMats = new Map();

		SAT_CONFIG.forEach((cfg) => {
			const el = {
				a: cfg.a_km,
				e: cfg.e,
				i: (cfg.i_deg * Math.PI) / 180,
				raan: (cfg.raan_deg * Math.PI) / 180,
				argP: (cfg.argP_deg * Math.PI) / 180,
				M0: 0,
				epochSec: 0,
			};
			const pts = getOrbitPoints(el, 180).map(toOrbitScene);
			const mat = new THREE.LineBasicMaterial({
				color: 0x0d2a4a,
				transparent: true,
				opacity: 0.28,
			});
			this.orbitGroup.add(
				new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), mat),
			);
			this._orbitMats.set(cfg.id, mat);
		});
	}

	_buildSatellites() {
		this.satMeshes = []; // [{ mesh, glow, satId }]
		SAT_CONFIG.forEach((cfg) => {
			const mesh = createSatelliteModel(STATE_COLOR_HEX.IDLE);
			mesh.userData.satId = cfg.id;
			const glow = mesh.userData.glow;
			this.scene.add(mesh);
			this.satMeshes.push({ mesh, glow, satId: cfg.id });
		});
	}

	_buildGroundStations() {
		GROUND_STATIONS.forEach((gs) => {
			const m = new THREE.Mesh(
				new THREE.SphereGeometry(0.009, 6, 6),
				new THREE.MeshBasicMaterial({ color: 0x00ff88 }),
			);
			m.position.copy(toScene(latLonToEcef(gs.lat_deg, gs.lon_deg)));
			this.scene.add(m);
		});
	}

	_setupInteraction() {
		this.raycaster = new THREE.Raycaster();
		this._mouse = new THREE.Vector2();
		this._mdPos = null;

		this.canvas.addEventListener('mousedown', (e) => {
			this._mdPos = { x: e.clientX, y: e.clientY };
		});
		this.canvas.addEventListener(
			'click',
			(this._onClick = (e) => {
				if (!this._mdPos) return;
				if (
					Math.hypot(e.clientX - this._mdPos.x, e.clientY - this._mdPos.y) > 5
				)
					return;
				const rect = this.canvas.getBoundingClientRect();
				this._mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
				this._mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
				this.raycaster.setFromCamera(this._mouse, this.camera);
				const hits = this.raycaster.intersectObjects(
					this.satMeshes.map((s) => s.mesh),
					true,
				);
				const picked = hits[0]?.object;
				let cursor = picked;
				while (cursor && cursor.userData.satId == null) cursor = cursor.parent;
				this.onSelect(cursor?.userData.satId ?? null);
			}),
		);
	}

	// ── External API ──────────────────────────────────────────────────────────

	setSelected(id) {
		this._selectedId = id;
	}

	setTracked(id) {
		if (id !== this._trackedId) this._trackingFocus.copy(this.controls.target);
		this._trackedId = id;
		this.controls.minDistance = id == null ? 1.5 : 0.16;
		this.controls.maxDistance = id == null ? 24 : 4.5;
		this.controls.enablePan = false;
		if (id == null) this.controls.target.set(0, 0, 0);
	}

	// ── Render Loop ───────────────────────────────────────────────────────────

	_render(wallMs) {
		this._rafId = requestAnimationFrame(this._render);
		const prevSim = this.simClock.currentTime;
		this.simClock.advance(wallMs);
		const sim = this.simClock.currentTime;
		const simDt = Math.max(0, Math.min(3600, sim - prevSim));

		this._updateSunLight(sim);
		this._updateEarthCycle(sim, simDt);
		this._updateSatellites(sim);
		this._updateOrbitGroup(sim);
		this._updatePackets(sim);
		this._updateTracking();
		this._keepEarthCentered();
		this.controls.update();
		this.renderer.render(this.scene, this.camera);
	}

	_updateSunLight(sim) {
		this._lastSun = sunDirectionFixed(sim);
		const { x, y, z } = this._lastSun;
		// ECEF sun dir → Three.js (same coord transform as toScene but just direction)
		const sceneSun = new THREE.Vector3(x, z, -y).normalize();
		this.sunLight.position.copy(sceneSun).multiplyScalar(20);
		if (this.nightLights)
			this.nightLights.material.uniforms.sunDir.value.copy(sceneSun);
	}

	_updateEarthCycle(sim, simDt) {
		const cloudSpeed = (Math.PI * 2) / (18 * 3600);
		if (this.clouds) this.clouds.rotation.y += simDt * cloudSpeed;
	}

	_updateSatellites(sim) {
		this.engine.sats.forEach((sat, i) => {
			const eci = getPositionAtTime(sat.elements, sim);
			const ecef = eciToEcef(eci, sim);
			sat.currentPos = ecef;

			const { mesh, glow } = this.satMeshes[i];
			mesh.position.copy(toOrbitScene(ecef));
			mesh.lookAt(0, 0, 0);

			const col = STATE_COLOR_HEX[sat.state] || STATE_COLOR_HEX.IDLE;
			mesh.userData.statusMaterials.forEach((mat) => mat.color.setHex(col));
			glow.material.color.setHex(col);

			const sel = sat.id === this._selectedId;
			glow.material.opacity = sel ? 0.38 : 0.13;
			mesh.scale.setScalar(sel ? 1.7 : 1.0);

			if (this._lastSun) sat.inSunlight = isInSunlight(ecef, this._lastSun);
		});
	}

	_updateOrbitGroup(sim) {
		// ECI → ECEF: rotate group by -GMST around Three.js Y (= Earth's Z axis)
		this.orbitGroup.rotation.y = -gmstRad(sim);

		SAT_CONFIG.forEach((cfg) => {
			const mat = this._orbitMats.get(cfg.id);
			if (!mat) return;
			const sel = cfg.id === this._selectedId;
			mat.color.setHex(sel ? 0x00b9ff : 0x0d2a4a);
			mat.opacity = sel ? 0.8 : 0.28;
		});
	}

	_updatePackets(sim) {
		const proto = this.engine.protocol;

		// Spawn new vizzes
		for (const pkt of proto.packets) {
			if (this._packetViz.has(pkt.id) || pkt.startSimTime == null) continue;
			const from = pkt.from?.currentPos || GROUND_ECEF;
			const to = pkt.to?.currentPos || GROUND_ECEF;
			if (!from || !to) continue;
			this._spawnDot(pkt, from, to);
		}

		// Update + detect arrivals
		const stale = [];
		for (const [id, viz] of this._packetViz.entries()) {
			const pkt = proto.packets.find((p) => p.id === id);
			if (!pkt) {
				stale.push(id);
				continue;
			}

			const elapsed = sim - pkt.startSimTime;
			if (elapsed >= pkt.duration_s && !this._fadingPkt.has(id)) {
				proto.onPacketArrive(pkt);
				this._fadingPkt.set(id, sim + 0.4);
			}

			const t = Math.min(1, Math.max(0, elapsed / pkt.duration_s));
			this._updateTrail(viz, t);

			if (this._fadingPkt.has(id)) {
				const fe = this._fadingPkt.get(id);
				const opacity = Math.max(0, 1 - (sim - (fe - 0.4)) / 0.4);
				viz.line.material.opacity = opacity * 0.86;
				viz.glow.material.opacity = opacity * 0.24;
			}
		}

		// Remove faded
		for (const [id, fe] of this._fadingPkt.entries()) {
			if (sim >= fe) {
				this._removeDot(id);
				this._fadingPkt.delete(id);
				proto.packets = proto.packets.filter((p) => p.id !== id);
			}
		}
		stale.forEach((id) => this._removeDot(id));
	}

	_spawnDot(pkt, from, to) {
		const color = new THREE.Color(SERVICE_COLOR[pkt.service] || '#ffffff');
		const segments = 48;
		const geo = new THREE.BufferGeometry();
		geo.setAttribute(
			'position',
			new THREE.BufferAttribute(new Float32Array((segments + 1) * 3), 3),
		);
		geo.setDrawRange(0, 2);

		const glowGeo = geo.clone();
		const line = new THREE.Line(
			geo,
			new THREE.LineBasicMaterial({
				color,
				transparent: true,
				opacity: 0.86,
				blending: THREE.AdditiveBlending,
				depthWrite: false,
			}),
		);
		const glow = new THREE.Line(
			glowGeo,
			new THREE.LineBasicMaterial({
				color,
				transparent: true,
				opacity: 0.24,
				blending: THREE.AdditiveBlending,
				depthWrite: false,
			}),
		);
		this.scene.add(glow, line);
		const viz = { line, glow, from, ctrl: buildCtrl(from, to), to, segments };
		this._updateTrail(viz, 0.02);
		this._packetViz.set(pkt.id, viz);
	}

	_updateTrail(viz, t) {
		const head = Math.max(0.02, t);
		const tail = Math.max(0, head - 0.36);
		const count = Math.max(2, Math.ceil((head - tail) * viz.segments) + 1);
		[viz.line, viz.glow].forEach((line) => {
			const pos = line.geometry.attributes.position;
			for (let i = 0; i < count; i++) {
				const local = count === 1 ? 1 : i / (count - 1);
				const p = toOrbitScene(
					bezierLerp(viz.from, viz.ctrl, viz.to, tail + (head - tail) * local),
				);
				pos.setXYZ(i, p.x, p.y, p.z);
			}
			pos.needsUpdate = true;
			line.geometry.setDrawRange(0, count);
		});
	}

	_removeDot(id) {
		const viz = this._packetViz.get(id);
		if (viz) {
			this.scene.remove(viz.line, viz.glow);
			viz.line.geometry.dispose();
			viz.line.material.dispose();
			viz.glow.geometry.dispose();
			viz.glow.material.dispose();
		}
		this._packetViz.delete(id);
	}

	_updateTracking() {
		if (this._trackedId == null) return;
		const sat = this.engine.sats.find((s) => s.id === this._trackedId);
		if (!sat || !sat.currentPos) return;
		const satPos = toOrbitScene(sat.currentPos);
		const radial = satPos.clone().normalize();
		const altitude = Math.max(0, satPos.length() - 1);
		const trackDistance = THREE.MathUtils.clamp(
			0.45 + altitude * 0.08,
			0.48,
			0.82,
		);
		const desiredTarget = satPos
			.clone()
			.add(radial.clone().multiplyScalar(-0.045));
		const desiredCamera = satPos
			.clone()
			.add(radial.clone().multiplyScalar(trackDistance));

		this._trackingFocus.lerp(desiredTarget, 0.12);
		this.controls.target.copy(this._trackingFocus);
		this.camera.position.lerp(desiredCamera, 0.08);
	}

	_keepEarthCentered() {
		if (this._trackedId != null) return;
		this.controls.target.lerp(new THREE.Vector3(0, 0, 0), 0.35);
	}

	_resize() {
		const w = this.canvas.clientWidth || window.innerWidth;
		const h = this.canvas.clientHeight || window.innerHeight;
		this.camera.aspect = w / h;
		this.camera.updateProjectionMatrix();
		this.renderer.setSize(w, h, false);
	}

	destroy() {
		if (this._rafId != null) cancelAnimationFrame(this._rafId);
		window.removeEventListener('resize', this._onResize);
		this.canvas.removeEventListener('click', this._onClick);
		this._stopTick();
		this._stopMinute();
		this.simClock.destroy();
		this.controls.dispose();
		this.renderer.dispose();
	}
}

// ── React wrapper ─────────────────────────────────────────────────────────────

export function ThreeGlobe({ onReady, onSelect, getSelectedId }) {
	const canvasRef = useRef(null);

	useEffect(() => {
		const globe = new GlobeScene(canvasRef.current, onSelect);
		onReady({ simClock: globe.simClock, engine: globe.engine, globe });

		// Sync external selection changes (event log, HUD clicks) → orbit highlight
		const syncId = setInterval(() => {
			const want = getSelectedId();
			if (want !== globe._selectedId) globe.setSelected(want);
		}, 80);

		return () => {
			clearInterval(syncId);
			globe.destroy();
		};
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, []);

	return (
		<canvas
			ref={canvasRef}
			style={{
				position: 'fixed',
				inset: 0,
				width: '100%',
				height: '100%',
				display: 'block',
			}}
		/>
	);
}
