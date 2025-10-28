const DEBUG_STREAM_ENABLED = process.env.NEXT_PUBLIC_DEBUG_STREAM === "true";

export function debugLog(...args: Parameters<typeof console.debug>) {
  if (!DEBUG_STREAM_ENABLED) {
    return;
  }
  if (typeof console !== "undefined") {
    console.debug(...args);
  }
}

export function isDebugStreamEnabled() {
  return DEBUG_STREAM_ENABLED;
}
