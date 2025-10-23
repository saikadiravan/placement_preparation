import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import time

def get_gfg_url(company, role):
    """Construct GfG URL based on input."""
    company_slug = re.sub(r'\s+', '-', company.lower())
    return f"https://www.geeksforgeeks.org/{company_slug}-interview-experience/"

def extract_questions(url):
    """Scrape questions from GfG page."""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    try:
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            return None, f"Failed to fetch main page: {response.status_code}"
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Narrow to post content
        content = (soup.find('div', id=re.compile(r'post-\d+')) or 
                   soup.find('article') or 
                   soup.find('div', class_='entry-content') or 
                   soup.find('div', class_='text'))
        if not content:
            content = soup.find_all(['p', 'li'])
            text = '\n'.join([elem.get_text() for elem in content if not any(noise in elem.get_text().lower() for noise in ['comment', 'geeksforgeeks', 'improve', 'article tags', 'var '])])
        else:
            text = content.get_text(separator='\n')
        
        # Debug: Save raw text
        with open('raw_text.txt', 'w', encoding='utf-8') as f:
            f.write(f"Main page: {url}\n{text}\n")
        
        # Split by Round headers or paragraphs
        patterns = r'(Round\s*[:\d]+:|Question\s*:|\n{2,})'
        sections = re.split(patterns, text, flags=re.IGNORECASE)
        sections = [s.strip() for s in sections if s.strip() and len(s) > 10 and 
                    not any(noise in s.lower() for noise in ['comment', 'geeksforgeeks', 'improve', 'article tags', 'var '])]
        
        qa_pairs = []
        i = 0
        while i < len(sections):
            if re.match(r'(Round\s*[:\d]+:|Question\s*:)', sections[i], re.IGNORECASE):
                # Question is the next section
                question = sections[i+1] if i+1 < len(sections) else ''
                # Answer is everything until the next Round/Question
                answer = ''
                for j in range(i+2, len(sections)):
                    if re.match(r'(Round\s*[:\d]+:|Question\s*:)', sections[j], re.IGNORECASE):
                        break
                    answer += sections[j] + '\n'
                answer = answer.strip()
                if question and len(question) > 10:
                    qa_pairs.append({
                        'question': question[:200] + '...' if len(question) > 200 else question,
                        'answer': answer[:500] + '...' if len(answer) > 500 else answer
                    })
                i += 2
            else:
                i += 1
        
        # Debug: Log parsed pairs
        with open('raw_text.txt', 'a', encoding='utf-8') as f:
            f.write("\nParsed Q&A Pairs:\n")
            for idx, pair in enumerate(qa_pairs):
                f.write(f"Q{idx+1}: {pair['question']}\nA{idx+1}: {pair['answer']}\n\n")
        
        return qa_pairs, None
    
    except Exception as e:
        return None, f"Error during extraction: {str(e)}"

def main():
    company = input("Enter company name (e.g., Amazon): ").strip()
    role = input("Enter role (e.g., SDE): ").strip()
    
    url = get_gfg_url(company, role)
    print(f"Scraping: {url}")
    
    # Clear raw_text.txt
    with open('raw_text.txt', 'w', encoding='utf-8') as f:
        f.write("")
    
    data, error = extract_questions(url)
    if error:
        print(f"Extraction failed: {error}")
        return
    
    if not data or len(data) < 1:  # Lowered for testing
        print("Extraction incomplete—too few questions. Check raw_text.txt for clues.")
        return
    
    # Success: Save to CSV
    df = pd.DataFrame(data)
    df['company'] = company
    df['role'] = role
    df.to_csv(f"{company}_{role}_questions.csv", index=False)
    print(f"Success! Extracted {len(data)} Q&A pairs. Saved to {company}_{role}_questions.csv")
    
    # Gate: Proceed only if successful
    proceed = input("Extraction complete. Proceed to Transform step? (y/n): ")
    if proceed.lower() == 'y':
        print("TODO: Call transform function here (e.g., clean and tag topics)")

if __name__ == "__main__":
    main()