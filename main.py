#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys, re, os, csv, time, html, json, requests, configparser, contextlib, argparse
from collections import OrderedDict
from pathlib import Path
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor

# Optional dependencies
with contextlib.suppress(ImportError):
    import ebooklib, ebooklib.epub as _epub
with contextlib.suppress(ImportError):
    import PyPDF2
with contextlib.suppress(ImportError):
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

# ---------------------------------------------------------------------------#
# Config                                                                    #
# ---------------------------------------------------------------------------#

CFG_PATH = Path(__file__).with_name('config.ini')

def load_cfg(path=CFG_PATH):
    cp = configparser.ConfigParser()
    cp.read(path, encoding='utf-8')
    key = cp.get('openrouter', 'api_key', fallback='').strip()
    model = cp.get('openrouter', 'model', fallback='').strip()
    if not key or not model:
        raise RuntimeError('OpenRouter api_key or model missing in config.ini')
    def_params = {
        'temperature': cp.getfloat('llm_definition', 'temperature', fallback=0.2),
        'max_tokens': cp.getint('llm_definition', 'max_tokens', fallback=64),
        'prompt': cp.get('llm_definition', 'prompt', fallback="You are to define a word for an Anki vocab list. Give a concise dictionary-style definition for '{word}', which is part of a book. Please make sure the definition does not contain any words which may be non-trivial themselves. The context in which it appears is given. Do not include the word in the definition.")
    }
    ex_params = {
        'temperature': cp.getfloat('llm_example', 'temperature', fallback=0.5),
        'max_tokens': cp.getint('llm_example', 'max_tokens', fallback=80),
        'prompt': cp.get('llm_example', 'prompt', fallback="You are to provide a simple example sentence using '{word}' for an Anki vocab list. The definition is: '{definition}'. Write one natural, concise and simple example sentence that aligns with this specific meaning. Do not include any other words in the sentence which may be non-trivial. React only with the sentence. If context is provided, consider it: {context}")
    }
    return key, model, def_params, ex_params

OR_API_KEY, OR_MODEL, DEF_PARAMS, EX_PARAMS = load_cfg()

# ---------------------------------------------------------------------------#
# Helper Functions                                                          #
# ---------------------------------------------------------------------------#

def fetch_definitions(word, retries=3, timeout=5):
    url = f"https://dictionary.cambridge.org/dictionary/english/{word}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    for _ in range(retries):
        try:
            r = requests.get(url, headers=headers, timeout=timeout)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, 'html.parser')
                defs = [d.get_text(" ", strip=True) for d in soup.find_all('div', class_="def ddef_d db")]
                if defs:
                    return defs
        except Exception:
            time.sleep(1)
    return []

