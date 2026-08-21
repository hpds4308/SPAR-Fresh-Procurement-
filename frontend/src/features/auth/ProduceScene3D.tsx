import { useEffect, useRef } from "react";
import * as THREE from "three";

// A small real-3D scene (WebGL via three.js) of tomatoes and fruit,
// gently rotating/bobbing and tilting toward the cursor. Replaces the
// flat SVG crate with genuine depth, lighting and shading.
export default function ProduceScene3D() {
  const mountRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;

    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(35, 1, 0.1, 100);
    camera.position.set(0, 0, 9);

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    mount.appendChild(renderer.domElement);
    renderer.domElement.style.width = "100%";
    renderer.domElement.style.height = "100%";
    renderer.domElement.style.display = "block";

    // Lighting: bright key light + soft ambient + a crisp specular rim,
    // tuned for a glossy, "just-washed produce" photographic look.
    scene.add(new THREE.AmbientLight(0xfff2df, 0.55));
    const key = new THREE.DirectionalLight(0xffffff, 1.6);
    key.position.set(4, 6, 6);
    scene.add(key);
    const rim = new THREE.PointLight(0xffe9c2, 0.9, 24);
    rim.position.set(-5, -2, 4);
    scene.add(rim);
    const specular = new THREE.PointLight(0xffffff, 0.8, 14);
    specular.position.set(2.2, 3, 5);
    scene.add(specular);

    const group = new THREE.Group();
    scene.add(group);

    const stemMat = new THREE.MeshStandardMaterial({ color: 0x2f6d4e, roughness: 0.6 });

    function makeTomato(x: number, y: number, z: number, scale: number): THREE.Group {
      const g = new THREE.Group();
      const body = new THREE.Mesh(
        new THREE.SphereGeometry(1, 32, 32),
        new THREE.MeshStandardMaterial({ color: 0xe4472b, roughness: 0.18, metalness: 0.06 })
      );
      body.scale.set(1, 0.9, 1);
      g.add(body);
      for (let i = 0; i < 5; i++) {
        const leaf = new THREE.Mesh(new THREE.ConeGeometry(0.12, 0.4, 6), stemMat);
        const angle = (i / 5) * Math.PI * 2;
        leaf.position.set(Math.cos(angle) * 0.18, 0.83, Math.sin(angle) * 0.18);
        leaf.rotation.x = Math.PI;
        leaf.rotation.z = Math.cos(angle) * 0.4;
        g.add(leaf);
      }
      g.position.set(x, y, z);
      g.scale.setScalar(scale);
      return g;
    }

    function makeRoundFruit(
      x: number,
      y: number,
      z: number,
      scale: number,
      color: number,
      squashY = 1
    ): THREE.Mesh {
      const body = new THREE.Mesh(
        new THREE.SphereGeometry(1, 32, 32),
        new THREE.MeshStandardMaterial({ color, roughness: 0.22, metalness: 0.03 })
      );
      body.position.set(x, y, z);
      body.scale.set(scale, scale * squashY, scale);
      return body;
    }

    const tomato1 = makeTomato(-0.15, 0.25, 0.3, 1.5);
    const tomato2 = makeTomato(1.55, -0.75, -1.1, 0.62);
    const tomato3 = makeTomato(-1.7, 1.05, -1.3, 0.42);
    const orange1 = makeRoundFruit(1.7, 0.95, -0.6, 0.66, 0xf3a712);
    const lime1 = makeRoundFruit(-1.55, -0.85, -0.4, 0.5, 0x8bc34a, 1.08);

    group.add(tomato1, tomato2, tomato3, orange1, lime1);

    const meshes: THREE.Object3D[] = [tomato1, tomato2, tomato3, orange1, lime1];
    const basePositions = meshes.map((m) => m.position.clone());

    let raf = 0;
    let targetRotX = 0;
    let targetRotY = 0;
    let curRotX = 0;
    let curRotY = 0;

    function onPointerMove(e: PointerEvent) {
      if (!mount) return;
      const rect = mount.getBoundingClientRect();
      const relX = (e.clientX - rect.left) / rect.width - 0.5;
      const relY = (e.clientY - rect.top) / rect.height - 0.5;
      targetRotY = relX * 0.6;
      targetRotX = relY * -0.4;
    }
    mount.addEventListener("pointermove", onPointerMove);

    const clock = new THREE.Clock();

    function animate() {
      const t = clock.getElapsedTime();
      if (!reducedMotion) {
        meshes.forEach((m, i) => {
          m.rotation.y = t * (0.3 + i * 0.05);
          m.position.y = basePositions[i].y + Math.sin(t * (0.8 + i * 0.15) + i) * 0.12;
        });
        curRotX += (targetRotX - curRotX) * 0.06;
        curRotY += (targetRotY - curRotY) * 0.06;
        group.rotation.x = curRotX;
        group.rotation.y = curRotY;
      }
      renderer.render(scene, camera);
      raf = requestAnimationFrame(animate);
    }
    animate();

    function resize() {
      if (!mount) return;
      const w = mount.clientWidth;
      const h = mount.clientHeight;
      if (w === 0 || h === 0) return;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h, false);
    }
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(mount);

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      mount.removeEventListener("pointermove", onPointerMove);
      scene.traverse((obj) => {
        if (obj instanceof THREE.Mesh) {
          obj.geometry.dispose();
          const mat = obj.material;
          if (Array.isArray(mat)) mat.forEach((m) => m.dispose());
          else mat.dispose();
        }
      });
      renderer.dispose();
      if (mount.contains(renderer.domElement)) {
        mount.removeChild(renderer.domElement);
      }
    };
  }, []);

  return <div ref={mountRef} className="w-full h-full" />;
}
