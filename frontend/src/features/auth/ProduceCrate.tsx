// Flat-illustration produce crate — the login page's signature visual.
// Pure SVG, no external assets. Individual pieces sway/bob independently
// for a hand-animated feel; all motion respects prefers-reduced-motion.
export default function ProduceCrate() {
  return (
    <svg
      viewBox="0 0 520 420"
      className="w-full h-full max-w-md mx-auto drop-shadow-[0_25px_35px_rgba(0,0,0,0.35)] motion-safe:animate-float"
      style={{ transformOrigin: "50% 60%" }}
      xmlns="http://www.w3.org/2000/svg"
    >
      {/* soft ground shadow */}
      <ellipse cx="260" cy="392" rx="190" ry="18" fill="#0A1D13" opacity="0.5" />

      {/* wooden crate (stays put — everything else moves relative to it) */}
      <g>
        <rect x="60" y="270" width="400" height="110" rx="10" fill="#8A5A34" />
        <rect x="60" y="270" width="400" height="110" rx="10" fill="url(#crateShade)" />
        {[0, 1, 2, 3, 4].map((i) => (
          <rect key={i} x={80 + i * 76} y="270" width="10" height="110" fill="#6E4526" opacity="0.55" />
        ))}
        <rect x="60" y="270" width="400" height="16" fill="#A5713F" />
        <rect x="52" y="258" width="416" height="20" rx="8" fill="#9C6939" />
      </g>

      {/* leafy greens, back — gentle sway from the base */}
      <g
        className="motion-safe:animate-sway"
        style={{ transformOrigin: "130px 270px", transformBox: "view-box" as any }}
      >
        <g transform="translate(90,150)">
          <path d="M40 120 C10 90 10 40 45 10 C60 40 55 90 40 120Z" fill="#2F6D4E" />
          <path d="M40 120 C70 90 75 45 45 15 C35 45 30 90 40 120Z" fill="#3F8A64" />
          <path d="M40 120 C40 90 40 60 40 20" stroke="#1D4A33" strokeWidth="3" fill="none" />
        </g>
      </g>
      <g
        className="motion-safe:animate-sway"
        style={{ transformOrigin: "160px 270px", transformBox: "view-box" as any, animationDelay: "-1.2s" }}
      >
        <g transform="translate(120,145) rotate(18)">
          <path d="M40 120 C10 90 10 40 45 10 C60 40 55 90 40 120Z" fill="#3F8A64" />
          <path d="M40 120 C40 90 40 60 40 20" stroke="#1D4A33" strokeWidth="3" fill="none" />
        </g>
      </g>

      {/* bell pepper — light bob */}
      <g
        className="motion-safe:animate-bob"
        style={{ animationDelay: "-0.6s" }}
      >
        <g transform="translate(330,175)">
          <path
            d="M45 10 C40 -5 55 -8 60 5 C85 5 100 35 92 65 C86 95 60 115 40 108 C15 100 5 70 12 45 C16 25 30 12 45 10Z"
            fill="#EE6A4C"
          />
          <path d="M45 10 C40 -5 55 -8 60 5" stroke="#1D4A33" strokeWidth="4" fill="none" strokeLinecap="round" />
          <ellipse cx="35" cy="45" rx="10" ry="16" fill="#F58A70" opacity="0.7" />
        </g>
      </g>

      {/* carrots, crossed — tiny independent bob */}
      <g className="motion-safe:animate-bob" style={{ animationDelay: "-2s" }}>
        <g transform="translate(250,190) rotate(-8)">
          <path d="M0 0 L60 8 L14 20 Z" fill="#F3A712" />
          <path d="M0 0 L4 -4 L58 6 L60 8 Z" fill="#F7BE45" />
          <g transform="translate(-4,-6)" stroke="#3F8A64" strokeWidth="3" strokeLinecap="round">
            <path d="M0 0 L-14 -14" />
            <path d="M0 0 L-4 -18" />
            <path d="M0 0 L8 -14" />
          </g>
        </g>
      </g>
      <g className="motion-safe:animate-bob" style={{ animationDelay: "-3.1s" }}>
        <g transform="translate(215,205) rotate(10)">
          <path d="M0 0 L58 6 L12 18 Z" fill="#F3A712" />
          <g transform="translate(-2,-4)" stroke="#3F8A64" strokeWidth="3" strokeLinecap="round">
            <path d="M0 0 L-12 -16" />
            <path d="M0 0 L2 -18" />
          </g>
        </g>
      </g>

      {/* tomatoes cluster, front — each with a slightly different bob timing */}
      <g className="motion-safe:animate-bob" style={{ animationDelay: "-0.2s" }}>
        <g transform="translate(120,220)">
          <circle cx="30" cy="35" r="34" fill="#E4472B" />
          <path d="M30 3 C24 -4 20 -2 18 4 C24 4 27 6 30 10 C33 6 36 4 42 4 C40 -2 36 -4 30 3Z" fill="#2F6D4E" />
        </g>
      </g>
      <g className="motion-safe:animate-bob" style={{ animationDelay: "-1.6s" }}>
        <g transform="translate(170,245)">
          <circle cx="24" cy="26" r="26" fill="#C93A21" />
          <path d="M24 2 C19 -4 16 -2 14 3 C19 3 21 4 24 8 C27 4 29 3 34 3 C32 -2 29 -4 24 2Z" fill="#2F6D4E" />
        </g>
      </g>
      <g className="motion-safe:animate-bob" style={{ animationDelay: "-2.6s" }}>
        <g transform="translate(95,255)">
          <circle cx="20" cy="20" r="20" fill="#EE6A4C" />
          <path d="M20 2 C16 -3 13 -1 12 3 C16 3 17 4 20 6 C22 4 24 3 28 3 C26 -1 24 -3 20 2Z" fill="#3F8A64" />
        </g>
      </g>

      {/* orange, front right */}
      <g className="motion-safe:animate-bob" style={{ animationDelay: "-1s" }}>
        <g transform="translate(370,240)">
          <circle cx="26" cy="26" r="27" fill="#F3A712" />
          <circle cx="26" cy="26" r="27" fill="url(#orangeShade)" />
          <circle cx="26" cy="4" r="4" fill="#2F6D4E" />
        </g>
      </g>

      <defs>
        <linearGradient id="crateShade" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#000000" stopOpacity="0" />
          <stop offset="1" stopColor="#000000" stopOpacity="0.18" />
        </linearGradient>
        <radialGradient id="orangeShade" cx="0.35" cy="0.3" r="0.8">
          <stop offset="0" stopColor="#F7BE45" />
          <stop offset="1" stopColor="#E4472B" stopOpacity="0.25" />
        </radialGradient>
      </defs>
    </svg>
  );
}
