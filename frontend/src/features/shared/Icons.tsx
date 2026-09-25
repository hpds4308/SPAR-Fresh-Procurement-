/**
 * A small, consistent monoline icon set for the app shell — tab
 * navigation and empty states. Kept deliberately restrained (single
 * 1.75px stroke, no fills) so they read as a quiet system rather than a
 * decoration competing with the produce-market personality already
 * established on the login screen.
 */
import { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

function base(children: React.ReactNode, props: IconProps) {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      {...props}
    >
      {children}
    </svg>
  );
}

export function IconCrate(props: IconProps) {
  return base(
    <>
      <path d="M2.5 6.5 10 3l7.5 3.5-7.5 3.5-7.5-3.5Z" />
      <path d="M2.5 6.5v7L10 17l7.5-3.5v-7" />
      <path d="M10 10v7" />
      <path d="M5.8 4.9 13.3 8.4M14.2 4.9 6.7 8.4" />
    </>,
    props
  );
}

export function IconBasket(props: IconProps) {
  return base(
    <>
      <path d="M3.5 8h13l-1.4 8.1a1.5 1.5 0 0 1-1.48 1.24H6.38A1.5 1.5 0 0 1 4.9 16.1L3.5 8Z" />
      <path d="M6.5 8 8.7 3.2M13.5 8 11.3 3.2M2.5 8h15" />
      <path d="M8.2 11v4M11.8 11v4" />
    </>,
    props
  );
}

export function IconClock(props: IconProps) {
  return base(
    <>
      <circle cx="10" cy="10.5" r="7" />
      <path d="M10 6.7v4l2.8 1.6" />
    </>,
    props
  );
}

export function IconTruck(props: IconProps) {
  return base(
    <>
      <path d="M2 5.5h9v8H2z" />
      <path d="M11 8.5h3.6L17 11v2.5h-6z" />
      <circle cx="6" cy="15" r="1.6" />
      <circle cx="14" cy="15" r="1.6" />
    </>,
    props
  );
}

export function IconTag(props: IconProps) {
  return base(
    <>
      <path d="M10.4 2.5h4.6a1 1 0 0 1 1 1v4.6a1 1 0 0 1-.3.7l-8 8a1 1 0 0 1-1.4 0l-4.6-4.6a1 1 0 0 1 0-1.4l8-8a1 1 0 0 1 .7-.3Z" />
      <circle cx="13.2" cy="6.2" r="1.1" />
    </>,
    props
  );
}

export function IconChart(props: IconProps) {
  return base(
    <>
      <path d="M3 17V9M8 17V4.5M13 17v-6M18 17H2" />
    </>,
    props
  );
}

export function IconBranches(props: IconProps) {
  return base(
    <>
      <circle cx="6" cy="4.5" r="1.9" />
      <circle cx="6" cy="15.5" r="1.9" />
      <circle cx="15" cy="10" r="1.9" />
      <path d="M6 6.4v7.2M7.6 9 13.3 11" />
    </>,
    props
  );
}

export function IconPlus(props: IconProps) {
  return base(
    <>
      <path d="M10 4v12M4 10h12" />
    </>,
    props
  );
}

export function IconChat(props: IconProps) {
  return base(
    <>
      <path d="M3 5.2A1.7 1.7 0 0 1 4.7 3.5h10.6A1.7 1.7 0 0 1 17 5.2v6.1a1.7 1.7 0 0 1-1.7 1.7H9.4L5.5 16v-3H4.7A1.7 1.7 0 0 1 3 11.3V5.2Z" />
    </>,
    props
  );
}

export function IconShield(props: IconProps) {
  return base(
    <>
      <path d="M10 2.8 4 5v4.6c0 3.6 2.5 6.4 6 7.6 3.5-1.2 6-4 6-7.6V5l-6-2.2Z" />
      <path d="m7.4 10 1.8 1.8 3.4-3.6" />
    </>,
    props
  );
}

export function IconPercent(props: IconProps) {
  return base(
    <>
      <path d="m5 15 10-10" />
      <circle cx="6" cy="6" r="1.8" />
      <circle cx="14" cy="14" r="1.8" />
    </>,
    props
  );
}

export function IconChevronLeft(props: IconProps) {
  return base(
    <>
      <path d="M12.5 4.5 7 10l5.5 5.5" />
    </>,
    props
  );
}

export function IconChevronRight(props: IconProps) {
  return base(
    <>
      <path d="M7.5 4.5 13 10l-5.5 5.5" />
    </>,
    props
  );
}

export function IconChevronDown(props: IconProps) {
  return base(
    <>
      <path d="M4.5 7.5 10 13l5.5-5.5" />
    </>,
    props
  );
}

export function IconBell(props: IconProps) {
  return base(
    <>
      <path d="M5 8.2a5 5 0 0 1 10 0c0 3.4 1 4.6 1.6 5.2H3.4C4 12.8 5 11.6 5 8.2Z" />
      <path d="M8.3 15.8a1.8 1.8 0 0 0 3.4 0" />
    </>,
    props
  );
}

export function IconUser(props: IconProps) {
  return base(
    <>
      <circle cx="10" cy="6.8" r="3.1" />
      <path d="M3.8 16.2c.9-3.1 3.3-4.7 6.2-4.7s5.3 1.6 6.2 4.7" />
    </>,
    props
  );
}

export function IconLogout(props: IconProps) {
  return base(
    <>
      <path d="M8.5 3.5H5.7A1.7 1.7 0 0 0 4 5.2v9.6a1.7 1.7 0 0 0 1.7 1.7h2.8" />
      <path d="M12.5 13.5 16.5 10l-4-3.5M16.5 10h-9" />
    </>,
    props
  );
}

export function IconMenu(props: IconProps) {
  return base(
    <>
      <path d="M3.5 6h13M3.5 10h13M3.5 14h13" />
    </>,
    props
  );
}

export function IconGrid(props: IconProps) {
  return base(
    <>
      <rect x="3" y="3" width="6" height="6" rx="1" />
      <rect x="11" y="3" width="6" height="6" rx="1" />
      <rect x="3" y="11" width="6" height="6" rx="1" />
      <rect x="11" y="11" width="6" height="6" rx="1" />
    </>,
    props
  );
}

export function IconStore(props: IconProps) {
  return base(
    <>
      <path d="M3 7.5 4 3.5h12l1 4" />
      <path d="M3 7.5a2 2 0 0 0 4 0 2 2 0 0 0 4 0 2 2 0 0 0 4 0 2 2 0 0 0 4 0" />
      <path d="M4.5 7.8V16.5h11V7.8" />
      <path d="M8.3 16.5v-4.2a1.7 1.7 0 0 1 1.7-1.7 1.7 1.7 0 0 1 1.7 1.7v4.2" />
    </>,
    props
  );
}

export function IconLog(props: IconProps) {
  return base(
    <>
      <path d="M4.5 3.5h11v13h-11z" />
      <path d="M7 7h6M7 10h6M7 13h4" />
    </>,
    props
  );
}

export function IconSettings(props: IconProps) {
  return base(
    <>
      <circle cx="10" cy="10" r="2.6" />
      <path d="M10 3v2.1M10 14.9V17M17 10h-2.1M5.1 10H3M14.8 5.2l-1.5 1.5M6.7 13.3l-1.5 1.5M14.8 14.8l-1.5-1.5M6.7 6.7 5.2 5.2" />
    </>,
    props
  );
}
