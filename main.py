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

genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-2.5-flash')

app = FastAPI(title="스마트 주유비 계산기 API")

# --- 🛡️ Rate Limiter ---
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# --- 🛡️ CORS 설정 ---
origins = [
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    "https://ai-smart-fuel.onrender.com"  
]

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

        <link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🚗</text></svg>">

        <meta property="og:title" content="스마트 주유비 계산기 🚗">
        <meta property="og:description" content="차종과 목적지만 입력하세요! AI가 정확한 필요 주유량과 예상 주유비를 계산해 드립니다.">
        <meta property="og:image" content="https://images.unsplash.com/photo-1542362567-b07e54358753?q=80&w=1000&auto=format&fit=crop">
        <meta property="og:url" content="https://ai-smart-fuel.onrender.com/">

        <script async src="https://www.googletagmanager.com/gtag/js?id=G-XXXXXXXXXX"></script>
        <script>
          window.dataLayer = window.dataLayer || [];
          function gtag(){dataLayer.push(arguments);}
          gtag('js', new Date());
          gtag('config', 'G-8KQKFJH24P');
        </script>

        <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-7788233630120009" crossorigin="anonymous"></script>

        <style>
            body { font-family: 'Malgun Gothic', sans-serif; background-color: #f4f7f6; display: flex; flex-direction: column; justify-content: center; align-items: center; height: 100vh; margin: 0; position: relative; }
            .calculator { background: white; padding: 30px; border-radius: 15px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); width: 320px; z-index: 1; }
            h2 { text-align: center; color: #333; margin-bottom: 20px; }
            input, select { width: 100%; padding: 12px; margin-bottom: 15px; border: 1px solid #ddd; border-radius: 8px; box-sizing: border-box; font-size: 14px; }
            button { width: 100%; padding: 15px; background-color: #0056b3; color: white; border: none; border-radius: 8px; font-size: 16px; font-weight: bold; cursor: pointer; transition: 0.3s; }
            button:hover { background-color: #004494; }
            #result-box { margin-top: 20px; padding: 15px; background-color: #e9f5ff; border-radius: 8px; color: #0056b3; display: none; font-size: 14px; line-height: 1.6; }
            .highlight { font-size: 18px; font-weight: bold; color: #d9534f; }
            .banner-ad { width: 320px; height: 50px; background-color: #e0e0e0; border: 1px dashed #999; margin-top: 20px; display: flex; justify-content: center; align-items: center; color: #666; font-size: 12px; font-weight: bold; }
            .interstitial-ad { position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background-color: rgba(0,0,0,0.9); z-index: 100; display: none; flex-direction: column; justify-content: center; align-items: center; color: white; }
            .interstitial-ad h1 { color: #f1c40f; }
            .interstitial-ad p { font-size: 14px; color: #ccc; }
        </style>
    </head>
    <body>
        
        <div class="interstitial-ad" id="full-ad">
            <h1>[전면 광고 스폰서]</h1>
            <p>이번 달 자동차 보험료, 최저가로 비교해보세요!</p>
            <p style="margin-top: 50px; font-size: 12px;">(2초 후 자동으로 닫히고 계산 결과가 나옵니다...)</p>
        </div>

        <div class="calculator">
            <h2>🚗 Ai 스마트 주유비 계산기</h2>
            <input type="text" id="vehicle" placeholder="차종 (예: 쏘렌토 하이브리드)">
            <select id="fuel">
                <option value="휘발유">휘발유</option>
                <option value="경유">경유</option>
            </select>
            <input type="text" id="price" placeholder="현재 주유소 가격 (원/L)" oninput="formatNumber(this)">
            <input type="text" id="distance" placeholder="목표 주행 거리 (km)" oninput="formatNumber(this)">
            <button onclick="startCalculation()">계산하기</button>

            <div id="result-box"></div>
        </div>

        <div class="banner-ad" id="real-banner-space">
            [구글 애드센스 심사 대기 중...]
        </div>

        <script>
            // 🚀 UX 개선: 숫자 입력 시 천 단위 콤마 자동 추가 함수
            function formatNumber(input) {
                let value = input.value.replace(/,/g, ''); 
                if (!isNaN(value) && value !== "") {
                    input.value = Number(value).toLocaleString('ko-KR');
                } else {
                    input.value = value.replace(/[^0-9]/g, ''); 
                }
            }

            async function startCalculation() {
                const vehicle = document.getElementById('vehicle').value;
                // 계산을 위해 콤마 제거 후 숫자로 변환
                const priceStr = document.getElementById('price').value.replace(/,/g, '');
                const distanceStr = document.getElementById('distance').value.replace(/,/g, '');

                if(!vehicle || !priceStr || !distanceStr) {
                    alert("모든 칸을 입력해주세요!");
                    return;
                }

                const fullAd = document.getElementById('full-ad');
                const resultBox = document.getElementById('result-box');

                // 1. 전면 광고 띄우기 및 로딩 UI 표시
                fullAd.style.display = 'flex';
                resultBox.style.display = 'block';
                resultBox.innerHTML = "⏳ 입력하신 차종을 검증 및 분석 중입니다...";

                // 🚀 속도 개선: 2. 광고가 뜨는 동안 백그라운드에서 API 호출 동시 진행 (비동기 병렬 처리)
                const fetchPromise = fetch('/calculate-fuel', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        vehicle_model: vehicle,
                        fuel_type: document.getElementById('fuel').value,
                        price_per_liter: parseInt(priceStr),
                        target_distance: parseInt(distanceStr)
                    })
                });

                // 3. 광고 노출 시간 2초 대기
                await new Promise(resolve => setTimeout(resolve, 2000));
                
                // 4. 전면 광고 닫기
                fullAd.style.display = 'none';

                // 5. 서버 응답 결과 대기 및 화면 출력 (미리 끝났다면 즉시 출력됨)
                try {
                    const response = await fetchPromise;
                    
                    if(response.status === 429) {
                        resultBox.innerHTML = "<span style='color: red; font-weight: bold;'>❌ 너무 많은 요청이 발생했습니다. 1분 후에 다시 시도해주세요.</span>";
                        return;
                    }

                    const data = await response.json();
                    
                    if(response.ok) {
                        resultBox.innerHTML = `
                            ✅ <b>계산 완료!</b><br><br>
                            🚘 공인 연비: ${data.fuel_efficiency_km_l} km/L<br>
                            ⛽ 필요 주유량: ${data.required_fuel_liter} L<br>
                            💳 예상 결제 금액: <span class="highlight">${data.total_cost_won.toLocaleString()}원</span>
                        `;
                    } else {
                        resultBox.innerHTML = "<span style='color: red; font-weight: bold;'>❌ " + data.detail + "</span>";
                    }
                } catch (error) {
                    resultBox.innerHTML = "❌ 서버와 연결할 수 없습니다.";
                }
            }
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.post("/calculate-fuel")
@limiter.limit("5/minute")
async def calculate_fuel(request: Request, req: FuelRequest):
    # 🚀 서버 효율 개선: 띄어쓰기 제거 및 대문자 변환 정규화 (캐시 적중률 극대화)
    normalized_vehicle = req.vehicle_model.replace(" ", "").upper()
    cache_key = f"{normalized_vehicle}_{req.fuel_type}"
    
    try:
        if cache_key not in fuel_efficiency_cache:
            prompt = f"""
            차종 '{req.vehicle_model}' ({req.fuel_type})의 공인 복합 연비(km/L) 숫자만 대답하세요. (예: 15.3)
            장난스러운 입력일 경우에만 'FAKE'라고 대답하세요.
            실제 브랜드의 최신 모델이라면 예상 연비를 숫자로만 유추해서 대답하세요. 다른 말은 절대 하지 마세요.
            """
            response = model.generate_content(prompt)
            
            if "FAKE" in response.text.upper():
                raise ValueError("😅 실제 존재하는 자동차 모델명을 입력해주세요.")

            numbers = re.findall(r"[-+]?\d*\.\d+|\d+", response.text)
            if not numbers: 
                raise ValueError("정확한 연비 데이터를 찾을 수 없습니다.")
            
            fuel_efficiency_cache[cache_key] = float(numbers[0])
            
        fuel_efficiency = fuel_efficiency_cache[cache_key]
        required_fuel = req.target_distance / fuel_efficiency
        total_cost = required_fuel * req.price_per_liter
        
        return {
            "fuel_efficiency_km_l": fuel_efficiency,
            "required_fuel_liter": round(required_fuel, 2),
            "total_cost_won": int(total_cost)
        }
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"서버 처리 중 오류가 발생했습니다: {str(e)}")
