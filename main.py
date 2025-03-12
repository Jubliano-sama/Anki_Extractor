#!/usr/bin/env python3
import sys, re, requests, time, csv, os
from bs4 import BeautifulSoup

# for gui mode
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

def fetch_definitions(word, retries=3, timeout=5):
    url = f"https://dictionary.cambridge.org/dictionary/english/{word}"
    headers = {
        'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                       'AppleWebKit/537.36 (KHTML, like Gecko) '
                       'Chrome/115.0.0.0 Safari/537.36')
    }
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=headers, timeout=timeout)
            if r.status_code != 200:
                print(f"error fetching definition for {word}: status code {r.status_code}")
                return []
            soup = BeautifulSoup(r.text, 'html.parser')
            d_list = soup.find_all('div', class_="def ddef_d db")
            definitions = [d.get_text(" ", strip=True) for d in d_list if d.get_text(" ", strip=True)]
            return definitions
        except Exception as e:
            print(f"error fetching definition for {word}: {e}")
            if attempt < retries - 1:
                time.sleep(1)
            else:
                return []

def process_cli(filename):
    try:
        with open(filename, 'r') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"error opening file: {e}")
        sys.exit(1)

    words = [line.strip() for line in lines if line.strip() and re.fullmatch(r'[a-zA-Z]+', line.strip())]
    anki_cards = []
    skipped_words = []

    for word in words:
        print(f"\nword: {word}")
        definitions = fetch_definitions(word)
        chosen_def = None

        if not definitions:
            chosen_def = "definition not found"
            print("no definitions found.")
        elif len(definitions) == 1:
            chosen_def = definitions[0]
            print(f"fetched definition: {chosen_def}")
        else:
            print("multiple definitions found:")
            for idx, d in enumerate(definitions, start=1):
                print(f"{idx}. {d}")
            while True:
                choice = input("choose a definition number, or type 'n' to edit, or 's' to skip: ").strip().lower()
                if choice == 'n':
                    chosen_def = input(f"edit definition (default: {definitions[0]}): ").strip()
                    if chosen_def == "":
                        chosen_def = definitions[0]
                    else:
                        chosen_def = chosen_def.replace(r'\n', '\n')
                    break
                elif choice == 's':
                    skipped_words.append(word)
                    chosen_def = None
                    break
                elif choice.isdigit() and 1 <= int(choice) <= len(definitions):
                    chosen_def = definitions[int(choice) - 1]
                    break
                else:
                    print("invalid input, try again")

        if chosen_def is None:
            continue

        while True:
            ans = input("is this ok? type 'y' to accept, 'n' to edit, or 's' to skip: ").strip().lower()
            if ans == 'y':
                break
            elif ans == 'n':
                edited = input(f"edit definition (default: {chosen_def}): ").strip()
                if edited != "":
                    chosen_def = edited.replace(r'\n', '\n')
                break
            elif ans == 's':
                skipped_words.append(word)
                chosen_def = None
                break
            else:
                print("invalid input, try again")

        if chosen_def is None:
            continue

        while True:
            card_choice = input("generate anki card for this word? type 'b' for basic, 'br' for basic & reversed, or 'n' for none: ").strip().lower()
            if card_choice in ('b', 'br', 'n'):
                break
            else:
                print("invalid input, try again")

        if card_choice != 'n':
            anki_cards.append((word, chosen_def, card_choice))

    print("\nskipped words:")
    print(", ".join(skipped_words))
    
    print("\nword-definition pairs selected for anki cards:")
    for word, definition, card_type in anki_cards:
        ctype = 'basic' if card_type=='b' else 'basic & reversed'
        print(f"{word}: {definition} ({ctype})")

    if not anki_cards:
        print("no anki cards generated.")
        return

    basic_cards = [(word, definition) for (word, definition, card_type) in anki_cards if card_type == 'b']
    br_cards = [(word, definition) for (word, definition, card_type) in anki_cards if card_type == 'br']

    if basic_cards:
        basic_file = "anki_basic.csv"
        with open(basic_file, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["front", "back"])
            for word, definition in basic_cards:
                writer.writerow([word, definition])
        print(f"\nanki basic cards generated in {basic_file}")
    else:
        print("\nno basic cards to generate.")

    if br_cards:
        br_file = "anki_basic_reversed.csv"
        with open(br_file, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["front", "back"])
            for word, definition in br_cards:
                writer.writerow([word, definition])
        print(f"\nanki basic & reversed cards generated in {br_file}")
    else:
        print("\nno basic & reversed cards to generate.")

