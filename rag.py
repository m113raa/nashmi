"""
rag.py - Arabic RAG core (Ollama + command-r7b-arabic + bge-m3), hybrid search, ID lookup tool.

Commands:
  python rag.py ingest [data_dir]   build the index from every .md/.txt/.csv/.json/.pdf/.docx in data_dir
  python rag.py ask "سؤالك"         ask one question in the terminal
  python rag.py eval                run data/eval_questions.json and print a score
UI:   streamlit run ui.py

Offline dev mode (no Ollama needed, for UI work):  set RAG_FAKE=1
"""
import csv, glob, hashlib, json, math, os, pickle, re, sys
from collections import Counter

import numpy as np

LLM_MODEL = os.getenv("LLM_MODEL", "command-r7b-arabic")
EMB_MODEL = os.getenv("EMB_MODEL", "bge-m3")
DATA_DIR = os.getenv("DATA_DIR", "data")
INDEX_PATH = os.getenv("INDEX_PATH", "index.pkl")
TOP_K = int(os.getenv("TOP_K", "6"))
FAKE = os.getenv("RAG_FAKE") == "1"

# ------------------------------------------------------------------ 1. Arabic normalization
_DIACRITICS = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ]")  # tashkeel + tatweel


def normalize(text: str) -> str:
    """Make Arabic spelling variants match: أإآ->ا, ى->ي, ة->ه, ؤ->و, ئ->ي, strip diacritics, Arabic digits->latin."""
    t = _DIACRITICS.sub("", str(text))
    t = re.sub("[إأآٱ]", "ا", t).replace("ى", "ي").replace("ة", "ه").replace("ؤ", "و").replace("ئ", "ي")
    t = t.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
    return t.lower()


STOP = set(normalize(w) for w in """في من على الى إلى عن ما ماذا متى كم هل هو هي هذا هذه ان أن او أو و ثم
شو قديش وين ليش كيف بدي اللي الذي التي يا مع كل بعد قبل لا لم لن""".split())


def tokenize(text):
    return [w for w in re.findall(r"[\w]+", normalize(text)) if w not in STOP and len(w) > 1]


# ------------------------------------------------------------------ 2. Loading + chunking
def chunk_markdown(text, source, max_chars=1200):
    """Split on headings so each chunk is one topic; keep the doc title on every chunk for context."""
    title = next((l.lstrip("# ").strip() for l in text.splitlines() if l.startswith("# ")), source)
    parts = re.split(r"\n(?=##\s)", text)
    chunks = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        body = p if p.startswith("# ") else f"{title}\n{p}"
        for i in range(0, len(body), max_chars):  # hard cap for very long sections
            chunks.append({"text": body[i:i + max_chars], "source": source, "kind": "doc"})
    return chunks


def row_to_text(row: dict) -> str:
    """Generic: works for ANY table they hand you. 'column: value' lines read well for LLMs."""
    return "\n".join(f"{k}: {v}" for k, v in row.items() if str(v).strip())


def load_table_rows(path):
    if path.endswith(".csv"):
        with open(path, encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) and data and isinstance(data[0], dict) else None


def load_documents(data_dir=DATA_DIR):
    chunks, records = [], []
    for path in sorted(glob.glob(os.path.join(data_dir, "**", "*"), recursive=True)):
        name = os.path.relpath(path, data_dir)
        if os.path.isdir(path) or os.path.basename(path).startswith("eval_"):
            continue
        ext = path.lower().rsplit(".", 1)[-1]
        try:
            if ext in ("md", "txt"):
                chunks += chunk_markdown(open(path, encoding="utf-8").read(), name)
            elif ext in ("csv", "json"):
                if ext == "json" and os.path.exists(path[:-5] + ".csv"):
                    continue  # same table already loaded from CSV
                rows = load_table_rows(path)
                if rows is None:  # JSON that isn't a table: index it as text
                    chunks += chunk_markdown(open(path, encoding="utf-8").read(), name)
                    continue
                for i, r in enumerate(rows):
                    chunks.append({"text": f"[{name} سجل {i+1}]\n" + row_to_text(r), "source": name, "kind": "row"})
                    records.append({"source": name, **r})
            elif ext == "pdf":
                from pypdf import PdfReader
                text = "\n".join((pg.extract_text() or "") for pg in PdfReader(path).pages)
                chunks += chunk_markdown(text, name)
            elif ext == "docx":
                import docx
                text = "\n".join(p.text for p in docx.Document(path).paragraphs)
                chunks += chunk_markdown(text, name)
        except Exception as e:
            print(f"!! skipped {name}: {e}")
    return chunks, records


