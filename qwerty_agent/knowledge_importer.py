"""
Knowledge Importer — Free knowledge from Wikipedia API
No API key needed. Pure Python stdlib. Runs anywhere.

Downloads articles on ~500 technical/scientific topics,
converts them to Qwerty's JSON knowledge format,
and retrains Genius on the expanded dataset.
"""

import json
import os
import re
import sys
import time
import urllib.request
import urllib.parse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KNOWLEDGE_DIR = os.path.join(BASE_DIR, "knowledge")
MEMORY_DIR = os.path.join(BASE_DIR, "memory")

WIKIPEDIA_JSON = os.path.join(KNOWLEDGE_DIR, "wikipedia.json")
USER_AGENT = "QwertyAgent/2.0 (knowledge importer; kasish@qwerty)"

# ─── Wikipedia API ──────────────────────────────────────────────────────────────

WIKI_API = "https://en.wikipedia.org/w/api.php"

def wiki_request(params):
    """Query the Wikipedia API. Returns parsed JSON."""
    params["format"] = "json"
    params["origin"] = "*"
    url = WIKI_API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return None


def fetch_summary(title):
    """Fetch the extract/summary of a Wikipedia article."""
    params = {
        "action": "query",
        "prop": "extracts",
        "exintro": True,
        "explaintext": True,
        "titles": title,
        "redirects": 1,
    }
    data = wiki_request(params)
    if not data:
        return None
    pages = data.get("query", {}).get("pages", {})
    for page_id, page in pages.items():
        if page_id == "-1":
            return None
        return page.get("extract", None)
    return None


def search_titles(query):
    """Search Wikipedia for articles matching a query."""
    params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srlimit": 3,
        "srprop": "",
    }
    data = wiki_request(params)
    if not data:
        return None
    results = data.get("query", {}).get("search", [])
    if results:
        return results[0].get("title")
    return None


def fetch_sentences(title, max_sentences=12):
    """Fetch and split into sentences."""
    summary = fetch_summary(title)
    if not summary:
        # Try search as fallback
        found = search_titles(title)
        if found and found.lower() != title.lower():
            summary = fetch_summary(found)
    if not summary:
        return []
    cleaned = re.sub(r'\s+', ' ', summary).strip()
    sentences = re.split(r'(?<=[.!?])\s+', cleaned)
    result = []
    for s in sentences:
        s = s.strip()
        if len(s) > 20 and len(s) < 500:
            result.append(s)
    return result[:max_sentences]


# ─── Topic Catalog ──────────────────────────────────────────────────────────────

