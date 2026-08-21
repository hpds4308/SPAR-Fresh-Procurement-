// Flat, premium-style SVG produce icons for the login page's ambient
// background. Soft gradients + restrained line detail, no cartoon outlines.
// Every icon fills its viewBox so parents can size it freely via width/height.
import { useId } from "react";

type IconProps = {
  className?: string;
};

export function LeafIllustration({ className }: IconProps) {
  const id = useId();
  return (
    <svg viewBox="0 0 100 100" className={className} xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id={`leaf-${id}`} x1="10" y1="10" x2="90" y2="90" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#4C9A6E" />
          <stop offset="100%" stopColor="#1D4A33" />
        </linearGradient>
      </defs>
      <path
        d="M85 15C50 15 18 35 15 72c-.6 6 4 11 10 10 40-5 65-32 62-65-.2-2-1-2-2-2Z"
        fill={`url(#leaf-${id})`}
      />
      <path d="M22 76C40 58 58 40 80 20" stroke="#0F2A1C" strokeOpacity="0.35" strokeWidth="2.4" strokeLinecap="round" fill="none" />
    </svg>
  );
}

export function LemonIllustration({ className }: IconProps) {
  const id = useId();
  return (
    <svg viewBox="0 0 100 100" className={className} xmlns="http://www.w3.org/2000/svg">
      <defs>
        <radialGradient id={`lemon-${id}`} cx="38%" cy="34%" r="70%">
          <stop offset="0%" stopColor="#FCE38A" />
          <stop offset="60%" stopColor="#F7C948" />
          <stop offset="100%" stopColor="#E0A521" />
        </radialGradient>
      </defs>
      <ellipse cx="50" cy="50" rx="38" ry="30" fill={`url(#lemon-${id})`} />
      <ellipse cx="14" cy="50" rx="6" ry="5" fill="#E0A521" />
      <ellipse cx="86" cy="50" rx="6" ry="5" fill="#E0A521" />
      <ellipse cx="38" cy="38" rx="14" ry="8" fill="#FFF3C4" opacity="0.55" />
    </svg>
  );
}

export function OrangeIllustration({ className }: IconProps) {
  const id = useId();
  return (
    <svg viewBox="0 0 100 100" className={className} xmlns="http://www.w3.org/2000/svg">
      <defs>
        <radialGradient id={`orange-${id}`} cx="36%" cy="32%" r="72%">
          <stop offset="0%" stopColor="#FFC46B" />
          <stop offset="55%" stopColor="#F3A712" />
          <stop offset="100%" stopColor="#C97D0A" />
        </radialGradient>
      </defs>
      <circle cx="50" cy="52" r="38" fill={`url(#orange-${id})`} />
      <path d="M50 14c3 3 5 7 4 12" stroke="#5B7A4A" strokeWidth="3" strokeLinecap="round" fill="none" />
      <ellipse cx="38" cy="38" rx="13" ry="7" fill="#FFE1A8" opacity="0.5" />
    </svg>
  );
}

export function AppleIllustration({ className }: IconProps) {
  const id = useId();
  return (
    <svg viewBox="0 0 100 100" className={className} xmlns="http://www.w3.org/2000/svg">
      <defs>
        <radialGradient id={`apple-${id}`} cx="35%" cy="30%" r="75%">
          <stop offset="0%" stopColor="#F0765C" />
          <stop offset="55%" stopColor="#E4472B" />
          <stop offset="100%" stopColor="#A82F1A" />
        </radialGradient>
      </defs>
      <path
        d="M50 30c8-10 24-10 28 2 5 14-3 40-22 50-3 1.6-8 1.6-11 0C26 72 18 46 23 32c4-12 20-12 27-2Z"
        fill={`url(#apple-${id})`}
      />
      <path d="M50 30c0-8 2-14 8-18" stroke="#5B3A22" strokeWidth="3" strokeLinecap="round" fill="none" />
      <path d="M52 15c6-4 12-4 16 0" stroke="#3F8A64" strokeWidth="3" strokeLinecap="round" fill="none" />
      <ellipse cx="38" cy="42" rx="10" ry="6" fill="#FFD5C7" opacity="0.45" />
    </svg>
  );
}

