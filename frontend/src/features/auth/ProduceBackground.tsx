import { CSSProperties, ReactNode } from "react";
import {
  LeafIllustration,
  LemonIllustration,
  OrangeIllustration,
  TomatoIllustration,
  BellPepperIllustration,
  LettuceIllustration,
  BroccoliIllustration,
  CauliflowerIllustration,
  CucumberIllustration,
  RedOnionIllustration,
} from "./ProduceIcons";

type Variant = "float" | "sway" | "drift" | "glow";

type FloatingProduceProps = {
  children: ReactNode;
  /** Positioning, e.g. { top: "-10%", left: "-6%" } — use negative values to bleed off-screen. */
  position: CSSProperties;
  /** Pixel size of the square icon box. */
  size: number;
  /** Which subtle motion pattern to use. */
  variant?: Variant;
  /** Animation duration, in seconds — vary per element so nothing is in sync. */
  duration?: number;
  /** Negative delay starts the loop mid-cycle so elements don't move in lockstep. */
  delay?: number;
  /** Base opacity for the resting state. */
  opacity?: number;
  /** Rotation range in degrees, e.g. [-2, 2]. */
  rotationRange?: [number, number];
  /** Tailwind responsive-visibility classes, e.g. "hidden sm:block". Defaults to always visible. */
  visibility?: string;
  className?: string;
};

/**
 * A single decorative produce element. Purely CSS-animated (transform +
 * opacity only, GPU-friendly) via the `produce-*` keyframes declared in
 * tailwind.config.js. `motion-safe:` ensures the animation is skipped
 * entirely when the user has requested reduced motion.
 */
export function FloatingProduce({
  children,
  position,
  size,
  variant = "float",
  duration = 10,
  delay = 0,
  opacity = 1,
  rotationRange = [-2, 2],
  visibility = "",
  className = "",
}: FloatingProduceProps) {
  const animationClass = {
    float: "motion-safe:animate-produce-float",
    sway: "motion-safe:animate-produce-sway",
    drift: "motion-safe:animate-produce-drift",
    glow: "motion-safe:animate-produce-glow",
  }[variant];

  const style: CSSProperties & Record<string, string | number> = {
    ...position,
    width: size,
    height: size,
    opacity,
    animationDuration: `${duration}s`,
    animationDelay: `${delay}s`,
    "--produce-rot-a": `${rotationRange[0]}deg`,
    "--produce-rot-b": `${rotationRange[1]}deg`,
  };

  return (
    <div
      aria-hidden
      className={`absolute drop-shadow-[0_18px_24px_rgba(15,42,28,0.18)] will-change-transform ${animationClass} ${visibility} ${className}`}
      style={style}
    >
      {children}
    </div>
  );
}

type FloatingLeafProps = {
  position: CSSProperties;
  size: number;
  duration?: number;
  delay?: number;
  opacity?: [number, number];
  visibility?: string;
};

/** A lighter-weight leaf accent — slow diagonal drift with a gentle opacity breathe. */
export function FloatingLeaf({
  position,
  size,
  duration = 14,
  delay = 0,
  opacity = [0.5, 0.8],
  visibility = "",
}: FloatingLeafProps) {
  const style: CSSProperties & Record<string, string | number> = {
    ...position,
    width: size,
    height: size,
    "--produce-op-a": opacity[0],
    "--produce-op-b": opacity[1],
    animationDuration: `${duration}s`,
    animationDelay: `${delay}s`,
  };
  return (
    <div
      aria-hidden
      className={`absolute motion-safe:animate-produce-drift will-change-transform ${visibility}`}
      style={style}
    >
      <LeafIllustration className="w-full h-full" />
    </div>
  );
}

/**
 * The full ambient scene: fresh produce gathered around the outer edges,
 * leaving the centre clear for the login card. Every element:
 *  - is `pointer-events-none` and sits in its own layer behind the card
 *  - animates only `transform`/`opacity` (no layout thrash)
 *  - has an independent duration/delay so nothing moves in lockstep
 *  - is progressively thinned out on smaller screens via visibility classes
 */
