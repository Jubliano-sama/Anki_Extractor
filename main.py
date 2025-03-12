#!/usr/bin/env python3
import sys, re, requests, time
from bs4 import BeautifulSoup

def fetch_definitions(word, retries=3, timeout=5):
    url = f"https://dictionary.cambridge.org/dictionary/english/{word}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
    }
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=headers, timeout=timeout)
            if r.status_code != 200:
                print(f"error fetching definition for {word}: status code {r.status_code}")
                return []
            soup = BeautifulSoup(r.text, 'html.parser')
            d_list = soup.find_all('div', class_="def ddef_d db")
            # use a space separator to preserve spacing between adjacent tags
            definitions = [d.get_text(" ", strip=True) for d in d_list if d.get_text(" ", strip=True)]
            return definitions
        except Exception as e:
            print(f"error fetching definition for {word}: {e}")
            if attempt < retries - 1:
                time.sleep(1)
            else:
                return []

def main(filename):
    try:
        with open(filename, 'r') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"error opening file: {e}")
        sys.exit(1)

    # extract lines that are a single word (letters only)
    words = [line.strip() for line in lines if line.strip() and re.fullmatch(r'[a-zA-Z]+', line.strip())]
    word_definitions = {}
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
                    chosen_def = input("enter new definition: ").strip()
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
            if ans == 'y' or ans == '':
                word_definitions[word] = chosen_def
                break
            elif ans == 'n':
                new_def = input("enter new definition: ").strip()
                word_definitions[word] = new_def
                break
            elif ans == 's':
                skipped_words.append(word)
                break
            else:
                print("invalid input, try again")

    print("\nskipped words:")
    print(", ".join(skipped_words))
    
    print("\nword-definition pairs:")
    for w, d in word_definitions.items():
        print(f"{w}: {d}")

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("usage: python script.py <input_file>")
        sys.exit(1)
    main(sys.argv[1])
