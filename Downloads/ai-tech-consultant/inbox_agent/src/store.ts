import { existsSync, readFileSync, writeFileSync, renameSync } from "node:fs";
import { CATEGORIES, type Category, type CategoryState, type State } from "./types.js";

const fresh = (): CategoryState => ({
  streak: 0, autonomy: "review", autoSentCount: 0, activeVersion: 0,
  versions: [{ v: 0, rules: [], createdAt: new Date().toISOString(), note: "initial: no learned rules" }], log: [],
});

export class Store {
  state: State;
  constructor(private readonly path: string | null = null) {
    if (path && existsSync(path)) this.state = JSON.parse(readFileSync(path, "utf8")) as State;
    else this.state = { categories: Object.fromEntries(CATEGORIES.map((c) => [c, fresh()])) as Record<Category, CategoryState>, items: {}, examples: [] };
  }
  cat(c: Category): CategoryState { return this.state.categories[c]; }
  rules(c: Category): string[] { const s = this.cat(c); return s.versions.find((v) => v.v === s.activeVersion)?.rules ?? []; }
  save(): void {
    if (!this.path) return;
    writeFileSync(`${this.path}.tmp`, JSON.stringify(this.state, null, 2));
    renameSync(`${this.path}.tmp`, this.path);       // atomic: a crash never leaves half a file
  }
}