export function TomatoIllustration({ className }: IconProps) {
  const id = useId();
  return (
    <svg viewBox="0 0 100 100" className={className} xmlns="http://www.w3.org/2000/svg">
      <defs>
        <radialGradient id={`tomato-${id}`} cx="36%" cy="34%" r="72%">
          <stop offset="0%" stopColor="#F0765C" />
          <stop offset="55%" stopColor="#E4472B" />
          <stop offset="100%" stopColor="#A82F1A" />
        </radialGradient>
      </defs>
      <circle cx="50" cy="55" r="34" fill={`url(#tomato-${id})`} />
      {[0, 1, 2, 3, 4].map((i) => {
        const a = (i / 5) * Math.PI * 2;
        const x = 50 + Math.cos(a) * 9;
        const y = 24 + Math.sin(a) * 4;
        return <ellipse key={i} cx={x} cy={y} rx="4" ry="9" fill="#2F6D4E" transform={`rotate(${(i * 72)} ${x} ${y})`} />;
      })}
      <ellipse cx="38" cy="44" rx="11" ry="6" fill="#FFD5C7" opacity="0.4" />
    </svg>
  );
}

export function BellPepperIllustration({ className, color = "red" }: IconProps & { color?: "red" | "green" | "yellow" }) {
  const id = useId();
  const palette = {
    red: ["#F0765C", "#E4472B", "#A82F1A"],
    green: ["#6FBB8A", "#3F8A64", "#1D4A33"],
    yellow: ["#FCE38A", "#F3A712", "#C97D0A"],
  }[color];
  return (
    <svg viewBox="0 0 100 100" className={className} xmlns="http://www.w3.org/2000/svg">
      <defs>
        <radialGradient id={`pepper-${id}`} cx="34%" cy="26%" r="80%">
          <stop offset="0%" stopColor={palette[0]} />
          <stop offset="55%" stopColor={palette[1]} />
          <stop offset="100%" stopColor={palette[2]} />
        </radialGradient>
      </defs>
      <path
        d="M50 28c-14 0-26 14-26 34 0 16 12 26 26 26s26-10 26-26c0-20-12-34-26-34Z"
        fill={`url(#pepper-${id})`}
      />
      <path d="M50 28c-3-8-1-16 6-20" stroke="#2F6D4E" strokeWidth="4" strokeLinecap="round" fill="none" />
      <ellipse cx="36" cy="44" rx="9" ry="14" fill="#fff" opacity="0.18" />
    </svg>
  );
}

export function LettuceIllustration({ className }: IconProps) {
  const id = useId();
  return (
    <svg viewBox="0 0 100 100" className={className} xmlns="http://www.w3.org/2000/svg">
      <defs>
        <radialGradient id={`lettuce-${id}`} cx="45%" cy="35%" r="75%">
          <stop offset="0%" stopColor="#B7E0A6" />
          <stop offset="60%" stopColor="#7BC088" />
          <stop offset="100%" stopColor="#3F8A64" />
        </radialGradient>
      </defs>
      {[0, 1, 2, 3, 4, 5].map((i) => {
        const a = (i / 6) * Math.PI * 2;
        const cx = 50 + Math.cos(a) * 22;
        const cy = 52 + Math.sin(a) * 20;
        return <circle key={i} cx={cx} cy={cy} r="20" fill={`url(#lettuce-${id})`} opacity="0.92" />;
      })}
      <circle cx="50" cy="52" r="20" fill={`url(#lettuce-${id})`} />
    </svg>
  );
}

export function BroccoliIllustration({ className }: IconProps) {
  const id = useId();
  return (
    <svg viewBox="0 0 100 100" className={className} xmlns="http://www.w3.org/2000/svg">
      <defs>
        <radialGradient id={`broc-${id}`} cx="40%" cy="30%" r="75%">
          <stop offset="0%" stopColor="#5FAE7C" />
          <stop offset="60%" stopColor="#2F6D4E" />
          <stop offset="100%" stopColor="#1D4A33" />
        </radialGradient>
      </defs>
      {[[36, 30, 15], [62, 28, 16], [50, 44, 20], [30, 48, 13], [70, 48, 14]].map(([cx, cy, r], i) => (
        <circle key={i} cx={cx} cy={cy} r={r} fill={`url(#broc-${id})`} />
      ))}
      <rect x="42" y="55" width="16" height="30" rx="7" fill="#D9C79A" />
    </svg>
  );
}

