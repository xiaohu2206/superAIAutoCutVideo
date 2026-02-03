import { useLayoutEffect, useState } from "react";

export const useElementWidth = (ref: React.RefObject<HTMLElement>) => {
  const [width, setWidth] = useState(0);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;

    const apply = () => {
      const next = el.getBoundingClientRect().width;
      setWidth((prev) => (Math.abs(prev - next) < 0.5 ? prev : next));
    };

    apply();
    const ro = new ResizeObserver(() => apply());
    ro.observe(el);
    return () => ro.disconnect();
  }, [ref]);

  return width;
};

