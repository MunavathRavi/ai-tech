import { randomUUID } from "node:crypto";
import { decide } from "./autonomy.js";
import type { Brain } from "./brain.js";
import { classify, looksLikeInjection } from "./classify.js";
import { draftReply } from "./draft.js";
import type { Store } from "./store.js";
import type { Email, Item } from "./types.js";

export interface Mailer { send(to: string, subject: string, body: string): Promise<void> }
export class OutboxMailer implements Mailer {            // stand-in for SMTP/Gmail; records what would have been sent
  readonly sent: { to: string; subject: string; body: string }[] = [];
  async send(to: string, subject: string, body: string): Promise<void> { this.sent.push({ to, subject, body }); }
}

export async function processEmail(store: Store, brain: Brain, mailer: Mailer, email: Email): Promise<Item> {
  const injection = looksLikeInjection(email);
  const cls = await classify(email);
  let brainAnswer = null;
  if (cls.needsKnowledge && cls.question && !injection) {
    try { brainAnswer = await brain.ask(cls.question); } catch { brainAnswer = null; }   // brain down -> human review, not a crash
  }
  const st = store.cat(cls.category);
  const draft = await draftReply(email, cls, brainAnswer, store.rules(cls.category));
  const d = decide(cls, brainAnswer, draft, st, injection);
  const item: Item = {
    id: randomUUID(), email, classification: cls, brain: brainAnswer, draft, playbookVersion: st.activeVersion,
    status: d.mode === "auto_send" ? "auto_sent" : "pending_review", audit: d.audit, reasons: d.reasons, createdAt: new Date().toISOString(),
  };
  store.state.items[item.id] = item;
  if (d.mode === "auto_send") { st.autoSentCount += 1; await mailer.send(email.from, `Re: ${email.subject}`, draft.body); }
  store.save();
  return item;
}
