# anki card generator

this script extracts single words from a text file, fetches definitions from the cambridge dictionary, and allows the user to create anki flashcards in either basic or basic & reversed formats. the script supports both command-line (cli) and graphical user interface (gui) modes.

## features
- extracts words that appear as single entries (not part of a sentence) from a given text file.
- fetches definitions from the cambridge dictionary.
- allows users to accept, edit, or skip definitions.
- enables individual selection of anki card types:
  - **basic:** word → definition
  - **basic & reversed:** word → definition & definition → word (handled by anki itself)
- outputs separate csv files for basic and basic & reversed cards.
- supports both **cli mode** and **gui mode**.

## installation
### prerequisites
- python 3.x
- required libraries:
  ```sh
  pip install requests beautifulsoup4 tkinter
  ```

## usage
### cli mode
```sh
python script.py <input_file>
```
example:
```sh
python script.py words.txt
```
this will process the words in `words.txt` and generate csv files for anki import.

### gui mode
```sh
python script.py --gui
```
this opens a graphical interface for easier word selection and definition editing.

## output
- `anki_basic.csv`: contains cards in **basic** format.
- `anki_basic_reversed.csv`: contains cards in **basic & reversed** format.

these csv files can be imported into anki using the appropriate note types.

## license
this project is released under the mit license.

