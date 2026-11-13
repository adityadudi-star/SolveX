import { useEffect, useRef } from "react";

/**
 * Decorative animated background: blurred drifting colour blobs + faint grid + light sheen.
 * Only transform/opacity are animated (compositor-only). A tiny scroll parallax moves the blob layer;
 * it is rAF-throttled, passive, cleaned up on unmount and disabled for prefers-reduced-motion.
 */
export function Backdrop() {
  const layer = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    let raf = 0;
    const update = () => {
      raf = 0;
      layer.current?.style.setProperty("transform", `translate3d(0, ${(-window.scrollY * 0.06).toFixed(1)}px, 0)`);
    };
    const onScroll = () => { if (!raf) raf = requestAnimationFrame(update); };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => { window.removeEventListener("scroll", onScroll); if (raf) cancelAnimationFrame(raf); };
  }, []);

  return (
    <div className="backdrop" aria-hidden="true">
      <div className="grid" />
      <div ref={layer} className="absolute inset-0 will-change-transform">
        <div className="blob b1" /><div className="blob b2" /><div className="blob b3" />
      </div>
      <div className="sheen" />
    </div>
  );
}
