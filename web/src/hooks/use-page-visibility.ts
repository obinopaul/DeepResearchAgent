import { useEffect, useState } from "react";

export function usePageVisibility() {
  const [isVisible, setIsVisible] = useState(() => {
    if (typeof document === "undefined") {
      return true;
    }
    return !document.hidden;
  });

  useEffect(() => {
    if (typeof document === "undefined") {
      return;
    }
    const handleVisibilityChange = () => {
      setIsVisible(!document.hidden);
    };
    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => {
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, []);

  return isVisible;
}
