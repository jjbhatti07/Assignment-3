# Assignment 02 - Task 1: Gmail AI Email Responder

## Requirement covered
1. Capture the Gmail email the user opens.
2. Send the email text to a remotely hosted service.
3. Generate an AI suggested reply.
4. Return and display the suggested response to the Gmail user.

## Architecture

Gmail -> Chrome Extension -> Remote Flask API -> Hugging Face Inference -> Suggested Reply -> Extension

The extension never contains the Hugging Face token. The token stays on the backend.

## 1. Local backend test

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export HF_TOKEN='YOUR_NEW_HUGGING_FACE_TOKEN'
python app.py
```

Test:

```bash
curl http://127.0.0.1:5002/health
```

Generate a reply:

```bash
curl -X POST http://127.0.0.1:5002/generate-reply \
  -H 'Content-Type: application/json' \
  -d '{"subject":"Meeting tomorrow","sender":"teacher@example.com","body":"Can we meet tomorrow at 10 AM to discuss the assignment?"}'
```

## 2. Load the Chrome extension

Open Chrome/Chromium:

`chrome://extensions/`

Enable **Developer mode** -> **Load unpacked** -> select the `extension` folder.

Then open Gmail and open an email.

Use **Configure API** from the extension popup and set:

`http://127.0.0.1:5002`

or, after deployment, your public Render URL.

## 3. Remote deployment

The backend is ready for a Python web service such as Render.

Build command:

```bash
pip install -r requirements.txt
```

Start command:

```bash
gunicorn app:app
```

Environment variable:

```text
HF_TOKEN = your token
```

After deployment, put the service URL in the extension settings.

## 4. Submission

Do NOT submit `.venv` or any Hugging Face token.

Submit the extension source, backend source, requirements.txt, and README.md.
