import { z } from "zod";

export const CATEGORIES = ["how_to", "project_request", "refund", "complaint", "quote", "followup", "account", "other"] as const;
export const CategorySchema = z.enum(CATEGORIES);
export type Category = z.infer<typeof CategorySchema>;

export const EmailSchema = z.object({
  id: z.string().min(1).max(100),
  from: z.string().email(),
  subject: z.string().max(300),
  body: z.string().max(20_000),
});
export type Email = z.infer<typeof EmailSchema>;

export const ClassificationSchema = z.object({
  category: CategorySchema,
  risk: z.enum(["low", "high"]),
  needsKnowledge: z.boolean(),
  question: z.string(),          // the product question to ask the Knowledge Brain ("" if none)
  summary: z.string(),
});
export type Classification = z.infer<typeof ClassificationSchema>;

export const BrainAnswerSchema = z.object({
  answered: z.boolean(),
  answer: z.string(),
  sources: z.array(z.object({ url: z.string(), title: z.string().nullable().optional() })),
  confidence: z.number(),
  task_id: z.number().nullable(),
});
export type BrainAnswer = z.infer<typeof BrainAnswerSchema>;

export const DraftSchema = z.object({
  body: z.string().min(1),
  confidence: z.number().min(0).max(1),
  unsupportedClaims: z.boolean(),   // model self-check: did the draft state facts not in the Brain answer?
});
export type Draft = z.infer<typeof DraftSchema>;

export type ItemStatus = "pending_review" | "reviewed" | "auto_sent";
export interface Item {
  id: string;
  email: Email;
  classification: Classification;
  brain: BrainAnswer | null;
  draft: Draft;
  playbookVersion: number;
  status: ItemStatus;
  audit: boolean;                    // auto-sent but also shown to a human as a spot check
  reasons: string[];
  finalText?: string;
  createdAt: string;
}

export interface PlaybookVersion { v: number; rules: string[]; createdAt: string; note: string }
export interface CategoryState {
  streak: number;                    // consecutive human-reviewed drafts sent unchanged
  autonomy: "review" | "auto";
  autoSentCount: number;
  activeVersion: number;
  versions: PlaybookVersion[];
  log: string[];                     // human-readable history of promotions / revocations
}
export interface Example { category: Category; itemId: string; draft: string; final: string; similarity: number }
export interface State {
  categories: Record<Category, CategoryState>;
  items: Record<string, Item>;
  examples: Example[];
}

export type FeedbackAction = "sent_as_is" | "edited" | "wrote_own" | "customer_complaint";
export const PROMOTE_AFTER = 20;     // unchanged drafts in a row before a category may auto-send
export const NEVER_AUTO: ReadonlySet<Category> = new Set<Category>(["refund", "complaint", "quote"]);
export const AUDIT_EVERY = 5;        // every 5th auto-sent email is also put in front of a human