TOPICS = {
    "programming": [
        "Python (programming language)", "Rust (programming language)",
        "C (programming language)", "C++", "JavaScript", "Go (programming language)",
        "Java (programming language)", "TypeScript", "SQL", "Bash (Unix shell)",
        "Lua (programming language)", "Zig (programming language)",
        "Compiler", "Interpreter (computing)", "Assembly language",
        "Regular expression", "API", "Object-oriented programming",
        "Functional programming", "Procedural programming",
        "Type system", "Memory management", "Garbage collection (computer science)",
        "Exception handling", "Concurrency (computer science)",
        "Recursion (computer science)", "Algorithm", "Data structure",
        "Array (data structure)", "Linked list", "Stack (abstract data type)",
        "Queue (abstract data type)", "Tree (data structure)",
        "Graph (abstract data type)", "Hash table", "Binary search tree",
        "Sorting algorithm", "Search algorithm", "Graph algorithm",
        "Dynamic programming", "Big O notation",
        "Design Patterns", "Model-view-controller", "REST API",
        "Software testing", "Debugging", "Version control",
        "Code refactoring", "Software documentation",
        "Database", "Relational database", "NoSQL",
        "WebSocket", "HTTP", "JSON", "XML",
    ],
    "operating_systems": [
        "Operating system", "Linux", "Linux kernel", "Unix",
        "Kernel (operating system)", "Microkernel", "Monolithic kernel",
        "Device driver", "System call", "Interrupt", "Context switch",
        "Scheduling (computing)", "Memory management (operating systems)",
        "Virtual memory", "Paging", "Page table", "Heap (data structure)",
        "File system", "Virtual file system", "FAT32", "NTFS", "ext4",
        "BIOS", "UEFI", "Bootloader", "Booting",
        "Process (computing)", "Thread (computing)", "Multitasking",
        "Inter-process communication", "Deadlock", "Semaphore (programming)",
        "Mutex", "Input/output", "DMA", "PCI Express",
        "USB", "AHCI", "NVMe", "ACPI",
        "Firmware", "Embedded system", "Real-time operating system",
        "Systemd", "init", "Cgroups", "Namespace (Linux)",
        "Containerization (computing)", "Docker (software)",
    ],
    "networking": [
        "Computer network", "Internet", "TCP/IP", "IP address",
        "IPv4", "IPv6", "DNS", "DHCP", "HTTP", "HTTPS",
        "TLS", "SSH", "FTP", "SMTP", "IMAP", "POP3",
        "Ethernet", "Wi-Fi", "Router (computing)", "Switch (networking)",
        "Firewall (computing)", "Proxy server", "Load balancing (computing)",
        "OSI model", "Packet (information technology)",
        "Network socket", "Port (computer networking)",
        "Virtual private network", "NAT",
    ],
    "mathematics": [
        "Calculus", "Linear algebra", "Matrix (mathematics)",
        "Probability", "Statistics", "Differential equation",
        "Number theory", "Graph theory", "Set theory",
        "Trigonometry", "Geometry", "Topology",
        "Boolean algebra", "Mathematical logic",
        "Floating-point arithmetic", "Binary number",
        "Hexadecimal", "Numerical analysis",
        "Cryptography", "Information theory",
    ],
    "physics": [
        "Physics", "Classical mechanics", "Quantum mechanics",
        "Thermodynamics", "Electromagnetism", "Special relativity",
        "General relativity", "Newton's laws of motion",
        "Quantum computing", "Particle physics",
        "Nuclear physics", "Optics", "Acoustics",
        "Electricity", "Magnetism", "Semiconductor",
        "Transistor", "Integrated circuit", "Moore's law",
        "Clock signal", "Logic gate", "Flip-flop (electronics)",
        "CPU", "GPU", "FPGA", "Microcontroller",
    ],
    "chemistry": [
        "Chemistry", "Atom", "Chemical element", "Chemical bond",
        "Molecule", "Periodic table", "Chemical reaction",
        "Acid", "Base (chemistry)", "PH", "Redox",
        "Organic chemistry", "Inorganic chemistry",
        "Biochemistry", "Polymer", "Catalysis",
    ],
    "biology": [
        "Biology", "Cell (biology)", "DNA", "RNA", "Protein",
        "Genetics", "Evolution", "Natural selection",
        "Ecology", "Ecosystem", "Photosynthesis",
        "Virus", "Bacteria", "Fungus", "Human body",
        "Neuron", "Brain", "Immune system",
        "Enzyme", "Metabolism", "Homeostasis",
    ],
    "technology": [
        "Artificial intelligence", "Machine learning",
        "Deep learning", "Neural network", "Natural language processing",
        "Computer vision", "Robotics", "Automation",
        "Blockchain", "Cryptocurrency", "Cloud computing",
        "Virtualization", "Big data", "Data science",
        "Computer security", "Cryptography", "Authentication",
        "Encryption", "Access control",
        "Git", "GitHub", "Docker (software)", "Kubernetes",
        "Database index", "SQL injection", "Cross-site scripting",
        "Buffer overflow", "Race condition",
        "Computer architecture", "RISC-V", "x86",
        "ARM architecture family",
    ],
    "general": [
        "Philosophy", "Ethics", "Logic", "Epistemology",
        "Metaphysics", "History of science",
        "Economics", "Microeconomics", "Macroeconomics",
        "Geography", "Solar System", "Earth", "Moon",
        "Geology", "Climate", "Weather",
        "Language", "Linguistics", "Grammar",
        "Psychology", "Sociology", "Anthropology",
        "Democracy", "Capitalism", "Socialism",
        "Space exploration", "Satellite", "Telescope",
        "Black hole", "Galaxy", "Star", "Planet",
        "Matter", "Energy", "Light", "Time",
        "Internet", "World Wide Web", "Search engine",
        "Social media", "E-commerce",
        "Engineering", "Mechanical engineering",
        "Electrical engineering", "Civil engineering",
        "Reverse engineering", "Open-source software",
    ],
}


