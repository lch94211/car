from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import google.generativeai as genai
import re
import os
from dotenv import load_dotenv

# 🛡️ 보안 라이브러리
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

load_dotenv()

# 제미나이 API 설정
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-2.5-flash')

app = FastAPI(title="스마트 주유비 계산기 API")

# --- 🛡️ 보안 1: Rate Limiter ---
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# --- 🛡️ 보안 2: CORS 설정 ---
origins = ["*"] # 🚀 우선 배포 성공을 위해 모든 도메인 허용으로 유연하게 설정

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

class FuelRequest(BaseModel):
    vehicle_model: str   
    fuel_type: str       
    price_per_liter: int 
    target_distance: int 

fuel_efficiency_cache = {}

@app.get("/", response_class=HTMLResponse)
async def get_web_page(request: Request):
    html_content = """
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>스마트 주유비 계산기</title>
        <meta property="og:title" content=" Ai 스마트 주유비 계산기 🚗">
        <meta property="og:description" content="AI가 계산하는 정확한 주유비! 지금 바로 확인해보세요.">
        <meta property="og:image" content="https://images.unsplash.com/photo-1542362567-b07e54358753?q=80&w=1000&auto=format&fit=crop">
        <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-7788233630120009" crossorigin="anonymous"></script>
        <style>
            body { font-family: 'Malgun Gothic', sans-serif; background-color: #f4f7f6; display: flex; flex-direction: column; justify-content: center; align-items: center; height: 100vh; margin: 0; }
            .calculator { background: white; padding: 30px; border-radius: 15px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); width: 320px; }
            input, select, button { width: 100%; padding: 12px; margin-bottom: 15px; border-radius: 8px; border: 1px solid #ddd; box-sizing: border-box; }
            button { background-color: #0056b3; color: white; font-weight: bold; cursor: pointer; border: none; }
            #result-box { margin-top: 20px; padding: 15px; background-color: #e9f5ff; border-radius: 8px; display: none; }
        </style>
    </head>
    <body>
        <div class="calculator">
            <h2>🚗 Ai 주유비 계산기</h2>
            <input type="text" id="vehicle" placeholder="차종 (예: 토레스 하이브리드)">
            <select id="fuel"><option value="휘발유">휘발유</option><option value="경유">경유</option></select>
            <input type="number" id="price" placeholder="기름값 (원/L)">
            <input type="number" id="distance" placeholder="거리 (km)">
            <button onclick="fetchCalculation()">계산하기</button>
            <div id="result-box"></div>
        </div>
        <script>
            async function fetchCalculation() {
                const resultBox = document.getElementById('result-box');
                resultBox.style.display = 'block';
                resultBox.innerHTML = "⏳ AI 분석 중...";
                try {
                    const response = await fetch('/calculate-fuel', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            vehicle_model: document.getElementById('vehicle').value,
                            fuel_type: document.getElementById('fuel').value,
                            price_per_liter: parseInt(document.getElementById('price').value),
                            target_distance: parseInt(document.getElementById('distance').value)
                        })
                    });
                    const data = await response.json();
                    if(response.ok) {
                        resultBox.innerHTML = `✅ 연비: ${data.fuel_efficiency_km_l}km/L<br>⛽ 금액: ${data.total_cost_won.toLocaleString()}원`;
                    } else {
                        resultBox.innerHTML = "❌ " + data.detail;
                    }
                } catch (e) { resultBox.innerHTML = "❌ 서버 연결 오류"; }
            }
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.post("/calculate-fuel")
@limiter.limit("10/minute")
async def calculate_fuel(request: Request, req: FuelRequest):
    cache_key = f"{req.vehicle_model}_{req.fuel_type}"
    try:
        if cache_key not in fuel_efficiency_cache:
            # 💡 수정된 유연한 프롬프트
            prompt = f"""
            차종 '{req.vehicle_model}' ({req.fuel_type})의 공인 복합 연비(km/L) 숫자만 대답하세요. (예: 15.3)
            장난스러운 입력일 경우에만 'FAKE'라고 대답하세요.
            실제 브랜드의 최신 모델(예: 토레스 하이브리드)이라면 예상 연비를 숫자로만 유추해서 대답하세요. 다른 말은 절대 하지 마세요.
            """
            response = model.generate_content(prompt)
            if "FAKE" in response.text.upper():
                raise ValueError("실제 자동차 모델명을 입력해주세요.")
            numbers = re.findall(r"[-+]?\d*\.\d+|\d+", response.text)
            if not numbers: raise ValueError("연비 데이터를 찾을 수 없습니다.")
            fuel_efficiency_cache[cache_key] = float(numbers[0])
            
        eff = fuel_efficiency_cache[cache_key]
        total_cost = (req.target_distance / eff) * req.price_per_liter
        return {"fuel_efficiency_km_l": eff, "total_cost_won": int(total_cost)}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"오류 발생: {str(e)}")
