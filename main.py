from fastapi import FastAPI
from backend.src.foundation.models import Feedback

app = FastAPI()

# مسار لاستقبال التقييمات
@app.post("/feedback/")
async def create_feedback(feedback: Feedback):
    # هنا سيتم لاحقاً ربط قاعدة البيانات
    return {"message": "تم استلام تقييمك بنجاح", "data": feedback}

@app.get("/")
async def root():
    return {"message": "مرحباً بك في LegalMind API"}