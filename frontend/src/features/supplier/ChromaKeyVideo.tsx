import { useEffect, useRef } from "react";

// The source clip has a solid black backdrop (sampled ~(0,0,0) at every
// corner across its full duration). Below KEY_LOW a pixel is treated as
// pure background; between KEY_LOW and KEY_HIGH alpha fades linearly so
// the cutout edge doesn't look jagged. Hair/shadow pixels in the source
// sat at ~5-35, so this range removes the backdrop without eating hair.
const KEY_LOW = 10;
const KEY_HIGH = 40;

export default function ChromaKeyVideo({
  src,
  className,
  fit = "cover",
}: {
  src: string;
  className?: string;
  fit?: "cover" | "contain";
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas) return;
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    if (!ctx) return;

    let rafId = 0;
    let cancelled = false;

    function resize() {
      const rect = canvas!.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas!.width = Math.max(1, Math.round(rect.width * dpr));
      canvas!.height = Math.max(1, Math.round(rect.height * dpr));
    }

    function draw() {
      if (cancelled) return;
      if (video!.readyState >= 2 && video!.videoWidth) {
        const cw = canvas!.width;
        const ch = canvas!.height;
        const vw = video!.videoWidth;
        const vh = video!.videoHeight;
        // "cover" fills the canvas (cropping overflow); "contain" fits the
        // whole frame inside it (letterboxed) — needed once there's no
        // opaque backdrop to crop against, so cropping would clip the subject.
        const scale = fit === "cover" ? Math.max(cw / vw, ch / vh) : Math.min(cw / vw, ch / vh);
        const dw = vw * scale;
        const dh = vh * scale;
        const dx = (cw - dw) / 2;
        const dy = (ch - dh) / 2;
        ctx!.drawImage(video!, dx, dy, dw, dh);

        const frame = ctx!.getImageData(0, 0, cw, ch);
        const d = frame.data;
        for (let i = 0; i < d.length; i += 4) {
          const luma = Math.max(d[i], d[i + 1], d[i + 2]);
          if (luma <= KEY_LOW) {
            d[i + 3] = 0;
          } else if (luma < KEY_HIGH) {
            d[i + 3] = Math.round(((luma - KEY_LOW) / (KEY_HIGH - KEY_LOW)) * 255);
          }
        }
        ctx!.putImageData(frame, 0, 0);
      }
      rafId = requestAnimationFrame(draw);
    }

    resize();
    window.addEventListener("resize", resize);
    video.play().catch(() => {});
    rafId = requestAnimationFrame(draw);

    return () => {
      cancelled = true;
      cancelAnimationFrame(rafId);
      window.removeEventListener("resize", resize);
    };
  }, [src, fit]);

  return (
    <div className={className} style={{ position: "relative" }}>
      <video
        ref={videoRef}
        src={src}
        muted
        loop
        autoPlay
        playsInline
        aria-hidden
        // Some browsers deprioritize/pause decoding for video that's
        // zero-sized or parked off-screen (readyState stays 4 but the
        // element never actually starts playing). Keeping it on-screen at
        // full size, hidden only via opacity, avoids that — the canvas
        // drawn on top is the only thing actually visible.
        style={{ position: "absolute", inset: 0, width: "100%", height: "100%", opacity: 0, pointerEvents: "none" }}
      />
      <canvas ref={canvasRef} style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }} />
    </div>
  );
}
