import { AUDIT_EVERY, NEVER_AUTO, type BrainAnswer, type Category, type CategoryState, type Classification, type Draft } from "./types.js";

export interface Decision { mode: "auto_send" | "review"; audit: boolean; reasons: string[] }

/** The ONLY place that decides whether an email leaves without a human. Every gate must pass. */
export function decide(cls: Classification, brain: BrainAnswer | null, draft: Draft, st: CategoryState, injection: boolean): Decision {
  const why: string[] = [];
  if (st.autonomy !== "auto") why.push(`category "${cls.category}" not yet trusted (streak ${st.streak}/20)`);
  if (NEVER_AUTO.has(cls.category as Category)) why.push(`"${cls.category}" always needs a human`);
  if (cls.risk === "high") why.push("classified high risk");
  if (injection) why.push("possible prompt injection");
  if (cls.needsKnowledge && !brain?.answered) why.push("Knowledge Brain could not answer");
  if (draft.unsupportedClaims) why.push("draft states facts not in sources");
  if (draft.confidence < 0.8) why.push(`low draft confidence (${draft.confidence.toFixed(2)})`);
  if (why.length) return { mode: "review", audit: false, reasons: why };
  const audit = (st.autoSentCount + 1) % AUDIT_EVERY === 0;
  return { mode: "auto_send", audit, reasons: ["all gates passed"] };
}
