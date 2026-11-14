import React, { useEffect, useRef, useState } from "react";
import { indicators } from "./health-indicators";

// Positions in model space after the upstream viewer's -PI/2 Y rotation.
const markers = [
  { id: "heart_rate", point: [0.035, 0.25, 0.063] },
  { id: "respiratory_rate", point: [-0.04, 0.25, 0.063] },
  { id: "body_temperature", point: [0.09, 0.21, -0.015] },
  { id: "blood_pressure", point: [0.148, 0.015, 0.032] },
];

export default function HumanBodyMap({ selected, onSelect }) {
  const hostRef = useRef(null);
  const markerRefs = useRef({});
  const controlsRef = useRef(null);
  const renderRef = useRef(null);
  const [status, setStatus] = useState("loading");
  useEffect(() => {
    const host = hostRef.current;
    let disposed = false, renderer, controls, observer, scene, camera;
    const materials = [];
    const notify = () => host.dispatchEvent(new Event("body-map-change", { bubbles: true }));
    const fail = () => { if (!disposed) setStatus("error"); };
    async function setup() {
      try {
        const [THREE, { GLTFLoader }, { OrbitControls }] = await Promise.all([
          import("three"), import("three/addons/loaders/GLTFLoader.js"), import("three/addons/controls/OrbitControls.js"),
        ]);
        if (disposed) return;
        scene = new THREE.Scene();
        camera = new THREE.OrthographicCamera(-0.36, 0.36, 0.57, -0.57, 0.01, 10);
        camera.position.set(0, 0, 2);
        renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
        renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
        renderer.domElement.setAttribute("aria-hidden", "true");
        host.prepend(renderer.domElement);
        renderer.domElement.addEventListener("webglcontextlost", fail);
        scene.add(new THREE.HemisphereLight(0xffffff, 0x7a8ba5, 2));
        const light = new THREE.DirectionalLight(0xffffff, 2.5);
        light.position.set(2, 3, 4);
        scene.add(light);
        controls = new OrbitControls(camera, renderer.domElement);
        controls.enablePan = false;
        controls.enableZoom = false;
        controls.minPolarAngle = controls.maxPolarAngle = Math.PI / 2;
        controlsRef.current = { reset: () => controls.reset(), rotate: (angle) => {
          const radius = camera.position.length();
          const theta = Math.atan2(camera.position.x, camera.position.z) + angle;
          camera.position.set(Math.sin(theta) * radius, 0, Math.cos(theta) * radius);
          controls.update();
        } };
        const render = () => {
          if (disposed) return;
          renderer.render(scene, camera);
          for (const marker of markers) {
            const position = new THREE.Vector3(...marker.point).project(camera);
            const element = markerRefs.current[marker.id];
            if (element) {
              element.style.left = `${(position.x + 1) * 50}%`;
              element.style.top = `${(1 - position.y) * 50}%`;
            }
          }
          notify();
        };
        renderRef.current = render;
        controls.addEventListener("change", render);
        observer = new ResizeObserver(() => {
          const width = host.clientWidth, height = host.clientHeight;
          if (!width || !height) return;
          const halfWidth = 0.57 * width / height;
          camera.left = -halfWidth; camera.right = halfWidth;
          camera.updateProjectionMatrix();
          renderer.setSize(width, height);
          render();
        });
        observer.observe(host);
        const gltf = await new GLTFLoader().loadAsync(`${import.meta.env.BASE_URL}geometries/human_body.glb`);
        if (disposed) {
          gltf.scene.traverse((child) => { child.geometry?.dispose(); const m = child.material; (Array.isArray(m) ? m : m ? [m] : []).forEach((item) => { item.map?.dispose(); item.dispose(); }); });
          return;
        }
        gltf.scene.rotation.y = -Math.PI / 2;
        gltf.scene.traverse((child) => {
          if (!child.isMesh) return;
          const old = Array.isArray(child.material) ? child.material : [child.material];
          old.forEach((material) => { material.map?.dispose(); material.dispose(); });
          child.material = new THREE.MeshStandardMaterial({ color: "#e8e0d5", roughness: 0.4, metalness: 0.05 });
          materials.push(child.material);
        });
        scene.add(gltf.scene);
        setStatus("ready");
        render();
      } catch (error) { fail(); }
    }
    setup();
    return () => {
      disposed = true;
      observer?.disconnect(); controls?.dispose(); controlsRef.current = null; renderRef.current = null;
      scene?.traverse((child) => child.geometry?.dispose());
      materials.forEach((material) => material.dispose());
      if (renderer) {
        renderer.domElement.removeEventListener("webglcontextlost", fail);
        renderer.dispose(); renderer.domElement.remove();
      }
    };
  }, []);

  useEffect(() => { if (status === "ready") renderRef.current?.(); }, [status]);

  return (
    <div className="body-map body-map-3d" role="group" aria-label="Body map of health indicators">
      <div ref={hostRef} className="body-3d-stage">
        {status !== "ready" && <p className="body-3d-status" role="status">{status === "loading" ? "Loading human body…" : "Unable to display the 3D model. Select the indicators using the cards."}</p>}
        {status === "ready" && markers.map(({ id }) => {
          const indicator = indicators.find((item) => item.id === id);
          return <button key={id} ref={(element) => { markerRefs.current[id] = element; }} type="button" data-indicator={id}
            className={`body-hotspot body-3d-hotspot ${selected === id ? "selected" : ""}`}
            aria-label={`${indicator.name}, ${indicator.region}`} aria-pressed={selected === id}
            title={`${indicator.name} · ${indicator.region}`} onClick={() => onSelect(id)} />;
        })}
      </div>
      <div className="body-3d-controls" aria-label="Human body controls">
        <button type="button" disabled={status !== "ready"} aria-label="Rotate body left" onClick={() => controlsRef.current?.rotate(-Math.PI / 8)}>↶</button>
        <button type="button" disabled={status !== "ready"} onClick={() => controlsRef.current?.reset()}>Front view</button>
        <button type="button" disabled={status !== "ready"} aria-label="Rotate body right" onClick={() => controlsRef.current?.rotate(Math.PI / 8)}>↷</button>
      </div>
      <small>Drag to rotate the body.</small>
    </div>
  );
}
