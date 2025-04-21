#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys, re, os, csv, time, html, json, requests, configparser, contextlib
from collections import OrderedDict
from pathlib import Path
from bs4 import BeautifulSoup

# optional heavy deps
with contextlib.suppress(ImportError):
    import ebooklib, ebooklib.epub as _epub
with contextlib.suppress(ImportError):
    import PyPDF2
with contextlib.suppress(ImportError):
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

# ---------------------------------------------------------------------------#
# config                                                                     #
# ---------------------------------------------------------------------------#

CFG_PATH = Path(__file__).with_name('config.ini')

def load_cfg(path=CFG_PATH):
    cp = configparser.ConfigParser()
    cp.read(path, encoding='utf-8')
    key   = cp.get('openrouter', 'api_key',  fallback='').strip()
    model = cp.get('openrouter', 'model',    fallback='').strip()
    if not key:
        raise RuntimeError('openrouter api_key missing in config.ini')
    if not model:
        raise RuntimeError('openrouter model missing in config.ini')
    return key, model

OR_API_KEY, OR_MODEL = load_cfg()

# ---------------------------------------------------------------------------#
# helper: scrape cambridge definition                                        #
# ---------------------------------------------------------------------------#

def fetch_definitions(word, retries=3, timeout=5):
    url = f"https://dictionary.cambridge.org/dictionary/english/{word}"
    headers = {
        'User-Agent':
        ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
         'AppleWebKit/537.36 (KHTML, like Gecko) '
         'Chrome/115.0.0.0 Safari/537.36')
    }
    for _ in range(retries):
        try:
            r = requests.get(url, headers=headers, timeout=timeout)
            if r.status_code != 200:
                break
            soup = BeautifulSoup(r.text, 'html.parser')
            defs = [d.get_text(" ", strip=True)
                    for d in soup.find_all('div', class_="def ddef_d db")]
            if defs:
                return defs
        except Exception:
            time.sleep(1)
    return []

# ---------------------------------------------------------------------------#
# helper: openrouter                                                         #
# ---------------------------------------------------------------------------#

def llm_call(prompt, max_tokens=128, temperature=0.7):
    headers = {
        "Authorization": f"Bearer {OR_API_KEY}",
        "Content-Type": "application/json",
        # optional prestige headers
        "HTTP-Referer": "https://github.com/your-handle/anki-gen",
        "X-Title": "anki-card-generator"
    }
    payload = {
        "model": OR_MODEL,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}]
    }
    r = requests.post("https://openrouter.ai/api/v1/chat/completions",
                      headers=headers, data=json.dumps(payload), timeout=30)
    r.raise_for_status()
    return r.json()['choices'][0]['message']['content'].strip()

def gen_definition(word, ctx=None):
    prompt = f"You are to define a word for an Anki vocab list. Give a concise dictionary-style definition for '{word}', which is part of a book. Please make sure the definition does not contain any words which may be non-trivial themselves. The context in which it appears is given. Do not include the word in the definition."
    if ctx:
        prompt += f"\ncontext: {ctx}"
    return llm_call(prompt, max_tokens=64, temperature=0.2)

def gen_example(word, ctx=None):
    prompt = (f"You are to provide a simple example sentence using '{word}' for an Anki vocab list. Write one natural, concise and simple example sentence using '{word}', which is part of a book. Do not include any other words in the sentence which may be non-trivial. React only with the sentence."
              f"in the sense defined by the given context if any. If and only if there happen to be multiple meanings, generate multiple sentences seperated by '; '")
    if ctx:
        prompt += f"\ncontext: {ctx}"
    return llm_call(prompt, max_tokens=80, temperature=0.9)

# ---------------------------------------------------------------------------#
# helper: book ingestion + concordance                                       #
# ---------------------------------------------------------------------------#

SPAN = 120           # chars either side of match
MAX_CTX = 8         # max snippets fed to llm

