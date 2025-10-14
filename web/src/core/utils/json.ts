export function parseJSON<T>(json: string | null | undefined, fallback: T) {
  if (!json) return fallback;
  try {
    const raw = json
      .trim()
      .replace(/^```json\s*/i, "")
      .replace(/^```js\s*/i, "")
      .replace(/^```ts\s*/i, "")
      .replace(/^```plaintext\s*/i, "")
      .replace(/^```\s*/i, "")
      .replace(/\s*```$/i, "")
      .trim();

    if (raw.length === 0) return fallback;

    const start = raw[0];
    if (start !== "{" && start !== "[") return fallback;
    const endChar = start === "{" ? "}" : "]";
    const lastEnd = raw.lastIndexOf(endChar);
    if (lastEnd < 0) return fallback; // incomplete JSON while streaming

    // Slice to last matching end char to drop any trailing tokens
    const candidate = raw.slice(0, lastEnd + 1);
    return JSON.parse(candidate) as T;
  } catch {
    return fallback;
  }
}
