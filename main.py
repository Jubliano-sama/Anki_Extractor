#!/usr/bin/env python3
import sys, re, requests, time, csv
from bs4 import BeautifulSoup

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

def get_edited_definition(default_def):
    prompt = f"edit definition (default: {default_def}): "
    new_def = input(prompt)
    if new_def == "":
        return default_def
    else:
        return new_def.replace(r'\n', '\n')

def main(filename):
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
                    chosen_def = get_edited_definition(definitions[0])
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
                chosen_def = get_edited_definition(chosen_def)
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

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("usage: python script.py <input_file>")
        sys.exit(1)
    main(sys.argv[1])
