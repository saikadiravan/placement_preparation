import json
import requests
from pathlib import Path
from src.utils.paths import OUTPUTS_DIR

# Default Ollama local endpoint
OLLAMA_URL = "http://localhost:11434/api/generate"
# Change this to your installed model (e.g., "llama3", "mistral")
OLLAMA_MODEL = "llama3:latest"

def chat_with_insights(company: str, user_query: str) -> dict:
    """
    RAG-based function that reads the company insights and uses Ollama 
    to answer the user's specific query.
    """
    print(f"\n[Conversation Agent] Searching insights for {company}...")
    
    company_formatted = company.lower().replace(" ", "_").replace(".", "")
    
    # Check for either JSON or TXT insights in the outputs folder
    json_path = OUTPUTS_DIR / f"{company_formatted}_insights.json"
    txt_path = OUTPUTS_DIR / f"{company_formatted}_insights.txt"
    
    context_data = ""
    if json_path.exists():
        with open(json_path, "r", encoding="utf-8") as f:
            context_data = json.dumps(json.load(f))
    elif txt_path.exists():
        with open(txt_path, "r", encoding="utf-8") as f:
            context_data = f.read()
    else:
        return {"error": f"No insights data found for {company}. Please run the ETL pipeline first."}

    # Construct the RAG Prompt
    prompt = f"""
    You are an expert Career Coach and Placement Assistant. 
    You have access to the following highly accurate interview data extracted from recent candidates at {company}:
    
    --- START INTERVIEW DATA ---
    {context_data[:4000]}  # Truncated to prevent context window overflow
    --- END INTERVIEW DATA ---
    
    INSTRUCTIONS:
    1. Answer the user's question comprehensively using ONLY the information provided in the data above.
    2. Be conversational, encouraging, and helpful.
    3. If the answer is not contained within the data, clearly state: "I don't have that specific information in my current data for {company}, but..." and offer general advice.
    
    USER QUESTION: {user_query}
    
    ANSWER:
    """
    
    # Call Local Ollama
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_ctx": 4096  # Expands Ollama's memory to handle the large interview data
        }
    }
    try:
        response = requests.post(OLLAMA_URL, json=payload)
        response.raise_for_status()
        answer = response.json().get("response", "").strip()
        return {"company": company, "query": user_query, "reply": answer}
        
    except requests.exceptions.ConnectionError:
        return {"error": "Ollama is not running. Please start Ollama locally (e.g., 'ollama serve')."}
    except Exception as e:
        return {"error": f"Ollama generation failed: {str(e)}"}

if __name__ == "__main__":
    # Test the Conversational Agent locally in your terminal!
    print("🤖 PlacementPrep AI Chatbot (Powered by Ollama)")
    target_company = input("Enter company to query (e.g., Amazon, Deloitte): ").strip() or "Amazon"
    
    while True:
        question = input(f"\nAsk a question about {target_company} interviews (or type 'exit'): ")
        if question.lower() == 'exit':
            break
            
        result = chat_with_insights(target_company, question)
        
        if "error" in result:
            print(f"\n❌ Error: {result['error']}")
        else:
            print(f"\n💡 AI Coach: {result['reply']}")