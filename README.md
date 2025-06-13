# Anki Vocabulary Card Generator

This script leverages the power of Large Language Models (LLMs) to automate the creation of high-quality vocabulary flashcards for Anki. It takes a list of words, uses an LLM to generate context-aware definitions and example sentences, and exports them into CSV files ready for import into Anki.

The script is highly configurable and can operate in two modes: a fast command-line interface (CLI) for quick processing and a powerful graphical user interface (GUI) for fine-grained control over each card.

By connecting to any model on **OpenRouter**, you can use state-of-the-art AI to generate learning materials tailored to your needs, turning any word list into a rich, ready-to-study Anki deck.

## ✨ Features

*   **LLM-Powered Content Generation**: Uses a configurable LLM (via OpenRouter) to generate custom, dictionary-style definitions and natural example sentences.
*   **Dual-Mode Operation**: Choose between a fast, automated **CLI mode** or an interactive **GUI mode** for full control.
*   **Context-Aware Generation**: Can use a book (TXT, EPUB, or PDF) as a corpus to find the context in which a word appears, leading to more relevant and accurate LLM-generated content.
*   **Word Sense Disambiguation**: The GUI includes a "Split Word" feature that uses an LLM to break a word down into its different meanings (e.g., "bank" -> "bank (finance)", "bank (river)"), allowing you to create separate cards for each sense.
*   **Customizable LLM Prompts**: Tailor the prompts for generating definitions, examples, and word senses to fit your exact needs via a `config.ini` file.
*   **Efficient Pre-generation**: Optionally pre-generate all LLM definitions in parallel to speed up the manual review process in both CLI and GUI modes.
*   **Flexible Card Types**: Create both basic (front-to-back) and reversed (back-to-front) Anki cards.
*   **Fallback to Web Scraping**: Can also fetch definitions from the Cambridge Dictionary as a supplementary source.
*   **Optional Dependencies**: The script works with basic functionality out of the box, but can be enhanced by installing optional libraries for PDF/EPUB support and the GUI.

## ⚙️ Setup and Configuration

### 1. Prerequisites

*   Python 3.8+
*   Required Python libraries: `requests`, `beautifulsoup4`

```bash
pip install requests beautifulsoup4
```

### 2. Optional Dependencies

For full functionality, install these optional packages:

*   **GUI Mode**: Requires `tkinter`, which is usually included with Python.
*   **EPUB Support**: `ebooklib`
*   **PDF Support**: `PyPDF2`

```bash
# Install all optional dependencies
pip install ebooklib PyPDF2
```

### 3. Configuration (`config.ini`)

Before running the script, you must create a `config.ini` file in the same directory. This file holds your API key and custom prompts for the LLM.

1.  **Create the file**: `touch config.ini`
2.  **Add the following content**, replacing the placeholders with your information:

    ```ini
    [openrouter]
    # Get your key from https://openrouter.ai/keys
    api_key = sk-or-v1-abc...xyz
    # Choose any model available on OpenRouter, e.g., "openai/gpt-4-turbo"
    model = mistralai/mistral-7b-instruct

    [llm_definition]
    temperature = 0.2
    max_tokens = 80
    prompt = You are to define a word for an Anki vocab list. Give a concise dictionary-style definition for '{word}'. Please make sure the definition does not contain any words which may be non-trivial themselves. The context in which it appears is given. Do not include the word in the definition. You may include multiple definitions in a numbered list if appropriate. If and only if there are common synonyms, please provide them prepended by 'syn: ' at the end seperated by commas.

    [llm_example]
    temperature = 0.7
    max_tokens = 80
    prompt = You are to provide a simple example sentence using '{word}' for an Anki vocab list. The definition is: '{definition}'. Write one natural, concise and simple example sentence that aligns with this specific meaning. Do not include any other words in the sentence which may be non-trivial. React only with the sentence. If context is provided, consider it: {context}

    [llm_word_senses]
    temperature = 0.1
    max_tokens = 128
    prompt = You are to provide a numbered list of different meanings for the word '{word}' given its definition: '{definition}', each with a concise label in parentheses. For example, for 'bank', you might write: 1. bank (finance) 2. bank (river) 3. bank (aviation) Please provide the numbered list for '{word}'. Please only provide the core senses, nothing redundant.
    ```

    **Note**: The `{word}`, `{definition}`, and `{context}` placeholders will be automatically filled in by the script.

## 🚀 How to Use

The script can be run in two primary modes: GUI or CLI.

### 🖥️ GUI Mode (Recommended for Control)

The GUI provides a "wizard" interface to step through each word, edit definitions and examples, and choose the card type. This is the best mode for high-quality, curated flashcards.

**To launch the GUI:**

```bash
python anki_generator.py --gui
```

The script will first prompt you to select:
1.  A **word list file** (a plain `.txt` file with one word per line).
2.  (Optional) A **book file** (`.txt`, `.epub`, or `.pdf`) to use for context. You can press "Cancel" to skip this step.

 <!-- Placeholder: Add a screenshot of your GUI here -->

**GUI Features:**
*   **Generate Definition/Example**: Use the LLM to generate content on the fly.
*   **Duplicate Word**: Create another card for the same word (e.g., for a different meaning).
*   **Reset Word**: Revert any changes made to the word itself (e.g., after splitting).
*   **Split Word**: Use the LLM to find different senses of a word and split it into multiple entries.
*   **Navigation**: Move between words with "Prev" and "Next" buttons.
*   **Card Type**: Choose between "Basic", "Reverse", or "Skip" for each word.

When you are done, the script will automatically write the `anki_basic.csv` and `anki_basic_reversed.csv` files.

### ⌨️ CLI Mode (Recommended for Speed)

The CLI mode is designed for quickly processing a list of words with minimal user interaction.

**To run in CLI mode:**

```bash
python anki_generator.py path/to/your/words.txt
```

**With a context file:**

```bash
python anki_generator.py path/to/your/words.txt path/to/your/book.epub
```

For each word, the script will:
1.  Fetch definitions from Cambridge Dictionary.
2.  Prompt you to choose a definition, generate one with the LLM, or skip the word.
3.  Generate an example sentence based on the chosen definition.
4.  Ask whether to create a basic, reversed, or no card.

### ⚡ Pre-generation Option

For both modes, you can use the `--pregen-llm` flag to generate definitions for all words in your list *before* starting the interactive session. This is highly recommended for larger lists as it speeds up the process significantly.

**GUI with pre-generation:**
```bash
python anki_generator.py --gui --pregen-llm
```

**CLI with pre-generation:**
```bash
python anki_generator.py --pregen-llm path/to/your/words.txt
```

## 📦 Output Files

The script generates up to two files in the same directory:
*   `anki_basic.csv`: For standard front/back cards.
*   `anki_basic_reversed.csv`: For reversed cards.

These files are formatted for direct import into Anki.

### How to Import into Anki

1.  Open Anki and select `File > Import...`.
2.  Choose the generated `.csv` file.
3.  In the import dialog:
    *   Choose the correct **Deck** and **Note Type** (e.g., "Basic" or "Basic (and reversed card)").
    *   Ensure "Allow HTML in fields" is **checked**.
    *   Map `Field 1` to `Front` and `Field 2` to `Back`.
4.  Click "Import".