# ------------------------------------------------------------------ 3. Embeddings
def embed(texts, batch=32):
    if FAKE:  # hashed bag-of-words, only for offline UI development
        out = np.zeros((len(texts), 512), dtype=np.float32)
        for i, t in enumerate(texts):
            for w in tokenize(t):
                out[i, int(hashlib.md5(w.encode()).hexdigest(), 16) % 512] += 1
    else:
        import ollama
        vecs = []
        for i in range(0, len(texts), batch):
            vecs += ollama.embed(model=EMB_MODEL, input=texts[i:i + batch])["embeddings"]
            print(f"\r  embedded {min(i + batch, len(texts))}/{len(texts)}", end="", flush=True)
        print()
        out = np.array(vecs, dtype=np.float32)
    out /= (np.linalg.norm(out, axis=1, keepdims=True) + 1e-9)
    return out


# ------------------------------------------------------------------ 4. BM25 (keyword search: names, IDs, exact terms)
class BM25:
    def __init__(self, docs_tokens, k1=1.5, b=0.75):
        self.k1, self.b = k1, b
        self.docs = [Counter(d) for d in docs_tokens]
        self.lens = np.array([len(d) for d in docs_tokens], dtype=np.float32)
        self.avg = float(self.lens.mean()) if len(self.lens) else 1.0
        df = Counter(w for d in self.docs for w in d)
        n = len(self.docs)
        self.idf = {w: math.log(1 + (n - c + 0.5) / (c + 0.5)) for w, c in df.items()}
        self.inv = {}
        for i, d in enumerate(self.docs):
            for w in d:
                self.inv.setdefault(w, []).append(i)

    def scores(self, q_tokens):
        s = np.zeros(len(self.docs), dtype=np.float32)
        for w in set(q_tokens):
            for i in self.inv.get(w, []):
                tf = self.docs[i][w]
                s[i] += self.idf[w] * tf * (self.k1 + 1) / (tf + self.k1 * (1 - self.b + self.b * self.lens[i] / self.avg))
        return s


# ------------------------------------------------------------------ 5. Index build / load
def build_index(data_dir=DATA_DIR, path=INDEX_PATH):
    chunks, records = load_documents(data_dir)
    print(f"loaded {len(chunks)} chunks, {len(records)} table rows from {data_dir}")
    vecs = embed([c["text"] for c in chunks])
    with open(path, "wb") as f:
        pickle.dump({"chunks": chunks, "records": records, "vecs": vecs, "emb_model": "fake" if FAKE else EMB_MODEL}, f)
    print(f"index saved -> {path}")


class Retriever:
    def __init__(self, path=INDEX_PATH):
        with open(path, "rb") as f:
            d = pickle.load(f)
        self.chunks, self.records, self.vecs = d["chunks"], d["records"], d["vecs"]
        self.bm25 = BM25([tokenize(c["text"]) for c in self.chunks])
        self.by_id = {}  # exact lookup on any column that looks like an ID
        for r in self.records:
            for k, v in r.items():
                is_id_col = "id" in k.lower() or k == "family_book_no" or "رقم" in k
                if is_id_col and re.fullmatch(r"\d{6,}|FB\d+", str(v)):
                    self.by_id.setdefault(str(v), []).append(r)

    def search(self, query, k=TOP_K):
        """Hybrid = semantic (meaning) + BM25 (exact words), merged with Reciprocal Rank Fusion."""
        dense = self.vecs @ embed([query])[0]
        sparse = self.bm25.scores(tokenize(query))
        rrf = np.zeros(len(self.chunks))
        for scores in (dense, sparse):
            for rank, i in enumerate(np.argsort(-scores)[:50]):
                if scores[i] > 0:
                    rrf[i] += 1 / (60 + rank)
        return [self.chunks[i] for i in np.argsort(-rrf)[:k] if rrf[i] > 0]

    def lookup_ids(self, query):
        """'Agent tool': if the question has a national ID / family book no, fetch the record + linked people."""
        hits = []
        for token in re.findall(r"FB\d+|\d{6,}", normalize(query).upper()):
            for r in self.by_id.get(token, []):
                if r not in hits:
                    hits.append(r)
        # follow links one hop (spouse, father, mother) so "who is X's wife" works
        for r in list(hits):
            for k in ("spouse_id", "father_id", "mother_id"):
                for linked in self.by_id.get(str(r.get(k, "")), []):
                    if linked not in hits and str(linked.get("national_id")) == str(r.get(k)):
                        hits.append(linked)
        return hits[:8]


