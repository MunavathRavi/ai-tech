import Anthropic from "@anthropic-ai/sdk";
import type { z } from "zod";

export const FAST_MODEL = process.env["FAST_MODEL"] ?? "claude-haiku-5-5";
export const SMART_MODEL = process.env["SMART_MODEL"] ?? "claude-sonnet-5-5";
export const isMock = (): boolean => process.env["LLM_MODE"] === "mock";

const PRICES: Record<string, [number, number]> = {
  [FAST_MODEL]: [Number(process.env["FAST_IN"] ?? 1), Number(process.env["FAST_OUT"] ?? 5)],
  [SMART_MODEL]: [Number(process.env["SMART_IN"] ?? 3), Number(process.env["SMART_OUT"] ?? 15)],
};

export const ledger = {
  calls: [] as { model: string; usd: number; secs: number }[],
  reset(): void { this.calls.length = 0; },
  usd(): number { return this.calls.reduce((a, c) => a + c.usd, 0); },
  secs(): number { return this.calls.reduce((a, c) => a + c.secs, 0); },
};

let client: Anthropic | undefined;

export interface StructuredOpts<T> {
  system: string;
  user: string;
  jsonSchema: Record<string, unknown>;   // JSON schema sent to the model as the forced tool
  schema: z.ZodType<T>;                  // runtime validation of what comes back
  model?: string;
  maxTokens?: number;
  mock: () => unknown;                   // deterministic stand-in for offline tests
}

/** Every model call goes through here: forced tool use -> JSON -> zod validation. One retry on bad output. */
export async function structured<T>(o: StructuredOpts<T>): Promise<T> {
  if (isMock()) return o.schema.parse(o.mock());
  const model = o.model ?? FAST_MODEL;
  client ??= new Anthropic();
  let lastErr: unknown;
  for (let attempt = 0; attempt < 2; attempt++) {
    const t0 = Date.now();
    const resp = await client.messages.create({
      model,
      max_tokens: o.maxTokens ?? 1200,
      system: o.system,
      tools: [{ name: "respond", description: "Return the structured result.", input_schema: o.jsonSchema as Anthropic.Tool.InputSchema }],
      tool_choice: { type: "tool", name: "respond" },
      messages: [{ role: "user", content: o.user }],
    });
    const [pin, pout] = PRICES[model] ?? [0, 0];
    ledger.calls.push({ model, usd: (resp.usage.input_tokens * pin + resp.usage.output_tokens * pout) / 1e6, secs: (Date.now() - t0) / 1000 });
    for (const block of resp.content) {
      if (block.type === "tool_use") {
        const parsed = o.schema.safeParse(block.input);
        if (parsed.success) return parsed.data;
        lastErr = parsed.error;
      }
    }
  }
  throw new Error(`model output failed validation: ${String(lastErr)}`);
}
