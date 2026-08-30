import os

from flask import Flask, jsonify, request
from flask_cors import CORS
from huggingface_hub import InferenceClient

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

HF_TOKEN = os.getenv("HF_TOKEN")
MODEL = os.getenv("HF_MODEL", "Qwen/Qwen3-4B-Instruct-2507")


def get_client():
    if not HF_TOKEN:
        raise RuntimeError("HF_TOKEN is not configured on the server.")
    return InferenceClient(api_key=HF_TOKEN)


def build_messages(subject: str, sender: str, body: str):
    email_text = f"Subject: {subject}\nFrom: {sender}\n\n{body}".strip()
    return [
        {
            "role": "system",
            "content": (
                "You are an email reply assistant. Draft one natural, professional "
                "reply to the email. Do not invent facts, dates, attachments, or commitments. "
                "Keep the response concise. Return only the reply body, without a subject line."
            ),
        },
        {
            "role": "user",
            "content": (
                "Write a suggested email reply to this message.\n\n"
                f"{email_text[:12000]}"
            ),
        },
    ]


@app.get("/")
def home():
    return jsonify({
        "service": "Gmail AI Email Responder",
        "status": "ok",
        "model": MODEL,
    })


@app.get("/health")
def health():
    return jsonify({"status": "ok", "model": MODEL})


@app.post("/generate-reply")
def generate_reply():
    try:
        data = request.get_json(silent=True) or {}
        subject = str(data.get("subject", "")).strip()
        sender = str(data.get("sender", "")).strip()
        body = str(data.get("body", "")).strip()

        if len(body) < 10:
            return jsonify({"error": "Email body is empty or too short."}), 400

        client = get_client()

        completion = client.chat_completion(
            messages=build_messages(subject, sender, body),
            model=MODEL,
            max_tokens=180,
            temperature=0.3,
        )

        reply = completion.choices[0].message.content.strip()
        if not reply:
            raise RuntimeError("The AI service returned an empty response.")

        return jsonify({
            "reply": reply,
            "model": MODEL,
        })

    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5002"))
    app.run(host="0.0.0.0", port=port, debug=False)
