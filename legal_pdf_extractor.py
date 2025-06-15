#!/usr/bin/env python3
"""
Simple VCC Act Extractor - Direct execution without CLI complexity
Based on debug analysis findings
"""

import fitz
import re
import json
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict

@dataclass
class Section:
    number: str
    title: str
    content: str
    part: str = ""
    word_count: int = 0
    has_penalties: bool = False
    section_type: str = ""
    subsections: Optional[List['Section']] = None
    
    def __post_init__(self):
        if self.subsections is None:
            self.subsections = []
        self.word_count = len(self.content.split()) if self.content else 0
        penalty_keywords = ['penalty', 'fine', 'imprisonment', 'offence', 'guilty', 'liable on conviction']
        self.has_penalties = any(keyword in self.content.lower() for keyword in penalty_keywords)

class SimpleVCCExtractor:
    """Simple VCC extractor that works immediately"""
    
    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        self.doc = None
        self.full_text = ""
        
    def extract_text(self):
        """Extract text from PDF"""
        print(f"📄 Extracting text from {self.pdf_path}...")
        
        self.doc = fitz.open(self.pdf_path)
        self.full_text = ""
        
        for page_num in range(len(self.doc)):
            page = self.doc[page_num]
            text = page.get_text()
            
            # Clean the text
            lines = text.split('\n')
            cleaned_lines = []
            
            for line in lines:
                line = line.strip()
                if not line or line.isdigit():
                    continue
                if any(skip in line for skip in [
                    'Variable Capital Companies',
                    'Act 2018',
                    '2020 Ed.',
                    'Informal Consolidation'
                ]):
                    continue
                cleaned_lines.append(line)
            
            cleaned_text = '\n'.join(cleaned_lines)
            self.full_text += f"{cleaned_text}\n"
        
        print(f"✅ Extracted {len(self.full_text)} characters from {len(self.doc)} pages")
        return self.full_text
    
    def find_sections(self):
        """Find all sections in the document"""
        print("🔍 Finding sections...")
        
        # Based on debug analysis, we have these patterns:
        patterns = {
            'simple': re.compile(r'^(\d+)\.\s+(.+?)(?=^\d+\.|^$|\Z)', re.MULTILINE | re.DOTALL),
            'dash': re.compile(r'^(\d+)\.—(.+?)(?=^\d+\.|^$|\Z)', re.MULTILINE | re.DOTALL),
            'alphanumeric': re.compile(r'^(\d+\w+)\.\s+(.+?)(?=^\d+\w*\.|^$|\Z)', re.MULTILINE | re.DOTALL),
        }
        
        # Find content starting from where actual sections begin
        # Skip TOC and front matter
        content_start = self.full_text.find("1. This Act is the Variable Capital Companies Act 2018")
        if content_start == -1:
            content_start = self.full_text.find("Short title")
            if content_start != -1:
                content_start = self.full_text.find("1.", content_start)
        
        if content_start == -1:
            print("❌ Could not find content start")
            return {}
        
        main_content = self.full_text[content_start:]
        print(f"📖 Analyzing {len(main_content)} characters of main content...")
        
        # Find all parts
        part_pattern = re.compile(r'PART\s+(\d+)\s*\n(.+?)(?=PART\s+\d+|\Z)', re.MULTILINE | re.DOTALL)
        part_matches = list(part_pattern.finditer(main_content))
        
        print(f"🎯 Found {len(part_matches)} parts")
        
        all_sections = {}
        
        for match in part_matches:
            part_num = match.group(1)
            part_content = match.group(2)
            part_name = f"PART {part_num}"
            
            print(f"📋 Processing {part_name}...")
            
            # Get part title
            part_lines = part_content.split('\n')
            part_title = ""
            for line in part_lines[:5]:
                line = line.strip()
                if line and not line.startswith(('Division', 'Section', 'Subdivision', 'Application')):
                    if not re.match(r'^\d+\.', line):
                        part_title = line
                        break
            
            # Find sections in this part
            sections = []
            
            # Try all patterns
            all_matches = []
            for pattern_name, pattern in patterns.items():
                matches = list(pattern.finditer(part_content))
                for match in matches:
                    all_matches.append({
                        'number': match.group(1),
                        'content': match.group(2).strip(),
                        'type': pattern_name,
                        'start': match.start()
                    })
            
            # Sort by position and remove overlaps
            all_matches.sort(key=lambda x: x['start'])
            
            # Remove overlapping matches
            filtered_matches = []
            for match in all_matches:
                overlap = False
                for existing in filtered_matches:
                    if abs(match['start'] - existing['start']) < 10:  # Too close
                        overlap = True
                        break
                if not overlap:
                    filtered_matches.append(match)
            
            # Create sections
            for match in filtered_matches:
                section_num = match['number']
                section_content = match['content']
                section_type = match['type']
                
                # Split into title and content
                lines = section_content.split('\n', 1)
                if lines:
                    title = lines[0].strip()
                    content = lines[1] if len(lines) > 1 else ""
                    
                    # Clean title
                    title = re.sub(r'^[—–-]\s*', '', title)
                    title = re.sub(r'\s+', ' ', title)
                    
                    # Create section
                    section = Section(
                        number=section_num,
                        title=title,
                        content=content,
                        part=part_name,
                        section_type=section_type
                    )
                    
                    sections.append(section)
            
            all_sections[part_name] = {
                'title': part_title,
                'sections': sections
            }
            
            print(f"  ✅ Found {len(sections)} sections in {part_name}")
        
        return all_sections
    
    def save_sections(self, sections_data, output_dir=None):
        """Save sections to files"""
        if output_dir is None:
            # Create output directory based on PDF filename
            pdf_name = Path(self.pdf_path).stem
            output_dir = f"{pdf_name}_Sections"
        
        print(f"💾 Saving sections to {output_dir}...")
        
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)
        
        total_sections = 0
        total_words = 0
        
        for part_name, part_data in sections_data.items():
            part_dir = output_path / part_name.replace(" ", "_")
            part_dir.mkdir(exist_ok=True)
            
            sections = part_data['sections']
            part_title = part_data['title']
            
            # Save part summary
            part_summary = {
                'part_name': part_name,
                'title': part_title,
                'section_count': len(sections),
                'total_words': sum(s.word_count for s in sections),
                'sections': [
                    {
                        'number': s.number,
                        'title': s.title,
                        'word_count': s.word_count,
                        'type': s.section_type
                    } for s in sections
                ]
            }
            
            with open(part_dir / "part_summary.json", 'w') as f:
                json.dump(part_summary, f, indent=2)
            
            # Save individual sections
            for section in sections:
                filename = f"Section_{section.number.replace('.', '_').zfill(3)}.txt"
                filepath = part_dir / filename
                
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(f"VARIABLE CAPITAL COMPANIES ACT 2018\n")
                    f.write("=" * 60 + "\n\n")
                    f.write(f"SECTION {section.number}: {section.title}\n")
                    f.write("=" * 60 + "\n\n")
                    f.write(f"Part: {section.part}\n")
                    f.write(f"Type: {section.section_type}\n")
                    f.write(f"Word Count: {section.word_count}\n")
                    f.write(f"Has Penalties: {'Yes' if section.has_penalties else 'No'}\n\n")
                    f.write("-" * 60 + "\n")
                    f.write("CONTENT:\n")
                    f.write("-" * 60 + "\n\n")
                    
                    if section.content:
                        f.write(section.content)
                    else:
                        f.write("(No additional content)")
            
            total_sections += len(sections)
            total_words += sum(s.word_count for s in sections)
        
        # Create summary
        summary = {
            'document': Path(self.pdf_path).name,
            'total_parts': len(sections_data),
            'total_sections': total_sections,
            'total_words': total_words,
            'parts': {name: {
                'title': data['title'],
                'section_count': len(data['sections'])
            } for name, data in sections_data.items()}
        }
        
        with open(output_path / "extraction_summary.json", 'w') as f:
            json.dump(summary, f, indent=2)
        
        print(f"✅ Saved {total_sections} sections across {len(sections_data)} parts")
        print(f"📊 Total words extracted: {total_words:,}")
        
        return summary
    
    def print_summary(self, sections_data):
        """Print a summary of what was extracted"""
        print("\n" + "=" * 80)
        print("VCC ACT 2018 - EXTRACTION SUMMARY")
        print("=" * 80)
        
        for part_name, part_data in sections_data.items():
            sections = part_data['sections']
            part_title = part_data['title']
            
            print(f"\n{part_name}: {part_title}")
            print(f"  Sections: {len(sections)}")
            if sections:
                total_words = sum(s.word_count for s in sections)
                penalties = sum(1 for s in sections if s.has_penalties)
                print(f"  Words: {total_words:,}")
                print(f"  Penalty sections: {penalties}")
                print(f"  Sample: Section {sections[0].number} - {sections[0].title[:50]}...")
        
        total_sections = sum(len(data['sections']) for data in sections_data.values())
        total_words = sum(sum(s.word_count for s in data['sections']) for data in sections_data.values())
        
        print(f"\nTOTAL: {total_sections} sections, {total_words:,} words")
        print("=" * 80)
    
    def close(self):
        if self.doc:
            self.doc.close()

