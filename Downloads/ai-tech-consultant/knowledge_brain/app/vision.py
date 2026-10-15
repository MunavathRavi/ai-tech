"""Screenshots often carry the answer (button names, menu paths). Caption each one with Claude vision
and index the caption next to the article it belongs to. Captions are cached by image URL."""
from . import config, llm
from .crawler import PoliteFetcher
from .db import DB

SCHEMA = {"type": "object", "properties": {
    "caption": {"type": "string", "description": "What the screenshot shows: screen/page name, key UI labels, settings and values visible, and what the reader is meant to do."},
    "useful": {"type": "boolean", "description": "False if decorative (banner, avatar, logo)."}},
    "required": ["caption", "useful"]}

SYSTEM = ("You describe help-center screenshots so a search index can answer questions about them. "
          "Transcribe visible menu names, button labels and setting values exactly. No speculation.")

async def caption_images(db: DB, fetcher: PoliteFetcher, page_url: str, title: str, images: list[dict]) -> list[str]:
    out: list[str] = []
    for im in images[: config.MAX_IMAGES_PER_PAGE]:
        row = db.rows("SELECT caption FROM images WHERE src=?", (im["src"],))
        if row and row[0]["caption"] is not None:
            cap = row[0]["caption"]
        else:
            cap = ""
            try:
                r = await fetcher.get(im["src"])
                ctype = r.headers.get("content-type", "image/png").split(";")[0]
                if r.status_code == 200 and ctype.startswith("image/") and len(r.content) < 5_000_000:
                    res = llm.structured(
                        SYSTEM, f"Article: {title}\nAlt text: {im['alt'] or '(none)'}\nDescribe this screenshot.",
                        SCHEMA, images=[(ctype, r.content)], max_tokens=400,
                        mock=lambda: {"caption": f"Screenshot for '{title}'. {im['alt']}".strip(), "useful": True})
                    cap = res["caption"] if res.get("useful") else ""
            except Exception as e:  # one bad image must never kill a page
                cap = ""
            db.run("INSERT OR REPLACE INTO images(src,page_url,alt,caption) VALUES(?,?,?,?)",
                   (im["src"], page_url, im["alt"], cap))
        if cap: out.append(f"[Screenshot in article '{title}'] {cap}")
    return out
