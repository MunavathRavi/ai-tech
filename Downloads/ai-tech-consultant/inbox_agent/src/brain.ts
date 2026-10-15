import { BrainAnswerSchema, type BrainAnswer } from "./types.js";

/** Task 2 talks to Task 1 ONLY through this interface (its HTTP API). */
export interface Brain { ask(question: string): Promise<BrainAnswer> }

export class HttpBrain implements Brain {
  constructor(
    private readonly baseUrl = process.env["BRAIN_URL"] ?? "http://localhost:8001",
    private readonly apiKey = process.env["BRAIN_API_KEY"] ?? "",
    private readonly timeoutMs = 15_000,
    private readonly retries = 2,
  ) {}

  async ask(question: string): Promise<BrainAnswer> {
    let lastErr: unknown;
    for (let i = 0; i <= this.retries; i++) {
      const ctl = new AbortController();
      const timer = setTimeout(() => ctl.abort(), this.timeoutMs);
      try {
        const r = await fetch(`${this.baseUrl}/ask`, {
          method: "POST",
          headers: { "content-type": "application/json", "x-api-key": this.apiKey },
          body: JSON.stringify({ question, asker: "inbox-agent" }),
          signal: ctl.signal,
        });
        if (!r.ok) throw new Error(`brain returned ${r.status}`);
        return BrainAnswerSchema.parse(await r.json());
      } catch (e) {
        lastErr = e;
        await new Promise((res) => setTimeout(res, 300 * 2 ** i));
      } finally {
        clearTimeout(timer);
      }
    }
    throw new Error(`Knowledge Brain unreachable: ${String(lastErr)}`);
  }
}
