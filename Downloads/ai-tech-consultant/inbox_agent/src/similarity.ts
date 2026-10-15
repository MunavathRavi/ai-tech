const words = (s: string): string[] => s.toLowerCase().replace(/[^\p{L}\p{N}{}_ ]+/gu, " ").split(/\s+/).filter(Boolean);

/** "Without changing" means: identical after ignoring case, spacing and punctuation. Deliberately strict:
 *  changing a single word or number counts as an edit and resets the streak. */
export const normalize = (s: string): string => words(s).join(" ");
export const isUnchanged = (a: string, b: string): boolean => normalize(a) === normalize(b);

/** Word-level edit distance similarity in [0,1]; used to measure learning, not to decide autonomy. */
export function similarity(a: string, b: string): number {
  const x = words(a), y = words(b);
  if (x.length === 0 && y.length === 0) return 1;
  let prev = Array.from({ length: y.length + 1 }, (_, j) => j);
  for (let i = 1; i <= x.length; i++) {
    const cur: number[] = [i];
    for (let j = 1; j <= y.length; j++) {
      cur[j] = Math.min((prev[j] ?? 0) + 1, (cur[j - 1] ?? 0) + 1, (prev[j - 1] ?? 0) + (x[i - 1] === y[j - 1] ? 0 : 1));
    }
    prev = cur;
  }
  return 1 - (prev[y.length] ?? 0) / Math.max(x.length, y.length);
}
