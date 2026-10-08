// explain.js - all the teaching text in one place.
//   STAGE_KID   : the story told to a 8th-9th grader while an animation plays
//   STAGE_INFO  : the technical version (what happened / why it matters)
//   STRATEGY_INFO / EXPANSION_INFO : shown when a dropdown changes

export const INGEST_STEPS = ["load", "chunk", "embed", "store"];
export const QUERY_STEPS = ["query", "tool_call", "expand", "prefilter", "dense", "bm25", "fuse",
                            "postfilter", "rerank", "prompt", "answer", "reflect"];

// Which of the four big pipeline cards each stage belongs to.
export const STAGE_BOX = {
  load: "ingest", chunk: "ingest", embed: "ingest", store: "ingest",
  query: "retrieve", expand: "retrieve", prefilter: "retrieve", dense: "retrieve", bm25: "retrieve",
  fuse: "retrieve", postfilter: "retrieve", rerank: "retrieve",
  tool_call: "generate", prompt: "generate", answer: "generate", reflect: "generate", retry: "generate",
  eval: "evaluate", eval_summary: "evaluate",
};

export const STAGE_LABEL = {
  load: "Load", chunk: "Chunk", embed: "Embed", store: "Store",
  query: "Query", tool_call: "Tool call", expand: "Expand", prefilter: "Pre-filter", dense: "Dense",
  bm25: "BM25", fuse: "Fuse (RRF)", postfilter: "Post-filter", rerank: "Re-rank", prompt: "Prompt",
  answer: "Answer", reflect: "Reflect",
};

export const STAGE_ICON = {
  load: "📄", chunk: "✂️", embed: "🔢", store: "🗄️", query: "💬", tool_call: "🕵️", expand: "🔀",
  prefilter: "🗂️", dense: "🧭", bm25: "🔤", fuse: "🤝", postfilter: "🧹", rerank: "⚖️",
  prompt: "✉️", answer: "✍️", reflect: "✅",
};

// ---- the kid-friendly story ------------------------------------------------------------
export const STAGE_KID = {
  load: { title: "Opening the file",
          kid: "The computer opens your file and reads every word - just like you reading a book." },
  chunk: { title: "Cutting it into flash cards",
           kid: "A long file is too big to search all at once. So we cut it into small flash cards called chunks. Neighbouring cards share a few words (the glowing strip) so no sentence gets chopped in half!" },
  embed: { title: "Giving every card a secret number code",
           kid: "Computers can't 'understand' words, but they love numbers. So every card gets a fingerprint made of numbers that captures its MEANING. Cards about similar things get similar fingerprints." },
  store: { title: "Locking the cards in the locker room",
           kid: "All the fingerprints are saved in Pinecone, a giant online locker room. Each card is stored with a label (which file, which department) so we can find it later." },
  query: { title: "Your question arrives",
           kid: "Here is your question. Now the big puzzle: which cards hold the answer?" },
  tool_call: { title: "The detective plans the search",
               kid: "An AI detective cleans up your question and decides which shelf (department) to look on. Careful - if it picks the wrong shelf, the answer might not be there!" },
  expand: { title: "Asking in more than one way",
            kid: "Sometimes the book uses different words than you do. So the AI helps by asking again in other ways." },
  prefilter: { title: "Closing the wrong shelves",
               kid: "Before searching, we close the shelves that can't have the answer. Less to search means faster results and fewer silly mistakes." },
  dense: { title: "Searching by MEANING",
           kid: "Your question gets its own fingerprint too. We look for the cards whose fingerprints are closest - like finding the nearest dots on a map. This finds the same meaning even when the words are different." },
  bm25: { title: "Searching by exact WORDS",
          kid: "Now a second helper hunts for the exact words, like pressing Ctrl+F. Rare words are worth more points than common ones - 'the' is worth almost nothing, 'SIM-swap' is worth a lot!" },
  fuse: { title: "Merging the two lists fairly",
          kid: "Two helpers gave two different lists. We give every card points for each list it appears in (higher spot = more points). Cards that BOTH helpers like float to the top." },
  postfilter: { title: "Throwing away weak cards",
                kid: "Cards that barely match, or that repeat each other, are dropped. We keep the strong ones so the next judge has less to read." },
  rerank: { title: "The judge re-ranks the cards",
            kid: "A strict judge reads your question and each card TOGETHER, then gives marks for how well the card really answers it. Cards are re-ordered by those marks - the best go to the top, and only the top few are kept." },
  prompt: { title: "Packing the letter for the AI writer",
            kid: "The best cards and your question are packed into one letter for the AI writer. This letter is ALL the AI will read - it must not use anything else." },
  answer: { title: "The AI writes the answer",
            kid: "The AI writes the answer using only those cards, and marks which card each fact came from, like [1]." },
  reflect: { title: "The AI checks its own homework",
             kid: "Last step: is every sentence of the answer really backed up by the cards? If not, the AI tries once more with better search words." },
  retry: { title: "Trying again", kid: "That answer wasn't fully backed up, so the AI tries again with new search words." },
  final: { title: "Done!", kid: "All finished. Look at the answer below - and the cards it came from." },
};

// What the animated stage says while the computer is still working.
export const WORKING = {
  load: "Reading the file…", chunk: "Cutting the text into cards…", embed: "Making number fingerprints…",
  store: "Putting cards in the Pinecone locker room…", tool_call: "The detective is thinking (an AI call, a few seconds)…",
  expand: "The AI is thinking of other ways to ask…", dense: "Asking Pinecone for the nearest cards…",
  bm25: "Counting matching words…", rerank: "The judge is reading every card…", answer: "The AI is writing…",
  reflect: "The AI is checking its homework…",
};

