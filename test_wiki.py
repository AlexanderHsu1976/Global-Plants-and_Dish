import wikipediaapi
import re

wiki_zh = wikipediaapi.Wikipedia(user_agent='PlantHistoryApp/1.0', language='zh', extract_format=wikipediaapi.ExtractFormat.WIKI)
wiki_en = wikipediaapi.Wikipedia(user_agent='PlantHistoryApp/1.0', language='en', extract_format=wikipediaapi.ExtractFormat.WIKI)

def test_extraction(name, lang='zh'):
    wiki = wiki_zh if lang == 'zh' else wiki_en
    page = wiki.page(name)
    print(f"\n--- Testing: {name} ({lang}) ---")
    if not page.exists():
        print("Page does not exist.")
        return
    
    print(f"Title: {page.title}")
    # print(f"Summary Start: {page.summary[:200]}")
    
    # Test Categorical Family Extraction
    families = []
    for cat in page.categories.values():
        title = cat.title.replace('Category:', '')
        if title.endswith('科'):
            families.append(title)
        elif 'Family' in title:
            families.append(title)
    print(f"Potential Families from Categories: {families}")
    
    # Test Scientific Name (Regex on Summary)
    content = page.summary
    latin_candidates = re.findall(r'\*([A-Z][a-z]+ [a-z]+)\*', content)
    if not latin_candidates:
        latin_candidates = re.findall(r'([A-Z][a-z]+ [a-z]+)', content[:500])
    
    stopwords = ["Wheat", "Rice", "Maize", "Common", "The", "It", "Is", "A", "And", "In", "Of", "Plant", "Genus", "Species", "Cereal", "Grain"]
    clean_candidates = [c for c in latin_candidates if not any(s.lower() == w.lower() for w in c.split() for s in stopwords)]
    print(f"Latin Candidates (Cleaned): {clean_candidates}")

test_extraction("小麥")
test_extraction("Triticum", 'en')
test_extraction("水稻")
test_extraction("Oryza sativa", 'en')
