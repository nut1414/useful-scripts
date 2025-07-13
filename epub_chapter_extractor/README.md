# EPUB Chapter Extractor

A powerful Python script that extracts chapters from EPUB files into organized text files. Perfect for creating readable, searchable text versions of your digital books while preserving chapter structure and organization.

## ✨ Features

- **Single & Bulk Processing**: Extract one EPUB or process entire directories
- **Smart Chapter Detection**: Automatically detects chapter boundaries using navigation files, TOC, or embedded content
- **Subchapter Support**: Option to extract numbered subchapters into separate files
- **Furigana Handling**: Choose to show or hide Japanese furigana (ruby text)
- **Multiple Input Types**: Works with `.epub` files or already extracted EPUB folders
- **Recursive Processing**: Process EPUBs in subdirectories
- **Cross-Platform**: Works on Windows, macOS, and Linux
- **Organized Output**: Creates clean folder structures with proper file naming
- **Index Generation**: Automatically creates table of contents for each extraction
- **Format Support**: Handles both old and new EPUB formats

## 🚀 Quick Start

### Basic Usage

```bash
# Extract a single EPUB file
python3 epub_chapter_extractor.py "my_book.epub"

# Extract to specific output directory
python3 epub_chapter_extractor.py "my_book.epub" -o "extracted_books"

# Bulk process all EPUBs in a directory
python3 epub_chapter_extractor.py "/path/to/epub/folder" --bulk

# Recursive bulk processing with subchapters
python3 epub_chapter_extractor.py "/path/to/epub/folder" --bulk --recursive --subchapters
```

## 📋 Requirements

- Python 3.6 or higher

## 📥 Installation

1. **Download the script:**

Clone this repo.

2. **Make executable (optional):**

   ```bash
   chmod +x epub_chapter_extractor.py
   ```

3. **Create requirements.txt (if needed):**
   ```bash
   echo "# No external dependencies required - uses Python standard library only" > requirements.txt
   ```

## 🎯 Usage Examples

### Single File Extraction

```bash
# Basic extraction
python3 epub_chapter_extractor.py "book.epub"

# With custom output directory
python3 epub_chapter_extractor.py "book.epub" -o "my_books"

# Extract subchapters into separate files
python3 epub_chapter_extractor.py "book.epub" --subchapters

# Show furigana in Japanese text
python3 epub_chapter_extractor.py "japanese_novel.epub" --furigana
```

### Bulk Processing

```bash
# Process all EPUBs in current directory
python3 epub_chapter_extractor.py . --bulk

# Process recursively through subdirectories
python3 epub_chapter_extractor.py "/path/to/library" --bulk --recursive

# Bulk process with all options
python3 epub_chapter_extractor.py "/epub/library" --bulk --recursive --subchapters --furigana -o "text_library"
```

### Working with Extracted EPUBs

```bash
# Use an already extracted EPUB folder
python3 epub_chapter_extractor.py "/path/to/extracted/epub/folder"
```

## ⚙️ Command Line Options

| Option          | Description                                                             |
| --------------- | ----------------------------------------------------------------------- |
| `epub_path`     | Path to EPUB file, extracted folder, or directory containing EPUBs      |
| `-o, --output`  | Output directory (default: `extracted_chapters`)                        |
| `--subchapters` | Extract numbered subchapters into separate files within chapter folders |
| `--furigana`    | Show furigana in parentheses format (e.g., 漢字（かんじ）)              |
| `--bulk`        | Process all EPUB files in the input directory                           |
| `--recursive`   | Search for EPUB files recursively in subdirectories (use with `--bulk`) |

## 📁 Output Structure

### Single File Mode (default)

```
extracted_chapters/
├── Chapter_01_Chapter_Title.txt
├── Chapter_02_Another_Chapter.txt
├── Chapter_03_Final_Chapter.txt
└── index.txt
```

### Subchapter Mode (`--subchapters`)