def llm_call(prompt, max_tokens, temperature):
    headers = {
        "Authorization": f"Bearer {OR_API_KEY}",
        "Content-Type": "application/json",
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
    prompt = DEF_PARAMS['prompt'].format(word=word)
    if ctx:
        prompt += f"\ncontext: {ctx}"
    return llm_call(prompt, DEF_PARAMS['max_tokens'], DEF_PARAMS['temperature'])

def gen_example(word, definition, ctx=None):
    prompt = EX_PARAMS['prompt'].format(word=word, definition=definition, context=ctx or '')
    return llm_call(prompt, EX_PARAMS['max_tokens'], EX_PARAMS['temperature'])

def load_book_text(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".txt":
        return path.read_text(encoding='utf-8', errors='ignore')
    if ext == ".epub" and 'ebooklib.epub' in sys.modules:
        book = _epub.read_epub(str(path))
        return "\n".join(html.unescape(item.get_content().decode('utf-8', 'ignore'))
                         for item in book.get_items() if item.get_type() == ebooklib.ITEM_DOCUMENT)
    if ext == ".pdf" and 'PyPDF2' in sys.modules:
        pdf = PyPDF2.PdfReader(str(path))
        return "\n".join(pg.extract_text() or '' for pg in pdf.pages)
    raise RuntimeError(f"Unsupported book type: {ext}")

def find_contexts(text: str, word: str, span: int = 120, max_ctx: int = 8):
    rgx = re.compile(rf'\b{re.escape(word)}\b', re.IGNORECASE)
    return [text[max(0, m.start() - span):m.end() + span].replace('\n', ' ').strip()
            for m in list(rgx.finditer(text))[:max_ctx]]

def pregen_definitions(words, corpus_text, num_workers=5):
    def gen_def(word):
        ctx = "\n".join(find_contexts(corpus_text, word)) if corpus_text else None
        return word, gen_definition(word, ctx)

    pregen_defs = {}
    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        for i, (word, definition) in enumerate(executor.map(gen_def, words), 1):
            pregen_defs[word] = definition
            print(f"Generated definition for '{word}' ({i}/{len(words)})")
    return pregen_defs

def parse_definitions(def_text, word):
    items = [item.strip() for item in re.split(r'^\d+\.\s*', def_text, flags=re.MULTILINE) if item.strip()]
    if len(items) > 1:
        split_words = []
        for i, item in enumerate(items, 1):
            if ':' in item:
                parts = item.split(':', 1)
                label = parts[0].strip('() ')
                definition = parts[1].strip()
                new_word = f"{word} ({label})"
            else:
                definition = item.strip()
                new_word = f"{word} (sense {i})"
            split_words.append((new_word, definition))
        return split_words
    else:
        return [(word, def_text)]

# ---------------------------------------------------------------------------#
# CLI Mode                                                                  #
# ---------------------------------------------------------------------------#

def dedupe(seq):
    return list(OrderedDict.fromkeys(seq))

def run_cli(word_list_file, pregen_llm=False, book_file=None):
    words = Path(word_list_file).read_text(encoding='utf-8').splitlines()
    words = dedupe([w.strip() for w in words if re.fullmatch(r'[A-Za-z]+', w.strip())])
    corpus = load_book_text(Path(book_file)) if book_file else None

    if pregen_llm:
        print("Pre-generating LLM definitions...")
        pregen_defs = pregen_definitions(words, corpus)
    else:
        pregen_defs = None

    anki_cards = []
    skipped = []

    for w in words:
        print(f"\nword: {w}")
        if pregen_defs and w in pregen_defs:
            d = pregen_defs[w]
            print(f"LLM definition: {d}")
        else:
            defs = fetch_definitions(w)
            if not defs:
                ctx = "\n".join(find_contexts(corpus, w)) if corpus else None
                defs.append(gen_definition(w, ctx))
            for i, d in enumerate(defs, 1):
                print(f"{i}. {d}")
            choice = input("pick #, 'l' for llm def, 's' skip: ").lower().strip()
            if choice == 's':
                skipped.append(w)
                continue
            if choice == 'l':
                ctx = "\n".join(find_contexts(corpus, w)) if corpus else None
                d = gen_definition(w, ctx)
            elif choice.isdigit() and 1 <= int(choice) <= len(defs):
                d = defs[int(choice) - 1]
            else:
                print("bad choice")
                continue

        ctx = "\n".join(find_contexts(corpus, w)) if corpus else None
        ex = gen_example(w, d, ctx)
        print(f"example: {ex}")
        card_choice = input("anki card? (b)asic, (r)everse, (n)one: ").lower()
        if card_choice == 'n':
            continue
        anki_cards.append((w, d + '<br><br>' + ex, 'br' if card_choice == 'r' else 'b'))

    write_anki(anki_cards)
    print("done; skipped ->", skipped)

def write_anki(cards):
    basics = [(w, d) for w, d, t in cards if t == 'b']
    revs = [(w, d) for w, d, t in cards if t == 'br']
    if basics:
        with open('anki_basic.csv', 'w', newline='', encoding='utf-8') as f:
            csv.writer(f).writerows([["front", "back"], *basics])
    if revs:
        with open('anki_basic_reversed.csv', 'w', newline='', encoding='utf-8') as f:
            csv.writer(f).writerows([["front", "back"], *revs])

# ---------------------------------------------------------------------------#
# GUI Mode                                                                  #
# ---------------------------------------------------------------------------#

class Wizard:
    def __init__(self, root, words, corpus_text, pregen_defs=None):
        self.root = root
        self.words = words
        self.orig_words = words[:]
        self.ctx_text = corpus_text
        self.pregen_defs = pregen_defs if pregen_defs else {}
        self.i = 0
        self.data = [{} for _ in range(len(words))]
        self.results = []

        root.title("Anki Card Generator")
        root.geometry("1000x600")
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)

        frm = ttk.Frame(root, padding=8)
        frm.grid(sticky="nsew")
        frm.columnconfigure(1, weight=1)
        frm.rowconfigure(1, weight=1)
        frm.rowconfigure(2, weight=1)

        # Word entry
        ttk.Label(frm, text="Word").grid(row=0, column=0, sticky='w')
        self.word_var = tk.StringVar()
        ttk.Entry(frm, textvariable=self.word_var, width=30).grid(row=0, column=1, sticky='ew')

        # Definition text area
        ttk.Label(frm, text="Definition").grid(row=1, column=0, sticky='nw')
        self.def_txt = tk.Text(frm, height=6, width=120, wrap='word')
        self.def_txt.grid(row=1, column=1, columnspan=2, sticky='nsew')

        # Example text area
        ttk.Label(frm, text="Example").grid(row=2, column=0, sticky='nw')
        self.ex_txt = tk.Text(frm, height=6, width=120, wrap='word')
        self.ex_txt.grid(row=2, column=1, columnspan=2, sticky='nsew')

        # Buttons
        btnfrm = ttk.Frame(frm)
        btnfrm.grid(row=3, column=0, columnspan=3, pady=4)
        ttk.Button(btnfrm, text="Generate Definition", command=self.ins_llm_def).pack(side='left', padx=2)
        ttk.Button(btnfrm, text="Generate Example", command=self.ins_llm_ex).pack(side='left', padx=2)
        ttk.Button(btnfrm, text="Generate Both", command=self.append_both).pack(side='left', padx=2)
        ttk.Button(btnfrm, text="Duplicate Word", command=self.duplicate_word).pack(side='left', padx=2)
        ttk.Button(btnfrm, text="Reset Word", command=self.reset_word).pack(side='left', padx=2)
        ttk.Button(btnfrm, text="Split Word", command=self.split_word).pack(side='left', padx=2)

        # Navigation and card type
        navfrm = ttk.Frame(frm)
        navfrm.grid(row=4, column=0, columnspan=3, pady=4, sticky='ew')
        ttk.Button(navfrm, text="Prev", command=self.prev).pack(side='left', padx=2)
        ttk.Button(navfrm, text="Next", command=self.next).pack(side='left', padx=2)
        self.card_type = tk.StringVar(value='b')
        ttk.Radiobutton(navfrm, text='Basic', variable=self.card_type, value='b').pack(side='left', padx=2)
        ttk.Radiobutton(navfrm, text='Reverse', variable=self.card_type, value='br').pack(side='left', padx=2)
        ttk.Radiobutton(navfrm, text='Skip', variable=self.card_type, value='n').pack(side='left', padx=2)

        self.show()

    def current_word(self):
        return self.word_var.get().strip()

    def ctx(self, word):
        return "\n".join(find_contexts(self.ctx_text, word)) if self.ctx_text else None

    def ins_llm_def(self):
        word = self.current_word()
        self.def_txt.delete('1.0', 'end')
        self.def_txt.insert('end', gen_definition(word, self.ctx(word)))

    def ins_llm_ex(self):
        word = self.current_word()
        definition = self.def_txt.get('1.0', 'end').strip()
        if not definition:
            messagebox.showwarning("Warning", "Please provide a definition first.")
            return
        self.ex_txt.delete('1.0', 'end')
        self.ex_txt.insert('end', gen_example(word, definition, self.ctx(word)))

    def append_both(self):
        word = self.current_word()
        ctx = self.ctx(word)
        d = gen_definition(word, ctx)
        self.def_txt.delete('1.0', 'end')
        self.def_txt.insert('end', d)
        e = gen_example(word, d, ctx)
        self.ex_txt.delete('1.0', 'end')
        self.ex_txt.insert('end', e)

    def duplicate_word(self):
        self.save_current()
        self.words.insert(self.i + 1, self.current_word())
        self.orig_words.insert(self.i + 1, self.current_word())
        self.data.insert(self.i + 1, {})
        self.i += 1
        self.show()

    def reset_word(self):
        self.word_var.set(self.orig_words[self.i])

    def split_word(self):
        word = self.current_word()
        def_text = self.def_txt.get('1.0', 'end').strip()
        new_entries = parse_definitions(def_text, word)
        if len(new_entries) > 1:
            # Remove current word
            del self.words[self.i]
            del self.orig_words[self.i]
            del self.data[self.i]
            # Insert new words
            for j, (new_word, definition) in enumerate(new_entries):
                self.words.insert(self.i + j, new_word)
                self.orig_words.insert(self.i + j, new_word)
                self.data.insert(self.i + j, {'word': new_word, 'text': definition, 'card_type': 'b'})
            # Show the first new word
            self.show()
        else:
            messagebox.showinfo("Info", "No multiple definitions found to split.")

    def save_current(self):
        if self.i < len(self.words):
            self.data[self.i] = {
                'word': self.current_word(),
                'text': (self.def_txt.get('1.0', 'end').strip() + '\n\n' +
                         self.ex_txt.get('1.0', 'end').strip()).strip(),
                'card_type': self.card_type.get()
            }

    def show(self):
        if self.i >= len(self.words):
            self.finish()
            return
        data = self.data[self.i]
        w = data.get('word', self.orig_words[self.i])
        self.word_var.set(w)
        text = data.get('text', '')
        self.def_txt.delete('1.0', 'end')
        self.ex_txt.delete('1.0', 'end')
        if text:
            parts = text.split('\n\n', 1)
            self.def_txt.insert('end', parts[0])
            if len(parts) > 1:
                self.ex_txt.insert('end', parts[1])
        else:
            if w in self.pregen_defs:
                self.def_txt.insert('end', self.pregen_defs[w])
            else:
                defs = fetch_definitions(w) or [gen_definition(w, self.ctx(w))]
                self.def_txt.insert('end', defs[0])
        self.card_type.set(data.get('card_type', 'b'))

    def next(self):
        self.save_current()
        self.i += 1
        self.show()

    def prev(self):
        if self.i > 0:
            self.save_current()
            self.i -= 1
            self.show()

    def finish(self):
        self.results = [(d['word'], d['text'], d['card_type']) for d in self.data
                        if d.get('card_type') in ('b', 'br')]
        write_anki(self.results)
        messagebox.showinfo("Done", "Anki files written; bye")
        self.root.quit()

# ---------------------------------------------------------------------------#
# Entry-Point                                                               #
# ---------------------------------------------------------------------------#

def choose_file(title, filetypes):
    return filedialog.askopenfilename(title=title, filetypes=filetypes)

def run_gui(pregen_llm=False):
    root = tk.Tk()
    root.withdraw()
    word_file = choose_file("Choose word list (.txt or .mrexpt)",
                            [("Text files", "*.txt *.mrexpt"), ("All files", "*.*")])
    if not word_file:
        sys.exit("No word list selected")
    book_file = choose_file("Choose book for context (txt/epub/pdf) – cancel to skip",
                            [("Supported files", "*.txt *.epub *.pdf"), ("All files", "*.*")])
    corpus = load_book_text(Path(book_file)) if book_file else None
    words = dedupe([w.strip() for w in Path(word_file).read_text(encoding='utf-8').splitlines()
                    if re.fullmatch(r'[A-Za-z]+', w.strip())])

    if pregen_llm:
        print("Pre-generating LLM definitions...")
        pregen_defs = pregen_definitions(words, corpus)
    else:
        pregen_defs = None

    root.deiconify()
    root.geometry("1000x600")
    Wizard(root, words, corpus, pregen_defs)
    root.mainloop()

# ---------------------------------------------------------------------------#
# Main                                                                      #
# ---------------------------------------------------------------------------#

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Anki Card Generator")
    parser.add_argument('--gui', action='store_true', help='Run in GUI mode')
    parser.add_argument('--pregen-llm', action='store_true', help='Pre-generate LLM definitions')
    parser.add_argument('word_list', nargs='?', help='Word list file for CLI mode')
    parser.add_argument('book', nargs='?', help='Book file for context (optional)')
    args = parser.parse_args()

    if args.gui:
        if 'tkinter' not in sys.modules:
            sys.exit("tkinter missing; cannot run GUI")
        run_gui(args.pregen_llm)
    elif args.word_list:
        run_cli(args.word_list, args.pregen_llm, args.book)
    else:
        parser.print_help()