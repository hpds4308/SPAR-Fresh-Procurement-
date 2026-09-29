declare global {
  interface Window {
    /** Defined by the inline script in index.html; finishes the progress bar and fades the splash out. */
    __hideSplash?: () => void;
  }
}

/** Dismiss the branded boot splash painted by index.html. Safe to call more than once. */
export function hideBootSplash() {
  window.__hideSplash?.();
}
