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
import math


class EPUBExtractor:
    def __init__(self, epub_path, output_dir, extract_subchapters=False, show_furigana=False, split_no_subchapters=False):
        self.epub_path = Path(epub_path)
        self.output_dir = Path(output_dir)
        self.temp_dir = self.output_dir / "temp_extracted"
        self.chapters = []
        self.resources = {}
        self.source_dir = None  # Will hold the directory to work with
        self.is_extracted_folder = False
        self.extract_subchapters = extract_subchapters
        self.show_furigana = show_furigana
        self.split_no_subchapters = split_no_subchapters
        
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
        
        # Fallback: search for .opf files in common locations
        # Check for content.opf in root (new format)
        content_opf_root = self.source_dir / "content.opf"
        if content_opf_root.exists():
            return content_opf_root
            
        # Check for standard.opf in item directory (old format)
        standard_opf = self.source_dir / "item" / "standard.opf"
        if standard_opf.exists():
            return standard_opf
        
        # General fallback: search for any .opf files
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
                # Handle relative paths correctly for both formats
                if href.startswith("OEBPS/") or href.startswith("item/"):
                    # Path already includes subdirectory
                    full_path = base_dir / href
                else:
                    # Check if the file exists in common subdirectories
                    possible_paths = [
                        base_dir / href,  # Direct path from OPF directory
                        base_dir / "OEBPS" / href,  # New format
                        base_dir / "item" / "xhtml" / href,  # Old format
                    ]
                    
                    full_path = None
                    for path in possible_paths:
                        if path.exists():
                            full_path = path
                            break
                    
                    # If not found, use the first possibility (direct path)
                    if full_path is None:
                        full_path = possible_paths[0]
                
                manifest_items[item_id] = {
                    "href": href,
                    "media_type": media_type,
                    "full_path": full_path
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
        """Parse navigation file to get chapter boundaries (supports navigation-documents.xhtml, nav.xhtml, and toc.ncx)"""
        base_dir = opf_path.parent
        chapter_markers = []
        
        # Try nav.xhtml first (standard EPUB3 format)
        nav_path = base_dir / "nav.xhtml"
        if nav_path.exists():
            print(f"Parsing navigation file: {nav_path}")
            chapter_markers = self._parse_navigation_xhtml(nav_path)
            if chapter_markers:
                return chapter_markers
        
        # Try navigation-documents.xhtml (old format)
        nav_path = base_dir / "navigation-documents.xhtml"
        if not nav_path.exists():
            # Check in item subdirectory for old format
            nav_path = base_dir / "item" / "navigation-documents.xhtml"
        
        if nav_path.exists():
            print(f"Parsing navigation file: {nav_path}")
            chapter_markers = self._parse_navigation_xhtml(nav_path)
            if chapter_markers:
                return chapter_markers
        
        # Try toc.ncx (alternative format)
        toc_path = base_dir / "toc.ncx"
        if toc_path.exists():
            print(f"Parsing toc.ncx file: {toc_path}")
            chapter_markers = self._parse_toc_ncx(toc_path, base_dir)
            if chapter_markers:
                return chapter_markers
        
        # Fallback: Try to find embedded table of contents in content files
        print("Standard navigation files didn't provide chapter structure, searching for embedded TOC...")
        chapter_markers = self._parse_embedded_toc(base_dir)
        if chapter_markers:
            return chapter_markers
        
        print("Warning: No navigation file found, using all spine items")
        return []
    
    def _parse_navigation_xhtml(self, nav_path):
        """Parse navigation-documents.xhtml file"""
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
                        
                        # Remove OEBPS/ prefix if present for consistency
                        if file_part.startswith('OEBPS/'):
                            file_part = file_part[6:]
                        
                        # Skip non-chapter items (cover, toc, etc.)
                        if any(x in text.lower() for x in ['表紙', '目次', '奥付', 'cover', 'toc', 'contents']):
                            continue
                        
                        chapter_markers.append({
                            'title': text.strip(),
                            'file': file_part,
                            'anchor': anchor,
                            'href': href
                        })
            
            print(f"Found {len(chapter_markers)} chapter markers from navigation file")
            return chapter_markers
            
        except Exception as e:
            print(f"Error parsing navigation file: {e}")
            return []
    
    def _parse_toc_ncx(self, toc_path, base_dir):
        """Parse toc.ncx file"""
        try:
            tree = ET.parse(toc_path)
            root = tree.getroot()
            
            # Find all navPoints
            namespace = {'ncx': 'http://www.daisy.org/z3986/2005/ncx/'}
            chapter_markers = []
            
            for nav_point in root.findall(".//ncx:navPoint", namespace):
                # Get the title
                nav_label = nav_point.find(".//ncx:navLabel/ncx:text", namespace)
                content = nav_point.find(".//ncx:content", namespace)
                
                if nav_label is not None and content is not None:
                    title = nav_label.text
                    src = content.get("src")
                    
                    if title and src:
                        # Extract filename and anchor
                        if '#' in src:
                            file_part, anchor = src.split('#', 1)
                        else:
                            file_part, anchor = src, None
                        
                        # Remove OEBPS/ prefix if present for consistency
                        if file_part.startswith('OEBPS/'):
                            file_part = file_part[6:]
                        
                        # Skip non-chapter items
                        if any(x in title.lower() for x in ['表紙', '目次', '奥付', 'cover', 'toc', 'contents']):
                            continue
                        
                        chapter_markers.append({
                            'title': title.strip(),
                            'file': file_part,
                            'anchor': anchor,
                            'href': src
                        })
            
            print(f"Found {len(chapter_markers)} chapter markers from toc.ncx")
            return chapter_markers
            
        except Exception as e:
            print(f"Error parsing toc.ncx file: {e}")
            return []

    def _parse_embedded_toc(self, base_dir):
        """Parse embedded table of contents from content files"""
        try:
            chapter_markers = []
            
            # Look through spine items for potential TOC files
            for item in self.spine_items:
                if item["media_type"] in ["application/xhtml+xml", "text/html"]:
                    file_path = item["full_path"]
                    
                    if not file_path.exists():
                        continue
                    
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                        
                        # Look for files that contain "CONTENTS" or multiple chapter links
                        if 'CONTENTS' in content or self._has_chapter_links(content):
                            print(f"Found potential embedded TOC in: {file_path.name}")
                            markers = self._extract_chapter_links(content, base_dir)
                            if markers:
                                chapter_markers.extend(markers)
                    
                    except Exception as e:
                        print(f"Error reading file {file_path}: {e}")
                        continue
            
            # Remove duplicates and sort by file order in spine
            if chapter_markers:
                chapter_markers = self._deduplicate_and_sort_markers(chapter_markers)
                print(f"Found {len(chapter_markers)} chapter markers from embedded TOC")
            
            return chapter_markers
            
        except Exception as e:
            print(f"Error parsing embedded TOC: {e}")
            return []
    
    def _has_chapter_links(self, content):
        """Check if content has multiple chapter-like links"""
        import re
        
        # Look for links with chapter-like text
        chapter_patterns = [
            r'<a[^>]*href="[^"]*"[^>]*>[^<]*(?:第[一二三四五六七八九十\d]+章|Chapter\s*\d+|プロローグ|エピローグ|あとがき)',
            r'<a[^>]*href="[^"]*"[^>]*>[^<]*(?:章|chapter|prologue|epilogue)',
        ]
        
        chapter_count = 0
        for pattern in chapter_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            chapter_count += len(matches)
        
        return chapter_count >= 3  # At least 3 chapter-like links
    
    def _extract_chapter_links(self, content, base_dir):
        """Extract chapter links from HTML content"""
        import re
        from xml.etree import ElementTree as ET
        
        try:
            # Parse as XML/HTML to extract links
            # Remove doctype and other problematic elements for parsing
            clean_content = re.sub(r'<!DOCTYPE[^>]*>', '', content)
            
            # Parse the content
            root = ET.fromstring(clean_content)
            
            chapter_markers = []
            
            # Find all links
            for link in root.iter():
                if link.tag.endswith('a'):  # Handle namespaced tags
                    href = link.get('href')
                    text = ''.join(link.itertext()).strip()
                    
                    if href and text and self._is_chapter_link(text):
                        # Extract filename and anchor
                        if '#' in href:
                            file_part, anchor = href.split('#', 1)
                        else:
                            file_part, anchor = href, None
                        
                        # Handle relative paths
                        if file_part.startswith('OEBPS/'):
                            file_part = file_part[6:]  # Remove OEBPS/ prefix
                        
                        chapter_markers.append({
                            'title': text.strip(),
                            'file': file_part,
                            'anchor': anchor,
                            'href': href
                        })
            
            return chapter_markers
            
        except Exception as e:
            print(f"Error extracting chapter links: {e}")
            # Fallback to regex parsing
            return self._extract_chapter_links_regex(content)
    
    def _extract_chapter_links_regex(self, content):
        """Fallback regex-based chapter link extraction"""
        import re
        
        chapter_markers = []
        
        # Pattern to match chapter links
        link_pattern = r'<a[^>]*href="([^"]*)"[^>]*>([^<]*)</a>'
        matches = re.findall(link_pattern, content, re.IGNORECASE)
        
        for href, text in matches:
            text = text.strip()
            if self._is_chapter_link(text):
                # Extract filename and anchor
                if '#' in href:
                    file_part, anchor = href.split('#', 1)
                else:
                    file_part, anchor = href, None
                
                # Handle relative paths
                if file_part.startswith('OEBPS/'):
                    file_part = file_part[6:]  # Remove OEBPS/ prefix
                
                chapter_markers.append({
                    'title': text.strip(),
                    'file': file_part,
                    'anchor': anchor,
                    'href': href
                })
        
        return chapter_markers
    
    def _is_chapter_link(self, text):
        """Check if link text represents a chapter"""
        if not text:
            return False
        
        # Skip common non-chapter items
        skip_items = ['表紙', '目次', '奥付', 'cover', 'toc', 'contents', '解説']
        if any(skip in text.lower() for skip in skip_items):
            return False
        
        # Look for chapter-like patterns
        chapter_patterns = [
            r'第[一二三四五六七八九十\d]+章',  # Japanese chapters
            r'Chapter\s*\d+',                 # English chapters
            r'プロローグ',                     # Prologue
            r'エピローグ',                     # Epilogue  
            r'あとがき',                       # Afterword
            r'終\s*章',                       # Final chapter
            r'[一二三四五六七八九十\d]+章',     # Chapters without 第
        ]
        
        for pattern in chapter_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        
        return False
    
    def _deduplicate_and_sort_markers(self, markers):
        """Remove duplicates and sort markers by spine order"""
        seen = set()
        unique_markers = []
        
        for marker in markers:
            key = (marker['file'], marker.get('anchor', ''))
            if key not in seen:
                seen.add(key)
                unique_markers.append(marker)
        
        # Sort by spine order if possible
        spine_order = {Path(item['href']).name: i for i, item in enumerate(self.spine_items)}
        
        def sort_key(marker):
            filename = marker['file']
            return spine_order.get(filename, 999)
        
        unique_markers.sort(key=sort_key)
        return unique_markers
    
    def process_furigana(self, html_content):
        """Process furigana based on the show_furigana flag"""
        if self.show_furigana:
            # Convert <ruby>漢字<rt>かんじ</rt></ruby> to 漢字（かんじ）
            def replace_ruby(match):
                ruby_content = match.group(1)
                # Extract kanji and furigana pairs
                kanji_parts = []
                furigana_parts = []
                
                # Split by <rt> tags to get kanji and furigana
                parts = re.split(r'<rt>(.*?)</rt>', ruby_content)
                for i in range(0, len(parts), 2):
                    if i < len(parts):
                        kanji_parts.append(parts[i])
                    if i + 1 < len(parts):
                        furigana_parts.append(parts[i + 1])
                
                # Combine kanji and furigana
                kanji_text = ''.join(kanji_parts)
                furigana_text = ''.join(furigana_parts)
                
                if furigana_text:
                    return f"{kanji_text}（{furigana_text}）"
                else:
                    return kanji_text
            
            # Replace ruby tags with furigana in parentheses
            html_content = re.sub(r'<ruby>(.*?)</ruby>', replace_ruby, html_content, flags=re.DOTALL)
        else:
            # Remove furigana, keep only kanji
            def replace_ruby_kanji_only(match):
                ruby_content = match.group(1)
                # Remove all <rt>...</rt> tags to keep only kanji
                kanji_only = re.sub(r'<rt>.*?</rt>', '', ruby_content)
                return kanji_only
            
            # Replace ruby tags with kanji only
            html_content = re.sub(r'<ruby>(.*?)</ruby>', replace_ruby_kanji_only, html_content, flags=re.DOTALL)
        
        return html_content
    
    def html_to_text(self, html_content):
        """Convert HTML content to plain text"""
        # Process furigana first
        html_content = self.process_furigana(html_content)
        
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
    
    def find_subchapters_in_html(self, html_content):
        """Find subchapter markers in HTML content"""
        # Look for patterns like:
        # <div class="start-4em"><p>１</p></div>
        # <span class="gfont">１</span>
        # <div class="start-8em"><p><span class="font-1em10 tcy">1</span></p></div>
        # <p>　　　　１</p> (Japanese style with full-width spaces)
        
        subchapters = []
        
        # Pattern 1: <div class="start-4em"><p>１</p></div>
        pattern1 = r'<div[^>]*class="start-4em"[^>]*>\s*<p[^>]*>([１２３４５６７８９０\d]+)</p>\s*</div>'
        matches1 = list(re.finditer(pattern1, html_content, re.IGNORECASE))
        
        # Pattern 2: <span class="gfont">１</span>
        pattern2 = r'<span[^>]*class="gfont"[^>]*>([１２３４５６７８９０\d]+)</span>'
        matches2 = list(re.finditer(pattern2, html_content, re.IGNORECASE))
        
        # Pattern 3: <p>　　　　<span class="gfont">１</span></p> (with indentation)
        pattern3 = r'<p[^>]*>\s*　+\s*<span[^>]*class="gfont"[^>]*>([１２３４５６７８９０\d]+)</span>\s*</p>'
        matches3 = list(re.finditer(pattern3, html_content, re.IGNORECASE))
        
        # Pattern 4: <div class="start-8em"><p><span class="font-1em10 tcy">1</span></p></div>
        pattern4 = r'<div[^>]*class="start-8em"[^>]*>\s*<p[^>]*>\s*<span[^>]*class="font-1em10[^"]*"[^>]*>([１２３４５６７８９０\d]+)</span>\s*</p>\s*</div>'
        matches4 = list(re.finditer(pattern4, html_content, re.IGNORECASE))
        
        # Pattern 5: <p>　　　　１</p> (Japanese style with full-width spaces and direct number)
        pattern5 = r'<p[^>]*>\s*　{2,}\s*([１２３４５６７８９０\d]+)\s*</p>'
        matches5 = list(re.finditer(pattern5, html_content, re.IGNORECASE))
        
        # Combine all matches and sort by position
        all_matches = []
        for match in matches1:
            all_matches.append(('pattern1', match))
        for match in matches2:
            all_matches.append(('pattern2', match))
        for match in matches3:
            all_matches.append(('pattern3', match))
        for match in matches4:
            all_matches.append(('pattern4', match))
        for match in matches5:
            all_matches.append(('pattern5', match))
        
        # Sort by start position
        all_matches.sort(key=lambda x: x[1].start())
        
        # Process matches to create subchapters
        for i, (pattern_type, match) in enumerate(all_matches):
            start_pos = match.start()
            end_pos = all_matches[i + 1][1].start() if i + 1 < len(all_matches) else len(html_content)
            
            # Extract the number
            number_text = match.group(1)
            # Convert Japanese numbers to Arabic if needed
            number_map = {'１': '1', '２': '2', '３': '3', '４': '4', '５': '5', 
                         '６': '6', '７': '7', '８': '8', '９': '9', '０': '0'}
            
            converted_number = ''
            for char in number_text:
                converted_number += number_map.get(char, char)
            
            # Skip if the number is not a valid subchapter number (e.g., not 1, 2, 3, etc.)
            try:
                chapter_num = int(converted_number)
                if chapter_num < 1 or chapter_num > 50:  # Reasonable range for subchapters
                    continue
            except ValueError:
                continue
            
            subchapters.append({
                'number': converted_number,
                'start_pos': start_pos,
                'end_pos': end_pos,
                'content': html_content[start_pos:end_pos],
                'pattern': pattern_type
            })
        
        # If we found subchapters, print debug info
        if subchapters:
            # Adjust first subchapter to include any content before its marker
            first_subchapter_marker_pos = all_matches[0][1].start()
            if first_subchapter_marker_pos > 0:
                first_subchapter_end_pos = subchapters[0]['end_pos']
                subchapters[0]['content'] = html_content[0:first_subchapter_end_pos]
                subchapters[0]['start_pos'] = 0
                
            print(f"  Found {len(subchapters)} subchapters using patterns: {set(s['pattern'] for s in subchapters)}")
        
        return subchapters

    def split_and_save_text(self, text_content, output_folder, file_prefix, chapter_title):
        """Splits text into manageable chunks and saves them."""
        CHUNK_SIZE = 15000  # Target size in characters
        
        total_len = len(text_content)
        num_chunks = math.ceil(total_len / CHUNK_SIZE)
        
        if num_chunks <= 1:
            # This case should ideally not be hit if called correctly, but as a safeguard:
            main_filename = f"[1] {file_prefix}.txt"
            main_file = output_folder / main_filename
            with open(main_file, 'w', encoding='utf-8') as f:
                f.write(f"# {chapter_title}\n\n")
                f.write(text_content)
            print(f"    Created: {main_filename}")
            return
            
        target_chunk_size = math.ceil(total_len / num_chunks)
        print(f"    Splitting into {num_chunks} chunks of ~{target_chunk_size} characters.")

        paragraphs = text_content.split('\n\n')
        
        chunks = []
        current_chunk_paras = []
        current_chunk_len = 0
        
        for p in paragraphs:
            p = p.strip()
            if not p:
                continue
            
            p_len = len(p)
            
            # If the current chunk is not empty and adding the new paragraph would make it too large,
            # finalize the current chunk.
            if current_chunk_paras and (current_chunk_len + p_len) > target_chunk_size:
                chunks.append("\n\n".join(current_chunk_paras))
                current_chunk_paras = [p]
                current_chunk_len = p_len
            else:
                # Add paragraph to the current chunk
                current_chunk_paras.append(p)
                # Add 2 for the '\n\n' that will join them
                current_chunk_len += p_len + 2
                
        # Add the last remaining chunk
        if current_chunk_paras:
            chunks.append("\n\n".join(current_chunk_paras))
            
        # Save the chunks to files
        for i, chunk in enumerate(chunks):
            filename = f"[{i + 1}] {file_prefix}.txt"
            output_file = output_folder / filename
            
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(f"# {chapter_title} - Part {i + 1}\n\n")
                f.write(chunk)
                
            print(f"    Created: {filename}")

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
            
            if self.extract_subchapters:
                # Create chapter folder and extract subchapters
                self.extract_chapter_with_subchapters(chapter_files, marker, i + 1)
            else:
                # Extract text content as single file
                chapter_text = self.extract_chapter_text(chapter_files)
                
                # Save to text file
                title = self.sanitize_filename(marker['title'])
                filename = f"Chapter_{i+1:02d}_{title}.txt"
                output_file = self.output_dir / filename
                
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(f"# {marker['title']}\n\n")
                    f.write(chapter_text)
                
                print(f"Created: {filename}")
    
    def extract_chapter_with_subchapters(self, chapter_files, marker, chapter_num):
        """Extract a chapter with subchapters into separate files in a folder"""
        title = self.sanitize_filename(marker['title'])
        chapter_folder_name = f"Chapter_{chapter_num:02d}_{title}"
        chapter_folder = self.output_dir / chapter_folder_name
        chapter_folder.mkdir(parents=True, exist_ok=True)
        
        print(f"  Creating chapter folder: {chapter_folder_name}")
        
        # Combine all HTML content for this chapter
        combined_html = ""
        for file_item in chapter_files:
            file_path = file_item["full_path"]
            
            if not file_path.exists():
                print(f"  Warning: File not found: {file_path}")
                continue
            
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    html_content = f.read()
                    combined_html += html_content + "\n"
            except Exception as e:
                print(f"  Error reading file {file_path}: {e}")
        
        # Find subchapters in the combined HTML
        subchapters = self.find_subchapters_in_html(combined_html)
        
        if subchapters:
            print(f"  Found {len(subchapters)} subchapters")
            
            # Extract each subchapter
            for j, subchapter in enumerate(subchapters):
                subchapter_text = self.html_to_text(subchapter['content'])
                
                if subchapter_text.strip():
                    subchapter_filename = f"[{subchapter['number']}] {chapter_folder_name}.txt"
                    subchapter_file = chapter_folder / subchapter_filename
                    
                    with open(subchapter_file, 'w', encoding='utf-8') as f:
                        f.write(f"# {marker['title']} - Part {subchapter['number']}\n\n")
                        f.write(subchapter_text)
                    
                    print(f"    Created: {subchapter_filename}")
        else:
            # No subchapters found, create single file
            chapter_text = self.html_to_text(combined_html)
            
            if not chapter_text.strip():
                return

            CHUNK_SIZE = 15000
            CHUNK_SIZE_TOLERANCE = 1.2  # Allow 20% oversize before splitting
            
            # If splitting is enabled and text is large enough
            if self.split_no_subchapters and len(chapter_text) > (CHUNK_SIZE * CHUNK_SIZE_TOLERANCE):
                self.split_and_save_text(chapter_text, chapter_folder, chapter_folder_name, marker['title'])
            else:
                # Default behavior: create a single file for the chapter
                print(f"  No subchapters found, creating single file.")
                main_filename = f"[1] {chapter_folder_name}.txt"
                main_file = chapter_folder / main_filename
                
                with open(main_file, 'w', encoding='utf-8') as f:
                    f.write(f"# {marker['title']}\n\n")
                    f.write(chapter_text)
                
                print(f"    Created: {main_filename}")

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
        content += f"Total chapters: {len(chapter_markers)}\n"
        if self.extract_subchapters:
            content += f"Extraction mode: Subchapters (folder per chapter)\n"
        else:
            content += f"Extraction mode: Single file per chapter\n"
        content += "\n" + "=" * 50 + "\n\n"
        
        # Add list of chapters
        for i, marker in enumerate(chapter_markers, 1):
            title = self.sanitize_filename(marker['title'])
            if self.extract_subchapters:
                folder_name = f"Chapter_{i:02d}_{title}"
                content += f"Chapter {i}: {marker['title']}\n"
                content += f"Folder: {folder_name}/\n\n"
            else:
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
                if self.extract_subchapters:
                    print("Each chapter is in its own folder with numbered subchapter files")
            else:
                print(f"Total files extracted: {len([f for f in self.output_dir.iterdir() if f.suffix == '.txt'])}")
            
        except Exception as e:
            print(f"Error during extraction: {e}")
            raise
        finally:
            self.cleanup()


def find_epub_files(directory, recursive=False):
    """Find all EPUB files in a directory, ignoring hidden files that start with '.'"""
    directory = Path(directory)
    epub_files = []
    
    if recursive:
        epub_files = list(directory.rglob("*.epub"))
    else:
        epub_files = list(directory.glob("*.epub"))
    
    # Filter out files that start with "." (hidden files, macOS metadata files, etc.)
    epub_files = [f for f in epub_files if not f.name.startswith('.')]
    
    return sorted(epub_files)

def bulk_extract_epubs(input_dir, output_dir, extract_subchapters=False, show_furigana=False, recursive=False, split_no_subchapters=False):
    """Extract multiple EPUB files from a directory, preserving directory structure"""
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    
    if not input_path.exists():
        raise FileNotFoundError(f"Input directory not found: {input_path}")
    
    if not input_path.is_dir():
        raise ValueError(f"Input path is not a directory: {input_path}")
    
    # Find all EPUB files
    epub_files = find_epub_files(input_path, recursive)
    
    if not epub_files:
        print(f"No EPUB files found in {input_path}")
        return
    
    print(f"Found {len(epub_files)} EPUB file(s) to process")
    
    # Create main output directory
    output_path.mkdir(parents=True, exist_ok=True)
    
    successful_extractions = 0
    failed_extractions = 0
    
    for i, epub_file in enumerate(epub_files, 1):
        print(f"\n{'='*60}")
        print(f"Processing EPUB {i}/{len(epub_files)}: {epub_file.name}")
        print(f"{'='*60}")
        
        # Calculate relative path from input directory to preserve structure
        relative_path = epub_file.relative_to(input_path)
        
        # Create output path preserving the directory structure
        # Remove the .epub extension from the filename and use it as the final folder name
        epub_folder_name = epub_file.stem
        
        # If the EPUB is in a subdirectory, preserve that structure
        if relative_path.parent != Path('.'):
            # Create: output_dir/series_folder/epub_name/
            epub_output_dir = output_path / relative_path.parent / epub_folder_name
        else:
            # Create: output_dir/epub_name/
            epub_output_dir = output_path / epub_folder_name
        
        try:
            extractor = EPUBExtractor(epub_file, epub_output_dir, extract_subchapters, show_furigana, split_no_subchapters)
            extractor.extract_chapters()
            successful_extractions += 1
            print(f"✓ Successfully extracted: {epub_file.name}")
        except Exception as e:
            failed_extractions += 1
            print(f"✗ Failed to extract {epub_file.name}: {e}")
            continue
    
    print(f"\n{'='*60}")
    print(f"BULK EXTRACTION COMPLETE")
    print(f"{'='*60}")
    print(f"Total files processed: {len(epub_files)}")
    print(f"Successful extractions: {successful_extractions}")
    print(f"Failed extractions: {failed_extractions}")
    print(f"Output directory: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Extract EPUB chapters into separate folders")
    parser.add_argument("epub_path", help="Path to the EPUB file, extracted EPUB folder, or directory containing EPUB files")
    parser.add_argument("-o", "--output", default="extracted_chapters", 
                       help="Output directory (default: extracted_chapters)")
    parser.add_argument("--subchapters", action="store_true",
                       help="Extract subchapters into separate files within chapter folders")
    parser.add_argument("--split-no-subchapters", action="store_true",
                        help="When using --subchapters, split chapters with no detected subchapters into smaller files.")
    parser.add_argument("--furigana", action="store_true",
                       help="Show furigana in parentheses format (e.g., 梓川咲太（あずさがわさくた）)")
    parser.add_argument("--bulk", action="store_true",
                       help="Process all EPUB files in the input directory (use with directory path)")
    parser.add_argument("--recursive", action="store_true",
                       help="Search for EPUB files recursively in subdirectories (use with --bulk)")
    
    args = parser.parse_args()
    
    input_path = Path(args.epub_path)
    
    try:
        # Check if bulk processing is requested or if input is a directory with EPUB files
        if args.bulk or (input_path.is_dir() and not (input_path / "META-INF").exists()):
            # Bulk processing mode
            if not input_path.is_dir():
                print(f"Error: Bulk processing requires a directory path, got: {input_path}")
                return 1
            
            bulk_extract_epubs(args.epub_path, args.output, args.subchapters, args.furigana, args.recursive, args.split_no_subchapters)
        else:
            # Single file/folder processing mode
            extractor = EPUBExtractor(args.epub_path, args.output, args.subchapters, args.furigana, args.split_no_subchapters)
            extractor.extract_chapters()
    except Exception as e:
        print(f"Failed to extract EPUB: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main()) 