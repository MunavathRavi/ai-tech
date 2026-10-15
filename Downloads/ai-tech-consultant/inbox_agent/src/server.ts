import express from "express";
import { z } from "zod";
import { HttpBrain } from "./brain.js";
import { draftReply } from "./draft.js";
import { SMART_MODEL } from "./llm.js";
import { llmDistill, recordFeedback, rollback, type LearnDeps } from "./learning.js";
import { OutboxMailer, processEmail, type Mailer } from "./pipeline.js";
import { Store } from "./store.js";
import { CategorySchema, EmailSchema, type Item } from "./types.js";

const store = new Store(process.env["STATE_FILE"] ?? "data/state.json");
const brain = new HttpBrain();
const mailer: Mailer = new OutboxMailer();
const deps: LearnDeps = {
  distill: llmDistill,
  redraft: async (item: Item, rules: string[]) => (await draftReply(item.email, item.classification, item.brain, rules, SMART_MODEL)).body,
};

const app = express();
app.use(express.json({ limit: "100kb" }));
const wrap = (fn: express.RequestHandler): express.RequestHandler => (req, res, next) => { Promise.resolve(fn(req, res, next)).catch(next); };

app.get("/health", (_q, r) => r.json({ ok: true }));
app.post("/emails", wrap(async (req, res) => {
  const email = EmailSchema.safeParse(req.body);
  if (!email.success) { res.status(400).json({ error: email.error.flatten() }); return; }
  res.status(201).json(await processEmail(store, brain, mailer, email.data));
}));
app.get("/queue", (_q, r) => r.json(Object.values(store.state.items).filter((i) => i.status === "pending_review" || i.audit)));
app.post("/emails/:id/feedback", wrap(async (req, res) => {
  const body = z.object({ action: z.enum(["sent_as_is", "edited", "wrote_own", "customer_complaint"]), finalText: z.string().max(20_000).optional() }).safeParse(req.body);
  if (!body.success) { res.status(400).json({ error: body.error.flatten() }); return; }
  const id = req.params["id"] ?? "";
  if (!store.state.items[id]) { res.status(404).json({ error: "unknown email id" }); return; }
  res.json(await recordFeedback(store, deps, id, body.data.action, body.data.finalText));
}));
app.get("/categories", (_q, r) => r.json(store.state.categories));
app.post("/categories/:c/rollback", (req, res) => {
  const c = CategorySchema.safeParse(req.params["c"]); const v = z.number().int().safeParse(req.body?.version);
  if (!c.success || !v.success) { res.status(400).json({ error: "bad category or version" }); return; }
  rollback(store, c.data, v.data); res.json({ ok: true });
});
app.use((err: unknown, _q: express.Request, res: express.Response, _n: express.NextFunction) => { console.error(err); res.status(500).json({ error: "internal error" }); });

const port = Number(process.env["PORT"] ?? 8002);
app.listen(port, () => console.log(`Inbox Agent on :${port}  (model: ${SMART_MODEL})`));