```
extracted_chapters/
├── Chapter_01_First_Chapter/
│   ├── [1] Chapter_01_First_Chapter.txt
│   ├── [2] Chapter_01_First_Chapter.txt
│   └── [3] Chapter_01_First_Chapter.txt
├── Chapter_02_Second_Chapter/
│   ├── [1] Chapter_02_Second_Chapter.txt
│   └── [2] Chapter_02_Second_Chapter.txt
└── index.txt
```

### Bulk Processing Structure

```
output_directory/
├── Series_Name/
│   ├── Volume_1/
│   │   ├── Chapter_01_Title.txt
│   │   ├── Chapter_02_Title.txt
│   │   └── index.txt
│   └── Volume_2/
│       ├── Chapter_01_Title.txt
│       └── index.txt
└── Another_Series/
    └── Volume_1/
        ├── Chapter_01_Title.txt
        └── index.txt
```

## 🌍 Language Support

### Japanese Text Features

- **Furigana Handling**: Choose to show furigana as `漢字（かんじ）` or hide it completely
- **Character Support**: Full Unicode support for Japanese, Chinese, Korean characters
- **Filename Sanitization**: Automatically handles special characters in chapter titles

### Supported EPUB Formats

- **EPUB 2.0** and **EPUB 3.0**
- **Old format**: `item/standard.opf` structure
- **New format**: `content.opf` in root or `OEBPS/` directory
- **Navigation files**: `nav.xhtml`, `navigation-documents.xhtml`, `toc.ncx`
- **Embedded TOC**: Automatically detects table of contents in content files

## 🔧 Advanced Features

### Chapter Detection Methods

1. **Navigation Files**: `nav.xhtml`, `navigation-documents.xhtml`
2. **TOC Files**: `toc.ncx`
3. **Embedded TOC**: Searches content for chapter links
4. **Fallback**: Uses all spine items if no structure found

### File Handling

- **Automatic cleanup**: Removes temporary files after extraction
- **Cross-platform paths**: Works on Windows, macOS, and Linux
- **Safe filenames**: Automatically sanitizes chapter titles for filesystem compatibility
- **Encoding detection**: Handles various text encodings properly

## 📊 Example Output

### Terminal Output

```
Found 15 EPUB file(s) to process

============================================================
Processing EPUB 1/15: my_novel_v1.epub
============================================================
Detected EPUB file: /path/to/my_novel_v1.epub
Extracting EPUB: /path/to/my_novel_v1.epub
Parsing OPF file: temp_extracted/content.opf
Found 12 spine items
Found 8 chapter markers from toc.ncx
Creating chapter text files...
Processing chapter 1: Prologue
Created: Chapter_01_Prologue.txt
Processing chapter 2: The Beginning
Created: Chapter_02_The_Beginning.txt
...
Created index file: output/my_novel_v1/index.txt

Extraction complete! Chapters saved to: output/my_novel_v1
Total chapters extracted: 8
✓ Successfully extracted: my_novel_v1.epub
```

### Generated Index File

```
EPUB Chapters
Extracted from: my_novel_v1.epub
Total chapters: 8
Extraction mode: Single file per chapter

==================================================

Chapter 1: Prologue
File: Chapter_01_Prologue.txt

Chapter 2: The Beginning
File: Chapter_02_The_Beginning.txt

Chapter 3: Rising Action
File: Chapter_03_Rising_Action.txt
...
```

## ❗ Troubleshooting

### Common Issues

**"No EPUB files found"**

- Check file extensions (must be `.epub`)
- Ensure files aren't hidden (names starting with `.`)
- Use `--recursive` flag for subdirectories

**"Could not find content.opf file"**

- EPUB file is not compatible.
- Try extracting manually first, then use the extracted folder

**"Warning: No navigation file found"**

- Script will fallback to extracting all spine items
- Output may have more files but will still work

### Performance Tips

- Use `--bulk` for multiple files (much faster than individual processing)
- Enable `--recursive` only when needed

---

**Happy reading!** 📚✨