def load_book_text(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".txt":
        return path.read_text(encoding='utf-8', errors='ignore')
    if ext == ".epub":
        if 'ebooklib.epub' not in sys.modules:
            raise RuntimeError("install ebooklib to read epub files")
        book = _epub.read_epub(str(path))
        texts = []
        for item in book.get_items():
            if item.get_type() == ebooklib.ITEM_DOCUMENT:
                texts.append(html.unescape(
                    item.get_content().decode('utf-8', 'ignore')))
        return "\n".join(texts)
    if ext == ".pdf":
        if 'PyPDF2' not in sys.modules:
            raise RuntimeError("install PyPDF2 to read pdf files")
        pdf = PyPDF2.PdfReader(str(path))
        return "\n".join(pg.extract_text() or '' for pg in pdf.pages)
    raise RuntimeError(f"unsupported book type: {ext}")

def find_contexts(text: str, word: str,
                  span: int = SPAN, max_ctx: int = MAX_CTX):
    rgx = re.compile(rf'\b{re.escape(word)}\b', re.IGNORECASE)
    out, last = [], 0
    for m in rgx.finditer(text):
        if len(out) >= max_ctx:
            break
        start = max(0, m.start() - span)
        end   = m.end() + span
        snippet = text[start:end].replace('\n', ' ')
        out.append(snippet.strip())
    return out

# ---------------------------------------------------------------------------#
# CLI mode                                                                   #
# ---------------------------------------------------------------------------#

def dedupe(seq):
    return list(OrderedDict.fromkeys(seq))

def run_cli(filename, book=None):
    words = Path(filename).read_text(encoding='utf-8').splitlines()
    words = [w.strip() for w in words if re.fullmatch(r'[A-Za-z]+', w.strip())]
    words = dedupe(words)

    corpus = load_book_text(Path(book)) if book else None
    anki_cards = []
    skipped = []

    for w in words:
        print(f"\nword: {w}")
        defs = fetch_definitions(w)
        if not defs:
            defs.append(gen_definition(w))
        for i, d in enumerate(defs, 1):
            print(f"{i}. {d}")
        choice = input("pick #, 'l' for llm def, 's' skip: ").lower().strip()
        if choice == 's':
            skipped.append(w)
            continue
        if choice == 'l':
            ctx = None
            if corpus:
                ctx = "\n".join(find_contexts(corpus, w))
            d = gen_definition(w, ctx)
        elif choice.isdigit() and 1 <= int(choice) <= len(defs):
            d = defs[int(choice) - 1]
        else:
            print("bad choice")
            continue

        ex = gen_example(w, ctx if corpus else None)
        print(f"example: {ex}")

        card_choice = input("anki card? (b)asic, (r)everse, (n)one: ").lower()
        if card_choice == 'n':
            continue
        anki_cards.append((w, d + '<br><br>' + ex,
                           'br' if card_choice == 'r' else 'b'))

    write_anki(anki_cards)
    print("done; skipped ->", skipped)

def write_anki(cards):
    basics = [(w, d) for w, d, t in cards if t == 'b']
    revs   = [(w, d) for w, d, t in cards if t == 'br']
    if basics:
        with open('anki_basic.csv', 'w', newline='', encoding='utf-8') as f:
            csv.writer(f).writerows([["front", "back"], *basics])
    if revs:
        with open('anki_basic_reversed.csv', 'w', newline='', encoding='utf-8') as f:
            csv.writer(f).writerows([["front", "back"], *revs])

# ---------------------------------------------------------------------------#
# GUI mode                                                                   #
# ---------------------------------------------------------------------------#

class Wizard:
    def __init__(self, root, words, corpus_text):
        self.root = root
        self.words = words
        self.orig_words = words[:]   # keep originals for reset
        self.ctx_text = corpus_text
        self.i = 0
        self.results = []

        root.title("anki card generator")
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)

        frm = ttk.Frame(root, padding=8)
        frm.grid(sticky="nsew")
        frm.columnconfigure(1, weight=1)

        # word entry
        ttk.Label(frm, text="word").grid(row=0, column=0, sticky='w')
        self.word_var = tk.StringVar()
        self.word_entry = ttk.Entry(frm, textvariable=self.word_var, width=30)
        self.word_entry.grid(row=0, column=1, sticky='ew')

        # definition / example text
        self.txt = tk.Text(frm, height=6, width=80, wrap='word')
        self.txt.grid(row=1, column=0, columnspan=3, sticky='nsew')

        # buttons
        btnfrm = ttk.Frame(frm)
        btnfrm.grid(row=2, column=0, columnspan=3, pady=4)
        ttk.Button(btnfrm, text="llm def", command=self.ins_llm_def).pack(side='left')
        ttk.Button(btnfrm, text="llm example", command=self.ins_llm_ex).pack(side='left')
        ttk.Button(btnfrm, text="append both", command=self.append_both).pack(side='left')
        ttk.Button(btnfrm, text="reset word", command=self.reset_word).pack(side='left')

        # nav / card type
        navfrm = ttk.Frame(frm)
        navfrm.grid(row=3, column=0, columnspan=3, pady=4, sticky='ew')
        ttk.Button(navfrm, text="prev", command=self.prev).pack(side='left')
        ttk.Button(navfrm, text="next", command=self.next).pack(side='left')
        self.card_type = tk.StringVar(value='b')
        ttk.Radiobutton(navfrm, text='basic',  variable=self.card_type, value='b').pack(side='left')
        ttk.Radiobutton(navfrm, text='rev',    variable=self.card_type, value='br').pack(side='left')
        ttk.Radiobutton(navfrm, text='skip',   variable=self.card_type, value='n').pack(side='left')

        self.show()

    # ---------------- internal ---------------- #

    def current_word(self):
        return self.word_var.get().strip()

    def ctx(self, word):
        if not self.ctx_text:
            return None
        return "\n".join(find_contexts(self.ctx_text, word))

    def ins_llm_def(self):
        word = self.current_word()
        self.txt.delete('1.0', 'end')
        self.txt.insert('end', gen_definition(word, self.ctx(word)))

    def ins_llm_ex(self):
        word = self.current_word()
        self.txt.insert('end', '\nExample: ' + gen_example(word, self.ctx(word)))

    def append_both(self):
        word = self.current_word()
        d = gen_definition(word, self.ctx(word))
        e = gen_example(word, self.ctx(word))
        self.txt.insert('end', ('' if self.txt.get('1.0', 'end').strip() == '' else '\n') + d + '\n' + e)

    def reset_word(self):
        self.word_var.set(self.orig_words[self.i])

    # --------------- nav ---------------------- #

    def show(self):
        if self.i >= len(self.words):
            self.finish()
            return
        w = self.words[self.i]
        self.word_var.set(w)
        self.txt.delete('1.0', 'end')
        defs = fetch_definitions(w) or [gen_definition(w, self.ctx(w))]
        self.txt.insert('end', defs[0])

    def store_current(self):
        ctype = self.card_type.get()
        if ctype == 'n':
            return
        text = self.txt.get('1.0', 'end').strip()
        self.results.append((self.current_word(), text, ctype))

    def next(self):
        self.store_current()
        self.i += 1
        self.show()

    def prev(self):
        if self.i == 0:
            return
        self.i -= 1
        self.show()

    def finish(self):
        write_anki(self.results)
        messagebox.showinfo("done", "anki files written; bye")
        self.root.quit()