// ---- technical version (what / why) ----------------------------------------------------
export const STAGE_INFO = {
  load: { what: "The file was read and turned into plain text (a PDF gives one text per page).",
          why: "Every later stage works on text, so the file format never matters again." },
  chunk: { what: "The text was cut into chunks. Yellow text at the top of a card is the overlap shared with the previous chunk.",
           why: "One embedding per small, focused chunk is far more searchable than one blurry vector per document." },
  embed: { what: "Each chunk became a vector of numbers (1536 with OpenAI's text-embedding-3-small).",
           why: "Texts with similar meaning get vectors that point in similar directions - that's what dense search uses." },
  store: { what: "Vectors + metadata were upserted to Pinecone, and we waited until Pinecone could search them.",
           why: "Pinecone is eventually consistent: an upsert returns at once, the vectors become searchable a moment later." },
  query: { what: "Your question entered the pipeline.", why: "Nothing is searched yet - first the LLM decides HOW to search." },
  tool_call: { what: "The LLM called search_knowledge_base(...) with a cleaner query and optional filters.",
               why: "Messy questions make poor queries. Tool calling lets the LLM plan the search, and Pydantic validates its arguments." },
  expand: { what: "The LLM generated extra search inputs (MQE: more phrasings, HyDE: a hypothetical answer).",
            why: "One query is one shot. Expansion gives retrieval several shots at the same question." },
  prefilter: { what: "Metadata filters were set BEFORE searching (Pinecone filter + the same rule for BM25).",
               why: "Searching only the right department is cheaper and avoids look-alike chunks from elsewhere." },
  dense: { what: "Each query was embedded and Pinecone returned the nearest chunk vectors (cosine similarity).",
           why: "Dense search matches MEANING: 'time off' finds 'annual leave' even with no shared words." },
  bm25: { what: "Every chunk was scored by shared keywords. Highlighted words are the query terms BM25 matched.",
          why: "BM25 matches exact WORDS: rare terms like 'SIM-swap' or '4400' score high. It has no idea of synonyms." },
  fuse: { what: "Reciprocal Rank Fusion merged the ranked lists: score = sum of 1 / (60 + rank) over every list.",
          why: "Dense and BM25 scores live on different scales, so we combine RANKS. Chunks near the top of several lists win." },
  postfilter: { what: "Weak matches (low cosine AND no keyword overlap) and near-duplicates were dropped, then capped.",
                why: "Cleaning AFTER the search keeps the slower re-ranker's job small." },
  rerank: { what: "A cross-encoder read (question, chunk) pairs together and re-ordered the survivors.",
            why: "Search encodes query and chunk separately (fast, rough). The cross-encoder reads them together (slow, precise)." },
  prompt: { what: "The top chunks were numbered and placed into the prompt with the question.",
            why: "This exact text is all the LLM sees. Most wrong answers become obvious when you read it." },
  answer: { what: "The answer model wrote a reply citing passages like [1].",
            why: "Citations let a human - and the reflection step - check every claim." },
  reflect: { what: "A second LLM call checked whether every claim is supported by the chunks.",
             why: "If not grounded, the pipeline retries once with a rewritten query instead of trusting a hallucination." },
};

// One short line about what the NEXT step will do (shown before clicking).
export const NEXT_PREVIEW = {
  load: "read the next file into plain text", chunk: "cut the text into flash cards",
  embed: "give every card a number fingerprint", store: "lock the fingerprints in Pinecone",
  tool_call: "the AI detective plans the search", expand: "the AI asks the question in other ways",
  prefilter: "close the wrong shelves", dense: "search by meaning (nearest fingerprints)",
  bm25: "search by exact words", fuse: "merge the lists fairly", postfilter: "throw away weak cards",
  rerank: "the judge re-orders the cards", prompt: "pack the best cards into a letter",
  answer: "the AI writes a cited answer", reflect: "the AI checks its own homework",
};

export const STRATEGY_INFO = {
  dense: { title: "Dense (semantic) search",
           text: "Embeds the query and asks Pinecone for the nearest chunk vectors. Great with synonyms and paraphrases; weak on exact codes, names and numbers." },
  bm25: { title: "BM25 (keyword) search",
          text: "Scores chunks by shared words, rewarding rare words most. Great for exact terms ('SIM-swap', 'extension 4400'); blind to synonyms." },
  hybrid: { title: "Hybrid: dense + BM25 with RRF",
            text: "Runs both searches and merges the two ranked lists with Reciprocal Rank Fusion. Chunks that BOTH methods like rise to the top." },
  hybrid_expansion: { title: "Hybrid + query expansion",
                      text: "First the LLM expands the query (MQE or HyDE), then hybrid search runs on every version and RRF fuses all the lists." },
};

export const EXPANSION_INFO = {
  mqe: { title: "MQE - Multi-Query Expansion",
         text: "The LLM writes 3 more phrasings of your question. Each is searched with dense + BM25, giving up to 8 lists to fuse. Higher recall, more searches." },
  hyde: { title: "HyDE - Hypothetical Document Embeddings",
          text: "The LLM writes a fake answer passage; dense search uses ITS embedding (answer-shaped text lands near answer-shaped chunks). BM25 keeps your real words." },
};

// Which stages actually run for a strategy (used to predict "next step").
export function activeQuerySteps(strategy) {
  return QUERY_STEPS.filter((s) => {
    if (s === "expand") return strategy === "hybrid_expansion";
    if (s === "dense") return strategy !== "bm25";
    if (s === "bm25") return strategy !== "dense";
    if (s === "fuse") return strategy === "hybrid" || strategy === "hybrid_expansion";
    return true;
  });
}

export const DEPT_COLOR = { hr: "#7c3aed", it: "#0891b2", finance: "#d97706", product: "#e11d48", general: "#059669" };