def main():
    """Main extraction function"""
    print("🚀 Simple Legal Document Extractor")
    print("=" * 50)
    
    # Get PDF file from command line argument
    import sys
    
    if len(sys.argv) < 2:
        print("❌ Please provide a PDF file as argument")
        print("Usage: uv run python simple_vcc_extractor.py <pdf_file>")
        print("Example: uv run python simple_vcc_extractor.py VCC_Act_2018.pdf")
        return
    
    pdf_path = sys.argv[1]
    
    if not Path(pdf_path).exists():
        print(f"❌ PDF file not found: {pdf_path}")
        print("Please check the file path and try again")
        return
    
    print(f"📁 Using PDF: {pdf_path}")
    
    # Extract
    extractor = SimpleVCCExtractor(pdf_path)
    
    try:
        # Extract text
        extractor.extract_text()
        
        # Find sections
        sections_data = extractor.find_sections()
        
        if not sections_data:
            print("❌ No sections found")
            return
        
        # Save results
        summary = extractor.save_sections(sections_data)
        
        # Print summary
        extractor.print_summary(sections_data)
        
        pdf_name = Path(pdf_path).stem
        print(f"\n✅ Extraction complete! Check '{pdf_name}_Sections' directory")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        extractor.close()

if __name__ == "__main__":
    main()
