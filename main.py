from fastapi import FastAPI, Header, HTTPException, Depends
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import subprocess, uuid, os

app = FastAPI()

SERVER = os.getenv("TTS_SERVER", "grpc.nvcf.nvidia.com:443")
FUNCTION_ID = os.getenv("TTS_FUNCTION_ID")
API_KEY = os.getenv("TTS_API_KEY")

PROTECT_TOKEN = os.getenv("PROTECT_TOKEN", "my-secret-token")

def verify_auth(authorization: str = Header(...)):
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or token != PROTECT_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True


class TTSRequest(BaseModel):
    text: str
    language_code: str = "en-US"
    voice: str = "Magpie-Multilingual.EN-US.Sofia"


@app.get("/health", dependencies=[Depends(verify_auth)])
def health():
    return JSONResponse(content={"status": "ok"})


@app.post("/tts", dependencies=[Depends(verify_auth)])
def tts(request: TTSRequest):
    output_file = f"audio_{uuid.uuid4().hex}.wav"

    cmd = [
        "python", "python-clients/scripts/tts/talk.py",
        "--server", SERVER,
        "--use-ssl",
        "--metadata", "function-id", FUNCTION_ID,
        "--metadata", "authorization", f"Bearer {API_KEY}",
        "--language-code", request.language_code,
        "--text", request.text,
        "--voice", request.voice,
        "--output", output_file,
    ]

    subprocess.run(cmd, check=True)

    return FileResponse(output_file, media_type="audio/wav", filename="speech.wav")