export default function ProduceBackground() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden z-0">
      {/* ── top-left ── */}
      <FloatingLeaf position={{ top: "-6%", left: "-5%" }} size={150} duration={15} delay={-3} />
      <FloatingLeaf
        position={{ top: "9%", left: "9%" }}
        size={70}
        duration={12}
        delay={-7}
        visibility="hidden sm:block"
      />
      <FloatingProduce
        position={{ top: "2%", left: "17%" }}
        size={64}
        variant="sway"
        duration={11}
        delay={-2}
        rotationRange={[-3, 2]}
        visibility="hidden md:block"
      >
        <LemonIllustration className="w-full h-full" />
      </FloatingProduce>

      {/* ── top-right ── */}
      <FloatingProduce
        position={{ top: "-7%", right: "-6%" }}
        size={140}
        variant="float"
        duration={12}
        delay={-5}
        rotationRange={[-1.5, 1.5]}
        opacity={0.95}
      >
        <OrangeIllustration className="w-full h-full" />
      </FloatingProduce>
      <FloatingProduce
        position={{ top: "12%", right: "13%" }}
        size={56}
        variant="sway"
        duration={10}
        delay={-4}
        rotationRange={[-2.5, 2]}
        visibility="hidden sm:block"
      >
        <LemonIllustration className="w-full h-full" />
      </FloatingProduce>
      <FloatingLeaf
        position={{ top: "22%", right: "3%" }}
        size={60}
        duration={13}
        delay={-9}
        visibility="hidden md:block"
      />

      {/* ── bottom-left ── */}
      <FloatingProduce
        position={{ bottom: "-8%", left: "-6%" }}
        size={160}
        variant="float"
        duration={13}
        delay={-6}
        rotationRange={[-1.5, 1.5]}
      >
        <LettuceIllustration className="w-full h-full" />
      </FloatingProduce>
      <FloatingProduce
        position={{ bottom: "4%", left: "14%" }}
        size={84}
        variant="sway"
        duration={11}
        delay={-1}
        rotationRange={[-2, 2]}
        visibility="hidden sm:block"
      >
        <BroccoliIllustration className="w-full h-full" />
      </FloatingProduce>
      <FloatingProduce
        position={{ bottom: "16%", left: "3%" }}
        size={62}
        variant="float"
        duration={9}
        delay={-3}
        rotationRange={[-3, 2]}
        visibility="hidden md:block"
      >
        <BellPepperIllustration className="w-full h-full" color="green" />
      </FloatingProduce>
      <FloatingProduce
        position={{ bottom: "26%", left: "9%" }}
        size={46}
        variant="glow"
        duration={9}
        delay={-2}
        visibility="hidden lg:block"
      >
        <TomatoIllustration className="w-full h-full" />
      </FloatingProduce>
      <FloatingLeaf
        position={{ bottom: "2%", left: "26%" }}
        size={50}
        duration={16}
        delay={-8}
        visibility="hidden lg:block"
      />

      {/* ── bottom-right ── */}
      <FloatingProduce
        position={{ bottom: "-9%", right: "-6%" }}
        size={150}
        variant="float"
        duration={14}
        delay={-4}
        rotationRange={[-1.5, 1.5]}
      >
        <CauliflowerIllustration className="w-full h-full" />
      </FloatingProduce>
      <FloatingProduce
        position={{ bottom: "6%", right: "15%" }}
        size={74}
        variant="sway"
        duration={10}
        delay={-6}
        rotationRange={[-2, 2.5]}
        visibility="hidden sm:block"
      >
        <BellPepperIllustration className="w-full h-full" color="red" />
      </FloatingProduce>
      <FloatingProduce
        position={{ bottom: "18%", right: "5%" }}
        size={48}
        variant="glow"
        duration={8}
        delay={-1}
        visibility="hidden md:block"
      >
        <TomatoIllustration className="w-full h-full" />
      </FloatingProduce>
      <FloatingProduce
        position={{ bottom: "27%", right: "12%" }}
        size={96}
        variant="sway"
        duration={12}
        delay={-8}
        rotationRange={[-2, 2]}
        visibility="hidden lg:block"
      >
        <CucumberIllustration className="w-full h-full" />
      </FloatingProduce>
      <FloatingProduce
        position={{ bottom: "9%", right: "24%" }}
        size={50}
        variant="float"
        duration={11}
        delay={-5}
        rotationRange={[-2.5, 2]}
        visibility="hidden lg:block"
      >
        <RedOnionIllustration className="w-full h-full" />
      </FloatingProduce>
      <FloatingLeaf
        position={{ bottom: "1%", right: "28%" }}
        size={54}
        duration={15}
        delay={-10}
        visibility="hidden md:block"
      />

      {/* ── side accents (larger screens only) ── */}
      <FloatingLeaf
        position={{ top: "45%", left: "1%" }}
        size={50}
        duration={17}
        delay={-6}
        opacity={[0.3, 0.55]}
        visibility="hidden lg:block"
      />
      <FloatingLeaf
        position={{ top: "40%", right: "1%" }}
        size={44}
        duration={16}
        delay={-11}
        opacity={[0.3, 0.5]}
        visibility="hidden lg:block"
      />
    </div>
  );
}
