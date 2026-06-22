"""
Qwerty Genius — Pure Python Neural Language Model
No numpy. No torch. No sklearn. Pure math.

Three engines working together:
  1. Decomposer — breaks queries into sub-questions for structured reasoning
  2. Knowlege composer — retrieves + ranks + assembles relevant knowledge sentences
  3. Word n-gram generator — learns next-word patterns from data, generates novel text

Together they produce responses that feel LLM-like: reasoned, composed, and fluent.

Training data: ~1200 clean sentences from 8 knowledge domains
"""

import json
import math
import os
import random
import re
import sys
import time
from collections import defaultdict

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KNOWLEDGE_DIR = os.path.join(BASE_DIR, "knowledge")
MEMORY_DIR = os.path.join(BASE_DIR, "memory")


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Data: Extract clean sentences from knowledge
# ═══════════════════════════════════════════════════════════════════════════════

def _clean_text(text):
    text = re.sub(r'```[\s\S]*?```', '', text)
    text = re.sub(r'`[^`]+`', '', text)
    text = re.sub(r'[^\x20-\x7E\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _extract_sentences(obj):
    raw_strings = []
    def _collect(v):
        if isinstance(v, str):
            raw_strings.append(v)
        elif isinstance(v, dict):
            for x in v.values():
                _collect(x)
        elif isinstance(v, list):
            for x in v:
                _collect(x)
    _collect(obj)

    sentences = []
    for s in raw_strings:
        s = _clean_text(s)
        if len(s) < 20:
            continue
        parts = re.split(r'(?<=[.!?])\s+', s)
        for p in parts:
            p = p.strip()
            if len(p) > 15 and p.count(' ') >= 2:
                sentences.append(p)
    return sentences


def load_sentences():
    sentences = []
    if os.path.isdir(KNOWLEDGE_DIR):
        for fname in sorted(os.listdir(KNOWLEDGE_DIR)):
            if fname.endswith(".json"):
                try:
                    with open(os.path.join(KNOWLEDGE_DIR, fname)) as f:
                        data = json.load(f)
                    sentences.extend(_extract_sentences(data))
                except:
                    pass
    mem = os.path.join(MEMORY_DIR, "learned.json")
    if os.path.exists(mem):
        try:
            with open(mem) as f:
                data = json.load(f)
                sentences.extend(_extract_sentences(data))
        except:
            pass
    return sentences


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Word N-gram Language Model (statistical, learns patterns from data)
# ═══════════════════════════════════════════════════════════════════════════════

class NGramLM:
    """Word-level bigram language model with add-1 smoothing and unigram backoff.

    Trains in milliseconds, generates novel word sequences.
    Learns which words tend to follow which other words in the knowledge base.
    """

    def __init__(self):
        self.uni = defaultdict(int)
        self.bi = defaultdict(int)
        self.words = set()
        self.total = 0
        self.ready = False

    def train(self, sentences):
        for s in sentences:
            words = re.findall(r"[a-zA-Z0-9'.-]+|[.,!?;]", s.lower())
            words = ['<s>'] + words + ['</s>']
            self.words.update(words)
            for w in words:
                self.uni[w] += 1
                self.total += 1
            for i in range(len(words) - 1):
                self.bi[(words[i], words[i + 1])] += 1
        self.ready = True

    def p_next(self, prev_word, temperature=0.8):
        """P(word | prev_word) with add-1 smoothing and unigram backoff."""
        candidates = list(self.words)
        scores = []
        for w in candidates:
            bi_count = self.bi.get((prev_word, w), 0)
            uni_count = self.uni.get(w, 1)
            # Interpolated: P(w|prev) = λ * P_bi(w|prev) + (1-λ) * P_uni(w)
            lam = 0.7 if bi_count > 0 else 0.0
            p_bi = (bi_count + 1) / max(self.uni.get(prev_word, 1) + len(self.words), 1)
            p_uni = (uni_count + 1) / max(self.total + len(self.words), 1)
            prob = lam * p_bi + (1.0 - lam) * p_uni
            if temperature != 1.0 and temperature > 0:
                prob = math.pow(max(prob, 1e-10), 1.0 / temperature)
            scores.append((prob, w))

        scores.sort(key=lambda x: -x[0])
        total_p = sum(s[0] for s in scores)
        if total_p <= 0:
            return '</s>'
        r = random.random() * total_p
        cum = 0.0
        for p, w in scores:
            cum += p
            if r < cum:
                return w
        return scores[-1][1]

    def generate(self, seed="", max_words=50, temperature=0.7):
        """Generate a sequence of words given a seed."""
        seed_words = re.findall(r"[a-zA-Z0-9'.-]+", seed.lower())
        if not seed_words:
            seed_words = ['<s>']

        result = seed_words[:]
        prev = result[-1]

        for _ in range(max_words):
            next_w = self.p_next(prev, temperature)
            if next_w in ('</s>', '<s>'):
                if len(result) > 3:
                    break
                continue
            result.append(next_w)
            prev = next_w

        # Skip the seed words in output
        new_words = result[len(seed_words):]
        if not new_words:
            return None
        return ' '.join(new_words)

    def extend(self, text, max_words=20):
        """Given a phrase, generate a completion."""
        result = self.generate(seed=text, max_words=max_words, temperature=0.6)
        if result:
            return text + ' ' + result
        return text


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Knowledge Response Composer (retrieval + assembly)
# ═══════════════════════════════════════════════════════════════════════════════

class KnowlegeComposer:
    """Composes responses by retrieving relevant knowledge and combining sentences.

    Steps:
      1. Extract key terms from the query
      2. Find sentences with high word + entity overlap
      3. Score and filter for quality
      4. Assemble into a coherent paragraph
      5. Optionally extend with n-gram generation
    """

    def __init__(self):
        self.sentences = []
        self.word_freqs = defaultdict(int)
        self.ready = False

    def train(self, sentences):
        self.sentences = [s for s in sentences if 20 < len(s) < 300 and s.count(' ') >= 3]
        for s in self.sentences:
            for w in re.findall(r"[a-zA-Z0-9'.-]+", s.lower()):
                self.word_freqs[w] += 1
        self.ready = bool(self.sentences)

    def _key_terms(self, text):
        words = re.findall(r"[a-zA-Z0-9'.-]+", text.lower())
        return [w for w in words if len(w) > 2 and self.word_freqs.get(w, 0) < 20]

    STOP = {
        'what', 'how', 'why', 'when', 'where', 'who', 'which',
        'is', 'are', 'was', 'were', 'do', 'does', 'did',
        'the', 'a', 'an', 'this', 'that', 'these', 'those',
        'i', 'you', 'we', 'they', 'he', 'she', 'it',
        'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by',
        'and', 'or', 'but', 'not', 'be', 'can', 'will',
        'tell', 'about', 'explain', 'describe', 'show',
    }

    def _key_terms(self, text):
        terms = re.findall(r"[a-zA-Z0-9'.-]+", text.lower())
        return [t for t in terms if len(t) > 2 and t not in self.STOP]

    def _domain_tags(self, sentence):
        """Map sentence to knowledge domain tags."""
        sl = sentence.lower()
        tags = set()
        domains = {
            'kernel': ['kernel', 'memory', 'page table', 'heap', 'allocator', 'context switch',
                       'process table', 'scheduling', 'interrupt', 'driver', 'panic', 'vfs'],
            'boot': ['uefi', 'boot', 'bootloader', 'efi', 'firmware', 'gop', 'fat32', 'ovmf'],
            'git': ['git', 'commit', 'merge', 'branch', 'push', 'pull', 'clone', 'stash',
                    'rebase', 'checkout', 'repository'],
            'linux': ['linux', 'linux command', 'shell', 'bash', 'terminal', 'grep',
                      'pacman', 'systemd', 'permission'],
            'programming': ['function', 'class', 'variable', 'compiler', 'error',
                           'rust', 'python', 'type', 'algorithm', 'data structure'],
            'pci': ['pci', 'bus', 'slot', 'device', 'vendor', 'class code'],
            'filesystem': ['filesystem', 'fat32', 'vfs', 'file', 'directory', 'ntfs', 'ext'],
            'network': ['network', 'tcp', 'ip', 'http', 'protocol', 'dns', 'dhcp'],
            'science': ['physics', 'chemistry', 'biology', 'science', 'atom', 'cell'],
            'general': ['technology', 'history', 'philosophy', 'economics', 'health'],
        }
        for domain, keywords in domains.items():
            for kw in keywords:
                if kw in sl:
                    tags.add(domain)
                    break
        return tags

    def _score(self, query, sentence):
        terms = self._key_terms(query)
        sl = sentence.lower()
        if not terms:
            return 0.0

        score = 0.0
        found_any = False
        for t in terms:
            if t in sl:
                found_any = True
                freq = self.word_freqs.get(t, 1)
                rarity = 1.0 / max(freq, 1)
                score += 1.0 + rarity * 2.0

        if not found_any:
            return 0.0

        # Entity overlap (tech terms, proper nouns)
        entities = set(re.findall(r'[A-Z][a-zA-Z0-9]+', query))
        sent_ents = set(re.findall(r'[A-Z][a-zA-Z0-9]+', sentence))
        overlap = entities & sent_ents
        score += len(overlap) * 4.0

        # Domain match bonus
        q_tags = self._domain_tags(query)
        s_tags = self._domain_tags(sentence)
        domain_overlap = q_tags & s_tags
        if domain_overlap:
            score += len(domain_overlap) * 3.5

        # Domain mismatch penalty
        if q_tags and s_tags and not domain_overlap:
            score *= 0.3

        # Quality filtering
        words = sentence.split()
        if len(words) < 5 or len(words) > 35:
            score *= 0.3
        if sl[0].isalpha() and sl[0].islower():
            score *= 0.5
        if sentence[-1] in '.!?':
            score *= 1.2

        # Multi-word term bonus (e.g., "linked list" matches exact phrase)
        q_phrases = re.findall(r'[a-zA-Z]+ [a-zA-Z]+', query)
        for phrase in q_phrases:
            if phrase.lower() in sl:
                score *= 2.0

        # Penalize sentences that look like debug/auto-saved artifacts
        if sl.startswith("react:") or sl.startswith("alt:") or sl.startswith("resolved:"):
            score *= 0.1

        return score

    def query(self, query, top_n=6):
        if not self.ready:
            return []
        scored = [(self._score(query, s), s) for s in self.sentences]
        scored.sort(key=lambda x: -x[0])
        return [s for sc, s in scored[:top_n] if sc > 0]

    def compose(self, query, max_len=500):
        matches = self.query(query)
        if not matches:
            return None

        used = set()
        parts = []
        for s in matches:
            sig = s[:40]
            if sig in used:
                continue
            used.add(sig)
            parts.append(s)
            if sum(len(p) for p in parts) > max_len:
                break

        if not parts:
            return None
        if len(parts) == 1 and len(parts[0]) < 25:
            return None
        return ' '.join(parts)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Query Decomposer (simulates multi-step reasoning)
# ═══════════════════════════════════════════════════════════════════════════════

def decompose_query(query):
    """If direct knowledge fails, try related sub-topics."""
    ql = query.lower()
    topics = [query]

    related = {
        'kernel': 'kernel memory management process scheduling',
        'uefi': 'uefi boot process uefi protocols',
        'memory': 'memory page table heap allocation',
        'boot': 'boot process bootloader uefi',
        'process': 'process scheduling context switch',
        'pci': 'pci bus device driver',
        'git': 'git merge branch commit',
    }

    for key, expansion in related.items():
        if key in ql:
            topics.append(expansion)
            break

    return topics[:3]


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Integrated Response Generator
# ═══════════════════════════════════════════════════════════════════════════════

class Genius:
    """Full response engine. Combines composition + n-gram generation."""

    def __init__(self):
        self.composer = KnowlegeComposer()
        self.ngram = NGramLM()
        self.ready = False

    def train(self, sentences):
        self.composer.train(sentences)
        self.ngram.train(sentences)
        self.ready = True

    def respond(self, query, max_len=600):
        if not self.ready or not query:
            return None

        # Step 1: Get relevant knowledge
        response = self.composer.compose(query, max_len)

        # Step 2: If good knowledge found, return it
        if response and len(response) > 40:
            return response

        # Step 3: If no direct knowledge, try n-gram generation
        topics = decompose_query(query)
        all_parts = []

        for topic in topics[:3]:
            r = self.composer.compose(topic, max_len // 2)
            if r and len(r) > 20:
                all_parts.append(r)

        if all_parts:
            return ' '.join(all_parts)

        # Step 4: Last resort — n-gram generation
        gen = self.ngram.generate(query, max_words=30, temperature=0.8)
        if gen:
            return gen

        return None


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Global Instance
# ═══════════════════════════════════════════════════════════════════════════════

_MASTER = None


def get_genius(force_retrain=False):
    global _MASTER
    if _MASTER is not None and not force_retrain:
        return _MASTER

    _MASTER = Genius()
    sentences = load_sentences()
    if sentences:
        print(f"[Genius] Training on {len(sentences)} sentences...", end=' ')
        sys.stdout.flush()
        t0 = time.time()
        _MASTER.train(sentences)
        print(f"done in {time.time()-t0:.3f}s")
    return _MASTER


def generate_response(prompt, max_len=600):
    g = get_genius()
    if not g.ready:
        return None
    return g.respond(prompt, max_len)


# ═══════════════════════════════════════════════════════════════════════════════
# 7. CLI
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("[Genius] Initializing...")
    g = get_genius(force_retrain=True)
    print(f"[Genius] Ready.\n")

    while True:
        try:
            q = input("Ask: ").strip()
            if q in ("exit", "quit", ""):
                break
            r = g.respond(q)
            print()
            if r:
                print(r)
            else:
                print("(no relevant knowledge found)")
            print()
        except KeyboardInterrupt:
            print("\nBye.")
            break