export function CauliflowerIllustration({ className }: IconProps) {
  const id = useId();
  return (
    <svg viewBox="0 0 100 100" className={className} xmlns="http://www.w3.org/2000/svg">
      <defs>
        <radialGradient id={`cauli-${id}`} cx="40%" cy="30%" r="75%">
          <stop offset="0%" stopColor="#FDFBF3" />
          <stop offset="70%" stopColor="#F0EBD8" />
          <stop offset="100%" stopColor="#D8CFAE" />
        </radialGradient>
      </defs>
      {[[38, 34, 14], [62, 32, 15], [50, 48, 19], [28, 50, 12], [72, 50, 13]].map(([cx, cy, r], i) => (
        <circle key={i} cx={cx} cy={cy} r={r} fill={`url(#cauli-${id})`} />
      ))}
      <path d="M30 58c-4 6-4 12 0 16M70 58c4 6 4 12 0 16" stroke="#5FAE7C" strokeWidth="5" strokeLinecap="round" fill="none" />
    </svg>
  );
}

export function CucumberIllustration({ className }: IconProps) {
  const id = useId();
  return (
    <svg viewBox="0 0 140 60" className={className} xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id={`cuke-${id}`} x1="0" y1="0" x2="0" y2="60" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#8BCB8E" />
          <stop offset="55%" stopColor="#4C9A6E" />
          <stop offset="100%" stopColor="#2F6D4E" />
        </linearGradient>
      </defs>
      <rect x="8" y="14" width="124" height="32" rx="16" fill={`url(#cuke-${id})`} />
      <ellipse cx="45" cy="24" rx="30" ry="5" fill="#D8F0CF" opacity="0.4" />
    </svg>
  );
}

export function RedOnionIllustration({ className }: IconProps) {
  const id = useId();
  return (
    <svg viewBox="0 0 100 100" className={className} xmlns="http://www.w3.org/2000/svg">
      <defs>
        <radialGradient id={`onion-${id}`} cx="38%" cy="30%" r="75%">
          <stop offset="0%" stopColor="#C48CC9" />
          <stop offset="55%" stopColor="#8E4E96" />
          <stop offset="100%" stopColor="#5C2E63" />
        </radialGradient>
      </defs>
      <path d="M50 22c18 0 30 16 30 36 0 16-13 28-30 28S20 74 20 58c0-20 12-36 30-36Z" fill={`url(#onion-${id})`} />
      <path d="M50 22c-1-8 1-14 6-18M50 22c1-8-1-14-6-18" stroke="#B87A9E" strokeWidth="2.5" strokeLinecap="round" fill="none" />
      <ellipse cx="38" cy="42" rx="9" ry="14" fill="#fff" opacity="0.15" />
    </svg>
  );
}

export function CarrotIllustration({ className }: IconProps) {
  const id = useId();
  return (
    <svg viewBox="0 0 60 130" className={className} xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id={`carrot-${id}`} x1="0" y1="0" x2="60" y2="130" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#FFB067" />
          <stop offset="100%" stopColor="#E8792A" />
        </linearGradient>
      </defs>
      <path d="M30 40c14 0 20 10 18 26L34 122c-1 5-7 5-8 0L10 66C8 50 16 40 30 40Z" fill={`url(#carrot-${id})`} />
      <path d="M22 35c-6-14-2-26 4-34M30 32c0-16 4-26 8-32M38 35c6-12 2-24-2-30" stroke="#3F8A64" strokeWidth="5" strokeLinecap="round" fill="none" />
    </svg>
  );
}

export function LeekIllustration({ className }: IconProps) {
  const id = useId();
  return (
    <svg viewBox="0 0 60 140" className={className} xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id={`leek-${id}`} x1="0" y1="0" x2="0" y2="140" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#3F8A64" />
          <stop offset="45%" stopColor="#CDE7C8" />
          <stop offset="100%" stopColor="#F4F2E4" />
        </linearGradient>
      </defs>
      <path d="M20 4c14 20 14 40 6 60l-6 70c0 4-8 4-8 0l-6-70C-2 44 2 24 14 4c1-2 5-2 6 0Z" fill={`url(#leek-${id})`} />
    </svg>
  );
}

