import { z } from "zod";
import { structured, FAST_MODEL } from "./llm.js";
import { isUnchanged, similarity } from "./similarity.js";
import type { Store } from "./store.js";
import { PROMOTE_AFTER, type Category, type FeedbackAction, type Item } from "./types.js";

export interface LearnDeps {
  /** Re-draft an old email under a given rule set (used to test whether a new rule really helps). */
  redraft: (item: Item, rules: string[]) => Promise<string>;
  /** Turn one human edit into a general rule, or null if the edit was a one-off. */
  distill: (draft: string, final: string, category: Category) => Promise<string | null>;
}

const RULE_SCHEMA = {
  type: "object",
  properties: { rule: { type: ["string", "null"], description: "One general, reusable style/content rule, or null if the edit was specific to this one email" } },
  required: ["rule"],
};

export const llmDistill: LearnDeps["distill"] = async (draft, final, category) => {
  const r = await structured<{ rule: string | null }>({
    system: "You study how a human edited an AI-drafted customer reply. Extract ONE general rule that would have made the draft need no edit. Rules must be about tone, structure, wording or policy phrasing. Return null for one-off corrections.",
    user: `Category: ${category}\n\nDRAFT:\n${draft}\n\nHUMAN FINAL:\n${final}`,
    jsonSchema: RULE_SCHEMA, schema: z.object({ rule: z.string().nullable() }), model: FAST_MODEL, maxTokens: 200,
    mock: () => ({ rule: null }),
  });
  return r.rule;
};

export interface FeedbackResult { unchanged: boolean; streak: number; autonomy: "review" | "auto"; ruleAdopted: string | null; note: string }

export async function recordFeedback(store: Store, deps: LearnDeps, itemId: string, action: FeedbackAction, finalText?: string): Promise<FeedbackResult> {
  const item = store.state.items[itemId];
  if (!item) throw new Error(`unknown item ${itemId}`);
  const cat = item.classification.category;
  const st = store.cat(cat);
  const wasAuto = item.status === "auto_sent";
  let note = "";
  let ruleAdopted: string | null = null;

  if (action === "customer_complaint") {
    st.streak = 0;
    if (st.autonomy === "auto") { st.autonomy = "review"; st.log.push(`${now()} auto-send REVOKED: customer complaint on ${itemId}`); }
    note = "autonomy revoked after complaint";
    store.save();
    return { unchanged: false, streak: st.streak, autonomy: st.autonomy, ruleAdopted, note };
  }

  const final = action === "sent_as_is" ? item.draft.body : (finalText ?? "");
  if (action !== "sent_as_is" && !final.trim()) throw new Error("final text required");
  const unchanged = isUnchanged(item.draft.body, final);
  item.finalText = final; item.status = wasAuto ? "auto_sent" : "reviewed";
  store.state.examples.push({ category: cat, itemId, draft: item.draft.body, final, similarity: similarity(item.draft.body, final) });

  if (unchanged) {
    st.streak += 1;
    if (st.autonomy === "review" && st.streak >= PROMOTE_AFTER) {
      st.autonomy = "auto"; st.log.push(`${now()} auto-send GRANTED after ${st.streak} unchanged drafts`);
      note = "category promoted to auto-send";
    }
  } else {
    st.streak = 0;
    if (st.autonomy === "auto") { st.autonomy = "review"; st.log.push(`${now()} auto-send REVOKED: human changed an audited draft (${itemId})`); note = "autonomy revoked"; }
    ruleAdopted = await learnFromEdit(store, deps, cat, item, final);
  }
  store.save();
  return { unchanged, streak: st.streak, autonomy: st.autonomy, ruleAdopted, note };
}

/** A new rule is adopted only if replaying recent human-approved examples with it is not worse than without it. */
async function learnFromEdit(store: Store, deps: LearnDeps, cat: Category, item: Item, final: string): Promise<string | null> {
  const rule = await deps.distill(item.draft.body, final, cat);
  if (!rule) return null;
  const st = store.cat(cat);
  const current = store.rules(cat);
  if (current.includes(rule)) return null;
  const recent = store.state.examples.filter((e) => e.category === cat).slice(-6);
  const score = async (rules: string[]): Promise<number> => {
    const sims = await Promise.all(recent.map(async (ex) => {
      const it = store.state.items[ex.itemId];
      return it ? similarity(await deps.redraft(it, rules), ex.final) : 0;
    }));
    return sims.reduce((a, b) => a + b, 0) / Math.max(sims.length, 1);
  };
  const [before, after] = [await score(current), await score([...current, rule])];
  const v = st.versions.length;
  if (after >= before) {
    st.versions.push({ v, rules: [...current, rule], createdAt: new Date().toISOString(), note: `adopted: replay ${before.toFixed(3)} -> ${after.toFixed(3)}` });
    st.activeVersion = v;
    return rule;
  }
  st.log.push(`${now()} rule rejected (replay ${before.toFixed(3)} -> ${after.toFixed(3)}): ${rule}`);
  return null;
}

/** Undo: make an older playbook version active again. */
export function rollback(store: Store, cat: Category, version: number): void {
  const st = store.cat(cat);
  if (!st.versions.some((v) => v.v === version)) throw new Error("no such version");
  st.activeVersion = version; st.log.push(`${now()} rolled back to v${version}`); store.save();
}
const now = (): string => new Date().toISOString();
