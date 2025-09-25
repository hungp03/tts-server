from fastapi import FastAPI, Header, HTTPException, Depends
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import subprocess, uuid, os, requests, tempfile

app = FastAPI()

### —— Config NVIDIA —— ###
SERVER = os.getenv("TTS_SERVER", "grpc.nvcf.nvidia.com:443")
FUNCTION_ID = os.getenv("TTS_FUNCTION_ID")
API_KEY = os.getenv("TTS_API_KEY")

### —— Config Cloudflare Aura-1 —— ###
CF_ACCOUNT_ID = os.getenv("CF_ACCOUNT_ID")
CF_API_TOKEN = os.getenv("CF_API_TOKEN")
CF_MODEL = os.getenv("CF_TTS_MODEL", "@cf/deepgram/aura-1")
CF_API_BASE = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/{CF_MODEL}"

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

class TTSV2Request(BaseModel):
    text: str
    speaker: str | None = None
    encoding: str | None = None
    container: str | None = None
    sample_rate: int | None = None
    bit_rate: int | None = None

@app.get("/health", dependencies=[Depends(verify_auth)])
def health():
    return JSONResponse(content={"status": "ok"})

@app.post("/tts/v1", dependencies=[Depends(verify_auth)])
def tts_v1(request: TTSRequest):
    uid = uuid.uuid4().hex
    filename = f"speech_{uid}.wav"
    filepath = os.path.join("/tmp", filename)

    cmd = [
        "python", "python-clients/scripts/tts/talk.py",
        "--server", SERVER,
        "--use-ssl",
        "--metadata", "function-id", FUNCTION_ID,
        "--metadata", "authorization", f"Bearer {API_KEY}",
        "--language-code", request.language_code,
        "--text", request.text,
        "--voice", request.voice,
        "--output", filepath,
    ]
    subprocess.run(cmd, check=True)
    return FileResponse(filepath, media_type="audio/wav", filename=filename)

@app.post("/tts/v2", dependencies=[Depends(verify_auth)])
def tts_v2(req: TTSV2Request):
    payload: dict = {"text": req.text}
    if req.speaker is not None:
        payload["speaker"] = req.speaker
    if req.encoding is not None:
        payload["encoding"] = req.encoding
    if req.container is not None:
        payload["container"] = req.container
    if req.sample_rate is not None:
        payload["sample_rate"] = req.sample_rate
    if req.bit_rate is not None:
        payload["bit_rate"] = req.bit_rate

    headers = {
        "Authorization": f"Bearer {CF_API_TOKEN}",
        "Content-Type": "application/json",
    }

    resp = requests.post(url=CF_API_BASE, json=payload, stream=True, headers=headers)
    if resp.status_code != 200:
        raise HTTPException(
            status_code=500,
            detail=f"TTS error: {resp.status_code} {resp.text}"
        )

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
    try:
        for chunk in resp.iter_content(chunk_size=8192):
            if chunk:
                tmp.write(chunk)
        tmp.flush()
    finally:
        tmp.close()

    uid = uuid.uuid4().hex
    filename = f"speech_{uid}.mp3"
    return FileResponse(tmp.name, media_type="audio/mpeg", filename=filename)