export function AvocadoIllustration({ className }: IconProps) {
  const id = useId();
  return (
    <svg viewBox="0 0 100 100" className={className} xmlns="http://www.w3.org/2000/svg">
      <defs>
        <radialGradient id={`avo-${id}`} cx="38%" cy="30%" r="75%">
          <stop offset="0%" stopColor="#8FBE7A" />
          <stop offset="60%" stopColor="#4C7A3C" />
          <stop offset="100%" stopColor="#2E4E24" />
        </radialGradient>
      </defs>
      <path d="M50 16c16 0 28 18 28 42s-12 34-28 34-28-14-28-34S34 16 50 16Z" fill={`url(#avo-${id})`} />
      <circle cx="50" cy="60" r="15" fill="#C97D0A" opacity="0.85" />
    </svg>
  );
}

export function PapayaIllustration({ className }: IconProps) {
  const id = useId();
  return (
    <svg viewBox="0 0 140 90" className={className} xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id={`papaya-${id}`} x1="0" y1="0" x2="140" y2="90" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#FFC46B" />
          <stop offset="55%" stopColor="#F3A712" />
          <stop offset="100%" stopColor="#DE7A1F" />
        </linearGradient>
      </defs>
      <path d="M20 45c0-20 22-32 50-32s50 12 50 32-22 32-50 32S20 65 20 45Z" fill={`url(#papaya-${id})`} />
      <ellipse cx="60" cy="35" rx="20" ry="8" fill="#FFE1A8" opacity="0.45" />
    </svg>
  );
}

export function MangoIllustration({ className }: IconProps) {
  const id = useId();
  return (
    <svg viewBox="0 0 100 100" className={className} xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id={`mango-${id}`} x1="10" y1="10" x2="90" y2="90" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#F7C948" />
          <stop offset="55%" stopColor="#EE6A4C" />
          <stop offset="100%" stopColor="#C93A21" />
        </linearGradient>
      </defs>
      <path d="M22 55c0-24 18-40 40-36 16 3 24 16 20 30-5 18-24 34-42 30-12-3-18-13-18-24Z" fill={`url(#mango-${id})`} />
      <ellipse cx="38" cy="42" rx="12" ry="7" fill="#FFEFC4" opacity="0.4" />
    </svg>
  );
}

export function WatermelonIllustration({ className }: IconProps) {
  const id = useId();
  return (
    <svg viewBox="0 0 100 100" className={className} xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id={`wm-rind-${id}`} x1="0" y1="0" x2="0" y2="100" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#3F8A64" />
          <stop offset="100%" stopColor="#1D4A33" />
        </linearGradient>
      </defs>
      <path d="M8 50a42 42 0 0 1 84 0Z" fill={`url(#wm-rind-${id})`} />
      <path d="M14 50a36 36 0 0 1 72 0Z" fill="#F4F2E4" />
      <path d="M20 50a30 30 0 0 1 60 0Z" fill="#F0765C" />
      {[-18, -6, 6, 18].map((x, i) => (
        <ellipse key={i} cx={50 + x} cy={44} rx="2.4" ry="3.4" fill="#2A1A16" />
      ))}
    </svg>
  );
}

export function PineappleIllustration({ className }: IconProps) {
  const id = useId();
  return (
    <svg viewBox="0 0 90 140" className={className} xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id={`pine-${id}`} x1="0" y1="40" x2="90" y2="140" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#F7C948" />
          <stop offset="100%" stopColor="#C97D0A" />
        </linearGradient>
      </defs>
      <path d="M20 30c8 8 42 8 50 0l-8 8c6 6 6 10 0 16 6 6 6 10 0 16 6 6 6 10 0 16-8 8-34 8-42 0 6-6 6-10 0-16-6-6-6-10 0-16-6-6-6-10 0-16Z" fill={`url(#pine-${id})`} />
      {[0, 1, 2].map((i) => (
        <path
          key={i}
          d={`M${45 - 8 * (i - 1)} 30c-4-14-2-22 4-28`}
          stroke="#3F8A64"
          strokeWidth="6"
          strokeLinecap="round"
          fill="none"
          transform={`rotate(${(i - 1) * 18} 45 30)`}
        />
      ))}
    </svg>
  );
}
