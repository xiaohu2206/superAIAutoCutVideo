import { useCallback, useEffect, useRef } from "react";

export const useDebouncedCallback = <TArgs extends unknown[]>(
  callback: (...args: TArgs) => void | Promise<void>,
  delayMs: number
) => {
  const callbackRef = useRef(callback);
  const timeoutRef = useRef<number | null>(null);

  useEffect(() => {
    callbackRef.current = callback;
  }, [callback]);

  const cancel = useCallback(() => {
    if (timeoutRef.current === null) return;
    window.clearTimeout(timeoutRef.current);
    timeoutRef.current = null;
  }, []);

  const debounced = useCallback(
    (...args: TArgs) => {
      cancel();
      timeoutRef.current = window.setTimeout(() => {
        void callbackRef.current(...args);
      }, delayMs);
    },
    [cancel, delayMs]
  );

  useEffect(() => cancel, [cancel]);

  return [debounced, cancel] as const;
};
