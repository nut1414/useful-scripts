#!/usr/bin/env python3
"""
EPUB Chapter Extractor

This script extracts chapters from an EPUB file into separate folders.
Each chapter will be placed in its own folder with associated resources.
"""

import os
import zipfile
import xml.etree.ElementTree as ET
import shutil
import argparse
from pathlib import Path
import re
from urllib.parse import unquote
from html import unescape


class EPUBExtractor:
    def __init__(self, epub_path, output_dir):
        self.epub_path = Path(epub_path)
        self.output_dir = Path(output_dir)
        self.temp_dir = self.output_dir / "temp_extracted"
        self.chapters = []
        self.resources = {}
        self.source_dir = None  # Will hold the directory to work with
        self.is_extracted_folder = False
        
    def detect_input_type(self):
        """Detect if input is an EPUB file or an already extracted folder"""
        if self.epub_path.is_file() and self.epub_path.suffix.lower() == '.epub':
            self.is_extracted_folder = False
            print(f"Detected EPUB file: {self.epub_path}")
        elif self.epub_path.is_dir():
            # Check if it looks like an extracted EPUB (has META-INF and mimetype)
            meta_inf = self.epub_path / "META-INF"
            mimetype = self.epub_path / "mimetype"
            if meta_inf.exists() and mimetype.exists():
                self.is_extracted_folder = True
                self.source_dir = self.epub_path
                print(f"Detected extracted EPUB folder: {self.epub_path}")
            else:
                raise ValueError(f"Directory {self.epub_path} does not appear to be an extracted EPUB")
        else:
            raise FileNotFoundError(f"Input path not found or not recognized: {self.epub_path}")
        
    def extract_epub(self):
        """Extract EPUB file to temporary directory (only if needed)"""
        if self.is_extracted_folder:
            print(f"Using already extracted EPUB folder: {self.source_dir}")
            return
        
        print(f"Extracting EPUB: {self.epub_path}")
        
        if not self.epub_path.exists():
            raise FileNotFoundError(f"EPUB file not found: {self.epub_path}")
        
        # Create temporary extraction directory
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        
        # Extract EPUB (which is a ZIP file)
        with zipfile.ZipFile(self.epub_path, 'r') as zip_ref:
            zip_ref.extractall(self.temp_dir)
        
        self.source_dir = self.temp_dir
        print(f"Extracted to: {self.temp_dir}")
    
    def find_content_opf(self):
        """Find the content.opf file which contains the book structure"""
        # First check container.xml for the path
        container_path = self.source_dir / "META-INF" / "container.xml"
        
        if container_path.exists():
            tree = ET.parse(container_path)
            root = tree.getroot()
            
            # Look for the rootfile path
            for rootfile in root.findall(".//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile"):
                opf_path = rootfile.get("full-path")
                if opf_path:
                    return self.source_dir / opf_path
        
        # Fallback: search for .opf files
        for opf_file in self.source_dir.rglob("*.opf"):
            return opf_file
        
        raise FileNotFoundError("Could not find content.opf file")
    
    def parse_opf_file(self, opf_path):
        """Parse the OPF file to get chapter information"""
        print(f"Parsing OPF file: {opf_path}")
        
        tree = ET.parse(opf_path)
        root = tree.getroot()
        
        # Get the base directory of the OPF file
        base_dir = opf_path.parent
        
        # Find all manifest items
        manifest_items = {}
        for item in root.findall(".//{http://www.idpf.org/2007/opf}item"):
            item_id = item.get("id")
            href = item.get("href")
            media_type = item.get("media-type")
            
            if item_id and href:
                manifest_items[item_id] = {
                    "href": href,
                    "media_type": media_type,
                    "full_path": base_dir / href
                }
        
        # Find spine items (reading order)
        spine_items = []
        for itemref in root.findall(".//{http://www.idpf.org/2007/opf}itemref"):
            idref = itemref.get("idref")
            if idref in manifest_items:
                spine_items.append(manifest_items[idref])
        
        # Store all spine items (not just chapters)
        self.spine_items = spine_items
        
        # Filter for HTML/XHTML chapters
        chapters = []
        for item in spine_items:
            if item["media_type"] in ["application/xhtml+xml", "text/html"]:
                chapters.append(item)
        
        self.chapters = chapters
        self.resources = {k: v for k, v in manifest_items.items() 
                         if v["media_type"] not in ["application/xhtml+xml", "text/html"]}
        
        print(f"Found {len(chapters)} spine items")
        return chapters
    
    def parse_navigation_file(self, opf_path):
        """Parse navigation-documents.xhtml to get chapter boundaries"""
        base_dir = opf_path.parent
        nav_path = base_dir / "navigation-documents.xhtml"
        
        if not nav_path.exists():
            print("Warning: navigation-documents.xhtml not found, using all spine items")
            return []
        
        print(f"Parsing navigation file: {nav_path}")
        
        try:
            tree = ET.parse(nav_path)
            root = tree.getroot()
            
            # Find TOC navigation
            namespaces = {
                'xhtml': 'http://www.w3.org/1999/xhtml',
                'epub': 'http://www.idpf.org/2007/ops'
            }
            
            # Try to find nav with epub:type="toc"
            toc_nav = None
            for nav in root.findall(".//xhtml:nav", namespaces):
                epub_type = nav.get('{http://www.idpf.org/2007/ops}type')
                if epub_type == 'toc':
                    toc_nav = nav
                    break
            
            # Fallback to first nav element
            if toc_nav is None:
                toc_nav = root.find(".//xhtml:nav", namespaces)
            
            chapter_markers = []
            if toc_nav is not None:
                # Find all links in the TOC
                for link in toc_nav.findall(".//xhtml:a", namespaces):
                    href = link.get("href")
                    text = link.text
                    if href and text:
                        # Extract filename and anchor
                        if '#' in href:
                            file_part, anchor = href.split('#', 1)
                        else:
                            file_part, anchor = href, None
                        
                        # Skip non-chapter items (cover, toc, etc.)
                        if any(x in text.lower() for x in ['表紙', '目次', '奥付', 'cover', 'toc']):
                            continue
                        
                        chapter_markers.append({
                            'title': text.strip(),
                            'file': file_part,
                            'anchor': anchor,
                            'href': href
                        })
            
            print(f"Found {len(chapter_markers)} chapter markers")
            return chapter_markers
            
        except Exception as e:
            print(f"Error parsing navigation file: {e}")
            return []
    
    def html_to_text(self, html_content):
        """Convert HTML content to plain text"""
        # Remove script and style elements
        html_content = re.sub(r'<script[^>]*>.*?</script>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
        html_content = re.sub(r'<style[^>]*>.*?</style>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
        
        # Replace common HTML entities
        html_content = unescape(html_content)
        
        # Replace line breaks and paragraphs
        html_content = re.sub(r'<br[^>]*>', '\n', html_content, flags=re.IGNORECASE)
        html_content = re.sub(r'</p>', '\n\n', html_content, flags=re.IGNORECASE)
        html_content = re.sub(r'<p[^>]*>', '', html_content, flags=re.IGNORECASE)
        
        # Replace headings
        html_content = re.sub(r'<h[1-6][^>]*>', '\n\n', html_content, flags=re.IGNORECASE)
        html_content = re.sub(r'</h[1-6]>', '\n\n', html_content, flags=re.IGNORECASE)
        
        # Replace div tags
        html_content = re.sub(r'<div[^>]*>', '\n', html_content, flags=re.IGNORECASE)
        html_content = re.sub(r'</div>', '\n', html_content, flags=re.IGNORECASE)
        
        # Remove all remaining HTML tags
        html_content = re.sub(r'<[^>]+>', '', html_content)
        
        # Clean up whitespace
        html_content = re.sub(r'\n\s*\n', '\n\n', html_content)
        html_content = re.sub(r'[ \t]+', ' ', html_content)
        
        return html_content.strip()
    
    def sanitize_filename(self, filename):
        """Sanitize filename for cross-platform compatibility"""
        # Remove or replace invalid characters
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        filename = filename.strip('. ')
        return filename[:100]  # Limit length
    

    
    def create_chapter_text_files(self, chapter_markers):
        """Create text files for each chapter based on navigation markers"""
        print("Creating chapter text files...")
        
        if not chapter_markers:
            print("No chapter markers found, extracting all spine items as individual files")
            self.extract_all_spine_items()
            return
        
        # Create a mapping of filenames to spine items
        spine_by_filename = {}
        for item in self.spine_items:
            if item["media_type"] in ["application/xhtml+xml", "text/html"]:
                filename = Path(item["href"]).name
                spine_by_filename[filename] = item
        
        # Extract chapters based on markers
        for i, marker in enumerate(chapter_markers):
            print(f"Processing chapter {i+1}: {marker['title']}")
            
            # Find the starting file
            start_file = marker['file']
            if start_file.startswith('xhtml/'):
                start_file = start_file[6:]  # Remove 'xhtml/' prefix
            
            # Find the next chapter start (if any)
            next_start_file = None
            if i + 1 < len(chapter_markers):
                next_start_file = chapter_markers[i + 1]['file']
                if next_start_file.startswith('xhtml/'):
                    next_start_file = next_start_file[6:]
            
            # Collect all files for this chapter
            chapter_files = self.get_chapter_files(start_file, next_start_file, spine_by_filename)
            
            # Extract text content
            chapter_text = self.extract_chapter_text(chapter_files)
            
            # Save to text file
            title = self.sanitize_filename(marker['title'])
            filename = f"Chapter_{i+1:02d}_{title}.txt"
            output_file = self.output_dir / filename
            
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(f"# {marker['title']}\n\n")
                f.write(chapter_text)
            
            print(f"Created: {filename}")
    
    def get_chapter_files(self, start_file, next_start_file, spine_by_filename):
        """Get all files that belong to a chapter"""
        files = []
        
        # Find the starting index in spine
        start_index = None
        for i, item in enumerate(self.spine_items):
            if item["media_type"] in ["application/xhtml+xml", "text/html"]:
                filename = Path(item["href"]).name
                if filename == start_file:
                    start_index = i
                    break
        
        if start_index is None:
            print(f"Warning: Could not find start file: {start_file}")
            return files
        
        # Find the ending index
        end_index = len(self.spine_items)
        if next_start_file:
            for i in range(start_index + 1, len(self.spine_items)):
                item = self.spine_items[i]
                if item["media_type"] in ["application/xhtml+xml", "text/html"]:
                    filename = Path(item["href"]).name
                    if filename == next_start_file:
                        end_index = i
                        break
        
        # Collect files from start to end
        for i in range(start_index, end_index):
            item = self.spine_items[i]
            if item["media_type"] in ["application/xhtml+xml", "text/html"]:
                files.append(item)
        
        return files
    
    def extract_chapter_text(self, chapter_files):
        """Extract and combine text from chapter files"""
        chapter_text = ""
        
        for file_item in chapter_files:
            file_path = file_item["full_path"]
            
            if not file_path.exists():
                print(f"Warning: File not found: {file_path}")
                continue
            
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    html_content = f.read()
                
                # Convert HTML to text
                text_content = self.html_to_text(html_content)
                
                if text_content.strip():
                    chapter_text += text_content + "\n\n"
                    
            except Exception as e:
                print(f"Error reading file {file_path}: {e}")
        
        return chapter_text.strip()
    
    def extract_all_spine_items(self):
        """Extract all spine items as individual text files (fallback)"""
        print("Extracting all spine items...")
        
        for i, item in enumerate(self.spine_items):
            if item["media_type"] in ["application/xhtml+xml", "text/html"]:
                file_path = item["full_path"]
                
                if not file_path.exists():
                    continue
                
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        html_content = f.read()
                    
                    text_content = self.html_to_text(html_content)
                    
                    if text_content.strip():
                        # Use filename as title
                        title = self.sanitize_filename(file_path.stem)
                        filename = f"Part_{i+1:02d}_{title}.txt"
                        output_file = self.output_dir / filename
                        
                        with open(output_file, 'w', encoding='utf-8') as f:
                            f.write(text_content)
                        
                        print(f"Created: {filename}")
                        
                except Exception as e:
                    print(f"Error processing file {file_path}: {e}")
    

    
    def create_index_file(self, chapter_markers):
        """Create an index.txt file listing all chapters"""
        index_path = self.output_dir / "index.txt"
        
        content = f"EPUB Chapters\n"
        content += f"Extracted from: {self.epub_path.name}\n"
        content += f"Total chapters: {len(chapter_markers)}\n\n"
        content += "=" * 50 + "\n\n"
        
        # Add list of chapters
        for i, marker in enumerate(chapter_markers, 1):
            title = self.sanitize_filename(marker['title'])
            filename = f"Chapter_{i:02d}_{title}.txt"
            content += f"Chapter {i}: {marker['title']}\n"
            content += f"File: {filename}\n\n"
        
        with open(index_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"Created index file: {index_path}")
    
    def cleanup(self):
        """Remove temporary extraction directory (only if we created one)"""
        if not self.is_extracted_folder and self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
            print("Cleaned up temporary files")
    
    def extract_chapters(self):
        """Main extraction process"""
        try:
            # Create output directory
            self.output_dir.mkdir(parents=True, exist_ok=True)
            
            # Detect input type (file or folder)
            self.detect_input_type()
            
            # Extract EPUB (only if it's a file)
            self.extract_epub()
            
            # Find and parse OPF file
            opf_path = self.find_content_opf()
            self.parse_opf_file(opf_path)
            
            # Parse navigation to get chapter markers
            chapter_markers = self.parse_navigation_file(opf_path)
            
            # Create chapter text files
            self.create_chapter_text_files(chapter_markers)
            
            # Create index
            if chapter_markers:
                self.create_index_file(chapter_markers)
            
            print(f"\nExtraction complete! Chapters saved to: {self.output_dir}")
            if chapter_markers:
                print(f"Total chapters extracted: {len(chapter_markers)}")
            else:
                print(f"Total files extracted: {len([f for f in self.output_dir.iterdir() if f.suffix == '.txt'])}")
            
        except Exception as e:
            print(f"Error during extraction: {e}")
            raise
        finally:
            self.cleanup()


def main():
    parser = argparse.ArgumentParser(description="Extract EPUB chapters into separate folders")
    parser.add_argument("epub_path", help="Path to the EPUB file or extracted EPUB folder")
    parser.add_argument("-o", "--output", default="extracted_chapters", 
                       help="Output directory (default: extracted_chapters)")
    
    args = parser.parse_args()
    
    try:
        extractor = EPUBExtractor(args.epub_path, args.output)
        extractor.extract_chapters()
    except Exception as e:
        print(f"Failed to extract EPUB: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main()) 