# ─── Import Engine ──────────────────────────────────────────────────────────────

def import_topics(topics_dict, delay=0.5):
    """Download Wikipedia summaries for all topics and build knowledge JSON."""
    knowledge = {}

    for category, titles in topics_dict.items():
        print(f"  [{category}] {len(titles)} topics...")
        category_data = {}

        for i, title in enumerate(titles):
            sys.stdout.write(f"\r    {i+1}/{len(titles)}: {title[:40]:40s}")
            sys.stdout.flush()

            sentences = fetch_sentences(title)

            key = title.lower().replace(" (programming language)", "")
            key = key.replace(" (computer science)", "")
            key = key.replace(" (computing)", "")
            key = key.replace(" (networking)", "")
            key = key.replace(" (data structure)", "")
            key = key.replace(" (operating system)", "")
            key = key.replace(" (software)", "")
            key = key.replace(" (electronics)", "")
            key = key.replace(" (biology)", "")

            if sentences:
                category_data[key] = {
                    "summary": sentences[0],
                    "sentences": sentences,
                }

            time.sleep(delay)

        print()
        knowledge[category] = category_data

    return knowledge


def save_knowledge(knowledge, path):
    """Save knowledge to JSON file in Qwerty format."""
    existing = {}
    if os.path.exists(path):
        try:
            with open(path) as f:
                existing = json.load(f)
        except:
            pass

    for category, data in knowledge.items():
        if category in existing:
            existing[category].update(data)
        else:
            existing[category] = data

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(existing, f, indent=2)

    total_articles = sum(len(v) for v in existing.values() if isinstance(v, dict))
    return total_articles


# ─── Retrain Genius ─────────────────────────────────────────────────────────────

def retrain_genius():
    """Retrain Genius on all knowledge (including newly imported)."""
    try:
        sys.path.insert(0, BASE_DIR)
        from qwerty_agent.genius import get_genius, load_sentences
        sentences = load_sentences()
        if sentences:
            g = get_genius(force_retrain=True)
            g.train(sentences)
            print(f"  Genius retrained on {len(sentences)} sentences")
            return True
    except Exception as e:
        print(f"  Genius retrain skipped: {e}")
    return False


# ─── Main ───────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("Qwerty Knowledge Importer")
    print("  Free knowledge from Wikipedia API (no key needed)")
    print(f"  Target: {sum(len(v) for v in TOPICS.values())} topics in {len(TOPICS)} categories")
    print("=" * 60)

    print("\nDownloading articles...")
    t0 = time.time()
    knowledge = import_topics(TOPICS, delay=0.3)
    elapsed = time.time() - t0

    total = sum(len(v) for v in knowledge.values())
    print(f"\nDownloaded {total} articles in {elapsed:.0f}s")

    print("\nSaving to knowledge/wikipedia.json...")
    saved = save_knowledge(knowledge, WIKIPEDIA_JSON)
    file_size = os.path.getsize(WIKIPEDIA_JSON)
    print(f"  {saved} articles saved ({file_size / 1024:.0f} KB)")

    print("\nRetraining Genius...")
    retrain_genius()

    print("\nDone! Qwerty now has expanded knowledge.")
    print(f"Run the agent to ask questions about any of {saved}+ topics.")


if __name__ == "__main__":
    main()
