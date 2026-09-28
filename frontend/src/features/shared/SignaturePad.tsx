import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";

export type SignaturePadHandle = {
  /** PNG data URL of the signature at display size, or null if nothing has been drawn. */
  toDataURL: () => string | null;
  clear: () => void;
};

/**
 * Draw-with-finger/mouse signature box. Pointer events cover mouse, touch
 * and pen alike; touch-action: none stops the page scrolling while signing
 * on a phone.
 */
const SignaturePad = forwardRef<SignaturePadHandle, { onChange?: (hasInk: boolean) => void; height?: number }>(
  function SignaturePad({ onChange, height = 160 }, ref) {
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const drawing = useRef(false);
    const last = useRef<{ x: number; y: number } | null>(null);
    const [hasInk, setHasInk] = useState(false);

    // Size the backing store to the rendered size × devicePixelRatio so
    // strokes are crisp. Re-done only when the width changes (which clears
    // the drawing) — phones fire resize when the address bar slides in and
    // out, and that mustn't wipe a signature mid-stroke.
    const sizedWidth = useRef(0);
    useEffect(() => {
      function resize() {
        const canvas = canvasRef.current;
        if (!canvas) return;
        const dpr = window.devicePixelRatio || 1;
        const rect = canvas.getBoundingClientRect();
        if (rect.width === sizedWidth.current) return;
        sizedWidth.current = rect.width;
        canvas.width = Math.round(rect.width * dpr);
        canvas.height = Math.round(rect.height * dpr);
        const ctx = canvas.getContext("2d")!;
        ctx.scale(dpr, dpr);
        ctx.lineWidth = 2.2;
        ctx.lineCap = "round";
        ctx.lineJoin = "round";
        ctx.strokeStyle = "#0F2A1C";
        setHasInk(false);
        onChange?.(false);
      }
      resize();
      window.addEventListener("resize", resize);
      return () => window.removeEventListener("resize", resize);
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    function point(e: React.PointerEvent<HTMLCanvasElement>) {
      const rect = e.currentTarget.getBoundingClientRect();
      return { x: e.clientX - rect.left, y: e.clientY - rect.top };
    }

    function onPointerDown(e: React.PointerEvent<HTMLCanvasElement>) {
      e.currentTarget.setPointerCapture(e.pointerId);
      drawing.current = true;
      last.current = point(e);
      // A tap with no movement still leaves a dot.
      const ctx = e.currentTarget.getContext("2d")!;
      ctx.beginPath();
      ctx.arc(last.current.x, last.current.y, 1.1, 0, Math.PI * 2);
      ctx.fillStyle = "#0F2A1C";
      ctx.fill();
      if (!hasInk) {
        setHasInk(true);
        onChange?.(true);
      }
    }

    function onPointerMove(e: React.PointerEvent<HTMLCanvasElement>) {
      if (!drawing.current || !last.current) return;
      const p = point(e);
      const ctx = e.currentTarget.getContext("2d")!;
      ctx.beginPath();
      ctx.moveTo(last.current.x, last.current.y);
      ctx.lineTo(p.x, p.y);
      ctx.stroke();
      last.current = p;
      if (!hasInk) {
        setHasInk(true);
        onChange?.(true);
      }
    }

    function onPointerUp() {
      drawing.current = false;
      last.current = null;
    }

    useImperativeHandle(ref, () => ({
      toDataURL() {
        const canvas = canvasRef.current;
        if (!canvas || !hasInk) return null;
        // Export at display size (not ×dpr) to keep the stored image small.
        const rect = canvas.getBoundingClientRect();
        const out = document.createElement("canvas");
        out.width = Math.round(rect.width);
        out.height = Math.round(rect.height);
        const ctx = out.getContext("2d")!;
        ctx.fillStyle = "#FFFFFF";
        ctx.fillRect(0, 0, out.width, out.height);
        ctx.drawImage(canvas, 0, 0, out.width, out.height);
        return out.toDataURL("image/png");
      },
      clear() {
        const canvas = canvasRef.current;
        if (!canvas) return;
        const ctx = canvas.getContext("2d")!;
        ctx.save();
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.restore();
        setHasInk(false);
        onChange?.(false);
      },
    }));

    return (
      <div className="relative">
        <canvas
          ref={canvasRef}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
          style={{ height, touchAction: "none" }}
          className="w-full rounded-xl border-2 border-dashed border-sage-300 bg-white cursor-crosshair"
          aria-label="Signature box — draw your signature here"
        />
        {!hasInk && (
          <span className="pointer-events-none absolute inset-0 flex items-center justify-center text-sm text-crate-800/30">
            Sign here with your finger or mouse
          </span>
        )}
        <div className="pointer-events-none absolute left-6 right-6 bottom-8 border-b border-sage-300" />
      </div>
    );
  }
);

export default SignaturePad;
