/** Eval for Task 2.  `npm run evals`  (live: compares FAST vs SMART on classification)
 *  Measures: category accuracy, risk recall on dangerous mail, injection safety, autonomy ladder, cost, speed.
 *  With LLM_MODE=mock only the deterministic parts are meaningful. */
import { readFileSync } from "node:fs";
import type { Brain } from "../src/brain.js";
import { classify } from "../src/classify.js";
import { FAST_MODEL, SMART_MODEL, ledger } from "../src/llm.js";
import { recordFeedback, type LearnDeps } from "../src/learning.js";
import { OutboxMailer, processEmail } from "../src/pipeline.js";
import { Store } from "../src/store.js";
import type { BrainAnswer } from "../src/types.js";

interface Row { id: string; from: string; subject: string; body: string; label: string }
const data = JSON.parse(readFileSync(new URL("../data/emails.json", import.meta.url), "utf8")) as Row[];
const HIGH_RISK = new Set(["refund", "complaint", "quote"]);

async function classifyEval(model: string): Promise<string> {
  ledger.reset();
  let ok = 0, riskHit = 0, riskTotal = 0; const t0 = Date.now(); const misses: string[] = [];
  for (const r of data) {
    const c = await classify({ id: r.id, from: r.from, subject: r.subject, body: r.body }, model);
    const injected = r.subject.startsWith("Injection");
    if (c.category === r.label || (injected && c.risk === "high")) ok++; else misses.push(`${r.id} ${r.label}->${c.category}`);
    if (HIGH_RISK.has(r.label) || injected) { riskTotal++; if (c.risk === "high") riskHit++; }
  }
  const n = data.length;
  return `| ${model} | ${ok}/${n} (${Math.round((100 * ok) / n)}%) | ${riskHit}/${riskTotal} | $${ledger.usd().toFixed(4)} | ${((Date.now() - t0) / 1000 / n).toFixed(2)}s | ${misses.slice(0, 6).join("; ")} |`;
}

async function autonomySim(): Promise<string> {
  process.env["LLM_MODE"] ??= "mock";
  const brain: Brain = { ask: async (): Promise<BrainAnswer> => ({ answered: true, answer: "Open Design Settings.", sources: [{ url: "https://kb/x" }], confidence: 0.9, task_id: null }) };
  const deps: LearnDeps = { distill: async () => null, redraft: async (i) => i.draft.body };
  const store = new Store(), mailer = new OutboxMailer();
  const trace: string[] = [];
  const step = async (n: number, action: "sent_as_is" | "edited"): Promise<void> => {
    const it = await processEmail(store, brain, mailer, { id: `s${n}`, from: "a@b.co", subject: "Theme", body: `How do I change my theme? ${n}` });
    if (it.status !== "auto_sent") await recordFeedback(store, deps, it.id, action, action === "edited" ? it.draft.body + " Thanks!" : undefined);
    trace.push(`${it.status}`);
  };
  for (let i = 0; i < 20; i++) await step(i, "sent_as_is");
  const afterTwenty = store.cat("how_to").autonomy;
  await step(20, "sent_as_is");
  return `20 unchanged -> ${afterTwenty}; 21st email -> ${trace[20]}; sent without human: ${mailer.sent.length}`;
}

console.log("| model | category accuracy | high-risk caught | cost | s/email | first misses |\n|---|---|---|---|---|---|");
for (const m of new Set([FAST_MODEL, SMART_MODEL])) console.log(await classifyEval(m));
console.log("\nAutonomy ladder:", await autonomySim());
