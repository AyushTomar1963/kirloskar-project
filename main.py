from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import gspread
import datetime
import os
import google.generativeai as genai
from dotenv import load_dotenv

# Load the secret keys from the .env file
load_dotenv()

app = FastAPI()

# Allow any frontend (Laptop, Phone, or Cloud) to talk to this backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 1. Initialize Google Sheets
try:
    gc = gspread.service_account(filename='google_credentials.json')
    sh = gc.open_by_key("1eFMcq_pSOeOvz8-StfzFryOHN8Da9MsVL4nS_fGTAQE").sheet1 
    print("Successfully connected to the EXACT Google Sheet!")
    first_row = sh.row_values(1)
    
    # If the sheet is totally blank, OR if Row 1 doesn't have our headers...
    if not first_row or first_row[0] != "Timestamp":
        print("Headers missing! Forcing them into Row 1...")
        sh.insert_row(["Timestamp", "Part Name", "Status", "Worker Remark", "AI Category", "AI Formal Report"], 1)
        print("Headers added successfully.")
        
except Exception as e:
    print(f"Failed to connect to Google Sheets: {e}")

# 2. Initialize the AI Brain
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)
    # We use Flash because it is insanely fast for factory environments
    model = genai.GenerativeModel('gemini-2.5-flash')
else:
    print("WARNING: No Gemini API Key found in .env file!")

# 3. Define the data structure
class InspectionRequest(BaseModel):
    part_name: str
    status: str
    worker_remark: str | None = None

@app.get("/ping")
def ping_server():
    return {"message": "Python API is Live and AI is Ready!"}

@app.post("/api/log-inspection")
def log_inspection(request: InspectionRequest):
    
    ai_category = "N/A"
    ai_report = "N/A"
    
    # 4. THE AI LOGIC: Only trigger if the part is defective and there is a remark
    if request.status == "RED" and request.worker_remark and GEMINI_KEY:
        prompt = f"""
        You are a factory Quality Assurance assistant. 
        A worker submitted a defect remark which might be in casual language or Hindi: '{request.worker_remark}'
        
        1. Categorize the defect into 1-3 words (e.g., 'Physical Damage', 'Missing Component').
        2. Write a short, formal English report (1 sentence max) explaining the issue for management.
        
        Format your response EXACTLY like this with a pipe symbol in the middle:
        [CATEGORY] | [REPORT]
        """
        
        try:
            response = model.generate_content(prompt)
            # Split the AI's response down the middle using the pipe symbol
            parts = response.text.split("|")
            
            if len(parts) >= 2:
                ai_category = parts[0].strip()
                ai_report = parts[1].strip()
            else:
                ai_report = response.text.strip()
                
        except Exception as e:
            print(f"AI generation failed: {e}")
            # --- THE DEBUG HACK IS NOW IN THE RIGHT SPOT ---
            ai_report = f"API CRASH: {str(e)}"

    # 5. Save to Google Sheets
    try:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        row_data = [
            timestamp, 
            request.part_name, 
            request.status, 
            request.worker_remark or "None", 
            ai_category, 
            ai_report
        ]
        
        sh.append_row(row_data)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to write to Google Sheets: {str(e)}")

    return {"message": "Logged successfully with AI Report!"}