# ---------------------------------------------------------------------------#
# entry-point                                                                #
# ---------------------------------------------------------------------------#

def choose_file(title, types):
    return filedialog.askopenfilename(title=title)

def run_gui():
    root = tk.Tk()
    root.withdraw()
    word_file = choose_file("choose word list (.txt)", [("text", "*.txt")])
    if not word_file:
        sys.exit("no word list selected")
    # optional book
    book_file = filedialog.askopenfilename(
        title="choose book for context (txt/epub/pdf) – cancel to skip",
        filetypes=[("all", "*.txt *.epub *.pdf")])
    corpus = load_book_text(Path(book_file)) if book_file else None

    words = Path(word_file).read_text(encoding='utf-8').splitlines()
    words = dedupe([w.strip() for w in words if re.fullmatch(r'[A-Za-z]+', w.strip())])

    root.deiconify()
    Wizard(root, words, corpus)
    root.mainloop()

# ---------------------------------------------------------------------------#

if __name__ == '__main__':
    if len(sys.argv) >= 2 and sys.argv[1] == '--gui':
        if 'tkinter' not in sys.modules:
            sys.exit("tkinter missing; cannot run gui")
        run_gui()
    elif len(sys.argv) >= 2:
        book = sys.argv[2] if len(sys.argv) >= 3 else None
        run_cli(sys.argv[1], book)
    else:
        print("usage:")
        print("  gui :  python script.py --gui")
        print("  cli :  python script.py <word_list.txt> [book.txt|.epub|.pdf]")