# ------------------------------------------------------------------ 6. Generation
SYSTEM_PROMPT = """أنت مساعد ذكي لدائرة الأحوال المدنية. أجب باللغة العربية الفصحى المبسطة.
القواعد:
1. أجب فقط من المعلومات الموجودة في "السياق" أدناه. لا تخترع أي رقم أو رسوم أو تاريخ.
2. إذا لم تجد الإجابة في السياق قل: "عذراً، لا تتوفر لدي هذه المعلومة." ولا تحاول التخمين.
3. اذكر رقم المصدر بين قوسين مربعين بعد المعلومة، مثل [1].
4. كن مختصراً وواضحاً، واستخدم نقاطاً عند ذكر الوثائق المطلوبة.
5. إذا كتب المستخدم باللهجة العامية افهمها وأجب بالفصحى المبسطة."""


def build_context(chunks, records):
    parts = []
    for r in records:
        parts.append(f"[{len(parts)+1}] (سجل مطابق تماماً للرقم المذكور)\n" + row_to_text(r))
    for c in chunks:
        parts.append(f"[{len(parts)+1}] (المصدر: {c['source']})\n{c['text']}")
    return "\n\n".join(parts)


def answer(retriever, question, history=None, stream=False):
    records = retriever.lookup_ids(question)
    chunks = retriever.search(question)
    context = build_context(chunks, records)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages += (history or [])[-6:]  # last 3 turns for follow-up questions
    messages.append({"role": "user", "content": f"السياق:\n{context}\n\nالسؤال: {question}"})
    sources = [f"سجل {r.get('national_id', '')}" for r in records] + [c["source"] for c in chunks]

    if FAKE:
        text = "[وضع تجريبي بدون نموذج] أقرب نتيجة:\n" + (context.split("\n\n")[0] if context else "لا يوجد سياق")
        return (iter([text]) if stream else text), sources, context

    import ollama
    opts = {"temperature": 0.1, "num_ctx": 8192}
    if stream:
        gen = (p["message"]["content"] for p in ollama.chat(model=LLM_MODEL, messages=messages, stream=True, options=opts))
        return gen, sources, context
    out = ollama.chat(model=LLM_MODEL, messages=messages, options=opts)["message"]["content"]
    return out, sources, context


# ------------------------------------------------------------------ 7. CLI + eval
def run_eval(retriever, path=os.path.join(DATA_DIR, "eval_questions.json")):
    qs = json.load(open(path, encoding="utf-8"))
    hit = 0
    for q in qs:
        out, sources, ctx = answer(retriever, q["q"])
        expected_in_ctx = q["source"] == "none" or any(s.startswith(q["source"]) or q["source"] in s for s in sources) \
            or normalize(q["a"])[:12] in normalize(ctx)
        hit += expected_in_ctx
        print(f"\nQ: {q['q']}\n  expected: {q['a']}\n  got: {str(out)[:300]}\n  retrieval {'OK' if expected_in_ctx else 'MISS'}")
    print(f"\nretrieval hit-rate: {hit}/{len(qs)}  (read the answers yourself to judge correctness)")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    if cmd == "ingest":
        build_index(sys.argv[2] if len(sys.argv) > 2 else DATA_DIR)
    elif cmd == "ask":
        out, src, _ = answer(Retriever(), " ".join(sys.argv[2:]))
        print(out, "\n\nsources:", src)
    elif cmd == "eval":
        run_eval(Retriever())
    else:
        print(__doc__)