class Wizard:
    def __init__(self, root, words):
        self.root = root
        self.words = words
        self.results = []  # list of tuples: (word, definition, card_type)
        self.index = 0

        self.frame = ttk.Frame(root, padding="10")
        self.frame.grid(row=0, column=0, sticky="nsew")
        root.title("anki card generator - gui mode")

        # word label
        self.word_label = ttk.Label(self.frame, text="")
        self.word_label.grid(row=0, column=0, columnspan=2, sticky="w")
        # definitions listbox
        self.def_listbox = tk.Listbox(self.frame, height=5, width=60)
        self.def_listbox.grid(row=1, column=0, columnspan=2, sticky="nsew")
        self.def_listbox.bind("<<ListboxSelect>>", self.on_def_select)
        # text widget for editing definition
        self.def_text = tk.Text(self.frame, height=5, width=60)
        self.def_text.grid(row=2, column=0, columnspan=2, sticky="nsew")
        # card type radio buttons
        self.card_type = tk.StringVar(value="b")
        ttk.Label(self.frame, text="card type:").grid(row=3, column=0, sticky="w")
        self.radio_basic = ttk.Radiobutton(self.frame, text="basic", variable=self.card_type, value="b")
        self.radio_br = ttk.Radiobutton(self.frame, text="basic & reversed", variable=self.card_type, value="br")
        self.radio_skip = ttk.Radiobutton(self.frame, text="skip", variable=self.card_type, value="n")
        self.radio_basic.grid(row=3, column=1, sticky="w")
        self.radio_br.grid(row=4, column=1, sticky="w")
        self.radio_skip.grid(row=5, column=1, sticky="w")
        # next button
        self.next_button = ttk.Button(self.frame, text="next", command=self.next_word)
        self.next_button.grid(row=6, column=1, sticky="e")
        self.show_word()

    def show_word(self):
        if self.index >= len(self.words):
            self.finish()
            return
        self.def_listbox.delete(0, tk.END)
        self.def_text.delete("1.0", tk.END)
        current_word = self.words[self.index]
        self.word_label.config(text=f"word: {current_word}")
        definitions = fetch_definitions(current_word)
        if not definitions:
            definitions = ["definition not found"]
        # store definitions for current word
        self.current_definitions = definitions
        for d in definitions:
            self.def_listbox.insert(tk.END, d)
        # pre-populate text widget with first definition
        self.def_text.insert(tk.END, definitions[0])
        # default card type is basic (b)
        self.card_type.set("b")

    def on_def_select(self, event):
        selection = self.def_listbox.curselection()
        if selection:
            index = selection[0]
            selected_def = self.current_definitions[index]
            self.def_text.delete("1.0", tk.END)
            self.def_text.insert(tk.END, selected_def)

    def next_word(self):
        # get edited definition from text widget, replace literal "\n" with actual newlines
        definition = self.def_text.get("1.0", tk.END).strip().replace(r'\n', '\n')
        ctype = self.card_type.get()
        current_word = self.words[self.index]
        if ctype != "n":
            self.results.append((current_word, definition, ctype))
        self.index += 1
        if self.index < len(self.words):
            self.show_word()
        else:
            self.finish()

    def finish(self):
        basic_cards = [(word, definition) for (word, definition, card_type) in self.results if card_type == 'b']
        br_cards = [(word, definition) for (word, definition, card_type) in self.results if card_type == 'br']
        if basic_cards:
            basic_file = "anki_basic.csv"
            with open(basic_file, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(["front", "back"])
                for word, definition in basic_cards:
                    writer.writerow([word, definition])
            messagebox.showinfo("done", f"anki basic cards generated in {os.path.abspath(basic_file)}")
        else:
            messagebox.showinfo("done", "no basic cards to generate.")
        if br_cards:
            br_file = "anki_basic_reversed.csv"
            with open(br_file, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(["front", "back"])
                for word, definition in br_cards:
                    writer.writerow([word, definition])
            messagebox.showinfo("done", f"anki basic & reversed cards generated in {os.path.abspath(br_file)}")
        else:
            messagebox.showinfo("done", "no basic & reversed cards to generate.")
        self.root.quit()

def process_gui():
    root = tk.Tk()
    root.withdraw()
    file_path = filedialog.askopenfilename(title="choose input file", filetypes=[("text files", "*.txt"), ("all files", "*.*")])
    if not file_path:
        messagebox.showerror("error", "no file selected")
        sys.exit(1)
    with open(file_path, 'r') as f:
        lines = f.readlines()
    words = [line.strip() for line in lines if line.strip() and re.fullmatch(r'[a-zA-Z]+', line.strip())]
    root.deiconify()
    Wizard(root, words)
    root.mainloop()

if __name__ == '__main__':
    # if user passes '--gui', use gui mode; otherwise, expect a filename argument
    if len(sys.argv) == 2 and sys.argv[1] == "--gui":
        process_gui()
    elif len(sys.argv) == 2:
        process_cli(sys.argv[1])
    else:
        print("usage:")
        print("  cli mode: python script.py <input_file>")
        print("  gui mode: python script.py --gui")
